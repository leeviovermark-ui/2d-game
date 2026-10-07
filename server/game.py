"""Single-thread authority. Requests transact synchronously; no await inside mutations."""
from copy import deepcopy
import math
import re
import secrets
import time
from .definitions import ITEMS, RECIPES, MOVE, WIDTH, HEIGHT, solid
from .inventory import Rejected, require, integer, add, remove, empty, transfer, quantity
from .world import normalize
from .trading import Trading


class Game:
    def __init__(self, store, clock=time.time):
        self.store = store
        self.clock = clock
        self.players = {}
        self.worlds = {}
        self.trades = {}
        self.invites = {}
        self.outbox = []
        self.trading = Trading(self)

    def emit(self, destination, kind, **data):
        self.outbox.append((destination, {'type': kind, **data}))

    def world(self, name):
        if name not in self.worlds:
            self.worlds[name] = self.store.load_world(name)
        return self.worlds[name]

    def join(self, ident):
        if ident in self.players:
            return self.players[ident]
        p = self.store.player(ident)
        w = self.world(p['world'])
        if w.collides(p['x'], p['y']):
            p['x'], p['y'] = w.spawn()
        self.players[ident] = p
        return p

    def leave(self, ident):
        if ident not in self.players:
            return
        p = self.players[ident]
        self.trading.cancel_trade(p)
        self.store.save_player(p)
        del self.players[ident]
        self.emit('world:'+p['world'], 'departure', id=ident, name=p['name'])
        self.unload()

    def unload(self):
        active = {p['world'] for p in self.players.values()}
        for name in list(self.worlds):
            if name not in active:
                del self.worlds[name]

    def inventory(self, p):
        self.store.save_player(p)
        self.emit(p['id'], 'inventory', slots=p['inventory'], selected=p['selected'])

    def target(self, p, data, permission=True):
        x, y = integer(data.get('x'), 0, WIDTH-1), integer(data.get('y'), 0, HEIGHT-1)
        w = self.world(p['world'])
        require(math.hypot(x+.5-p['x'], y+.5-p['y']-.7) <= MOVE['reach'], 'Move closer to that tile.')
        require(not permission or w.allowed(p['id']), 'This world is protected. Ask its owner for builder access.')
        return w, x, y

    def mutable_inventory(self, p):
        require(p['trade'] is None, 'Finish or cancel your trade first.')

    def command(self, ident, data):
        require(isinstance(data, dict), 'Invalid request.')
        p = self.players[ident]
        kind = data.get('type')
        if kind == 'input':
            axis = data.get('axis')
            require(type(axis) is int and axis in (-1, 0, 1) and type(data.get('jump')) is bool, 'Invalid movement.')
            p['input'] = {'axis': axis, 'jump': data['jump']}
            p['input_time'] = self.clock()
            return
        if kind == 'chat':
            text = data.get('text')
            require(isinstance(text, str) and 0 < len(text.strip()) <= 180, 'Chat is limited to 180 characters.')
            require(self.clock()-p['last_chat'] >= .7, 'Please slow down your messages.')
            text = ''.join(c for c in text.strip() if c.isprintable())
            p['last_chat'] = self.clock()
            for other in self.players.values():
                if other['world'] == p['world'] and ident not in other['ignore']:
                    self.emit(other['id'], 'chat', name=p['name'], id=ident, text=text)
            return
        if kind == 'ignore':
            target = data.get('player')
            require(isinstance(target, str), 'Invalid player.')
            p['ignore'].symmetric_difference_update({target})
            self.emit(ident, 'notice', text='Chat block updated for this session.')
            return
        if kind == 'directory':
            self.emit(ident, 'directory', worlds=self.store.directory())
            return
        request = data.get('request')
        require(isinstance(request, str) and re.fullmatch(r'[A-Za-z0-9_-]{8,64}', request), 'Missing request ID.')
        handlers = {'select': self.select, 'move_slot': self.move_slot, 'drop_item': self.drop_item,
                    'place': self.place, 'mine': self.mine, 'mine_cancel': self.mine_cancel,
                    'interact': self.interact, 'craft': self.craft, 'storage': self.storage,
                    'travel': self.travel, 'create_world': self.create_world, 'permissions': self.permissions,
                    'trade_request': self.trading.trade_request, 'trade_accept': self.trading.trade_accept,
                    'trade_offer': self.trading.trade_offer, 'trade_lock': self.trading.trade_lock,
                    'trade_confirm': self.trading.trade_confirm, 'trade_cancel': lambda a, b: self.trading.cancel_trade(a)}
        require(kind in handlers, 'Unknown action.')
        if kind in ('place', 'drop_item', 'craft', 'storage', 'move_slot'):
            require(self.clock()-p['last_action'] >= .08, 'Please slow down.')
        # Keep the cache and pending broadcasts consistent if any validation/DB operation fails.
        saved_players, saved_trades, saved_invites = deepcopy(self.players), deepcopy(self.trades), deepcopy(self.invites)
        saved_worlds = deepcopy(self.worlds)
        out_len = len(self.outbox)
        try:
            with self.store.transaction():
                self.store.remember(ident, request)
                handlers[kind](p, data)
                if kind in ('place', 'drop_item', 'craft', 'storage', 'move_slot'):
                    p['last_action'] = self.clock()
        except BaseException:
            self.players, self.trades, self.invites, self.worlds = saved_players, saved_trades, saved_invites, saved_worlds
            del self.outbox[out_len:]
            raise
        self.emit(ident, 'ack', request=request)

    def select(self, p, d):
        p['selected'] = integer(d.get('slot'), 0, 9)
        p['mining'] = None
        self.inventory(p)

    def move_slot(self, p, d):
        self.mutable_inventory(p)
        a, b = integer(d.get('from'), 0, 29), integer(d.get('to'), 0, 29)
        require(a != b and p['inventory'][a] is not None, 'Choose a different slot.')
        inv = deepcopy(p['inventory'])
        count = integer(d.get('count'), 1, inv[a]['n'])
        if inv[b] and inv[b]['id'] != inv[a]['id']:
            require(count == inv[a]['n'], 'Only full stacks can be swapped.')
            inv[a], inv[b] = inv[b], inv[a]
        else:
            room = ITEMS[inv[a]['id']]['stack'] - (inv[b]['n'] if inv[b] else 0)
            require(room >= count, 'That stack is full.')
            inv[b] = {'id': inv[a]['id'], 'n': (inv[b]['n'] if inv[b] else 0) + count}
            inv[a]['n'] -= count
            if not inv[a]['n']:
                inv[a] = None
        p['inventory'] = inv
        p['mining'] = None
        self.inventory(p)

    def drop_item(self, p, d):
        self.mutable_inventory(p)
        slot = integer(d.get('slot'), 0, 29)
        stack = p['inventory'][slot]
        require(stack is not None, 'Empty slot.')
        n = integer(d.get('count'), 1, stack['n'])
        item = stack['id']
        stack['n'] -= n
        if not stack['n']:
            p['inventory'][slot] = None
        self.new_drop(self.world(p['world']), p['x'], p['y']+.9, item, n, grace=2)
        p['mining'] = None
        self.inventory(p)

    def new_drop(self, w, x, y, item, n, grace=.15):
        drop = {'id': secrets.token_hex(10), 'x': x, 'y': y, 'item': item, 'n': n, 'ready': self.clock()+grace}
        w.drops[drop['id']] = drop
        self.store.drop(w.name, drop)
        self.emit('world:'+w.name, 'drop', drop=drop)

    def place(self, p, d):
        self.mutable_inventory(p)
        w, x, y = self.target(p, d)
        require(w.tile(x, y) is None, 'That tile is occupied.')
        stack = p['inventory'][p['selected']]
        require(stack is not None, 'Select a block or seed on your hotbar.')
        item = stack['id']
        definition = ITEMS[item]
        require(definition['category'] in ('block', 'seed', 'station', 'storage', 'core'), 'This item cannot be placed.')
        tile = definition.get('place', item)
        require(y >= 2 and y < HEIGHT-1, 'Keep the world boundary intact.')
        require(any(w.tile(x+dx, y+dy) for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]), 'Build beside an existing tile.')
        if solid(tile):
            for other in self.players.values():
                if other['world'] == w.name:
                    require(not (x < other['x']+MOVE['width']/2 and x+1 > other['x']-MOVE['width']/2
                                 and y < other['y']+MOVE['height'] and y+1 > other['y']), 'A player is standing there.')
        if tile == 'crop':
            require(w.tile(x, y+1) in ('dirt', 'grass', 'sand', 'snow'), 'Plant on earth, turf, sand, or snow.')
            w.crops[(x, y)] = self.clock()
            self.store.crop(w.name, x, y, self.clock())
        if tile == 'core':
            require(w.name != 'NEXUS', 'NEXUS is a shared refuge. Create a world to claim it.')
            require(w.meta['owner'] is None, 'This world already has an owner.')
            w.meta.update(owner=p['id'], owner_name=p['name'], guest_build=False)
            self.store.save_meta(w.meta)
            self.emit('world:'+w.name, 'metadata', meta=w.meta)
            self.store.audit('claim', [p['id']], {'world': w.name})
        if tile == 'chest':
            w.containers[(x, y)] = empty(12)
            self.store.container(w.name, x, y, empty(12))
        stack['n'] -= 1
        if not stack['n']:
            p['inventory'][p['selected']] = None
        w.cells[(x, y)] = tile
        self.store.tile(w.name, x, y, tile)
        self.emit('world:'+w.name, 'tile', x=x, y=y, item=tile, planted=w.crops.get((x, y)))
        self.inventory(p)

    def mine(self, p, d):
        self.mutable_inventory(p)
        w, x, y = self.target(p, d)
        item = w.tile(x, y)
        require(item is not None, 'Nothing to mine here.')
        require(y < HEIGHT-1, 'The bottom foundation is protected.')
        require(item != 'core', 'World Cores cannot be mined in this slice.')
        require(not any(w.containers.get((x, y), [])), 'Empty the chest before mining it.')
        tool = p['inventory'][p['selected']]
        tool_def = ITEMS[tool['id']] if tool else {}
        require(tool_def.get('level', 0) >= ITEMS[item].get('level', 0), 'You need a better pickaxe for this material.')
        if p['mining'] and p['mining']['x'] == x and p['mining']['y'] == y:
            return  # Holding/replaying start never accelerates the server timer.
        p['mining'] = {'x': x, 'y': y, 'item': item, 'start': self.clock(),
                       'duration': ITEMS[item]['hardness'] / tool_def.get('power', 1), 'slot': p['selected'],
                       'tool': tool['id'] if tool else None}

    def mine_cancel(self, p, d):
        p['mining'] = None

    def finish_mining(self, p):
        m = p['mining']
        if not m:
            return
        w = self.world(p['world'])
        valid = (w.tile(m['x'], m['y']) == m['item'] and w.allowed(p['id']) and p['trade'] is None
                 and math.hypot(m['x']+.5-p['x'], m['y']+.5-p['y']-.7) <= MOVE['reach']
                 and p['selected'] == m['slot'] and not any(w.containers.get((m['x'], m['y']), [])))
        valid = valid and (p['inventory'][p['selected']] or {}).get('id') == m['tool']
        if not valid:
            p['mining'] = None
            return
        if self.clock()-m['start'] < m['duration']:
            return
        x, y = m['x'], m['y']
        with self.store.transaction():
            self.store.tile(w.name, x, y, None)
            self.store.crop(w.name, x, y)
            self.new_drop(w, x+.5, y+.5, ITEMS[m['item']]['drop'], 1)
        w.cells.pop((x, y))
        w.crops.pop((x, y), None)
        p['mining'] = None
        self.emit('world:'+w.name, 'tile', x=x, y=y, item=None)

    def interact(self, p, d):
        self.mutable_inventory(p)
        w, x, y = self.target(p, d)
        item = w.tile(x, y)
        if item == 'crop':
            require(self.clock()-w.crops.get((x, y), self.clock()) >= ITEMS['crop']['growth'], 'Your sungrain is still growing.')
            inv = deepcopy(p['inventory'])
            require(add(inv, 'grain', 3) == 0 and add(inv, 'seed', 2) == 0, 'Make room for your harvest.')
            p['inventory'] = inv
            w.cells.pop((x, y))
            w.crops.pop((x, y))
            self.store.tile(w.name, x, y, None)
            self.store.crop(w.name, x, y)
            self.inventory(p)
            self.emit('world:'+w.name, 'tile', x=x, y=y, item=None)
            self.emit(p['id'], 'notice', text='Harvested 3 sungrain + 2 seeds.')
        elif item == 'chest':
            inv = w.containers.setdefault((x, y), empty(12))
            self.emit(p['id'], 'storage', x=x, y=y, slots=inv)
        elif item in ('bench', 'furnace'):
            self.emit(p['id'], 'open_craft')
        elif item == 'core':
            self.emit(p['id'], 'open_permissions', meta=w.meta)
        else:
            raise Rejected('Point at a crop, chest, station, or World Core to interact.')

    def craft(self, p, d):
        self.mutable_inventory(p)
        recipe = RECIPES.get(d.get('recipe'))
        require(recipe is not None, 'Unknown recipe.')
        if station := recipe.get('station'):
            w = self.world(p['world'])
            require(any(w.tile(x, y) == station for x in range(max(0, int(p['x'])-5), min(WIDTH, int(p['x'])+6))
                        for y in range(max(0, int(p['y'])-5), min(HEIGHT, int(p['y'])+6))
                        if math.hypot(x+.5-p['x'], y+.5-p['y']-.7) <= MOVE['reach']), 'Stand near a '+ITEMS[station]['name']+'.')
        inv = deepcopy(p['inventory'])
        for item, n in recipe['ingredients'].items():
            remove(inv, item, n)
        require(add(inv, recipe['output'], recipe['amount']) == 0, 'Make room in your inventory.')
        p['inventory'] = inv
        p['mining'] = None
        self.inventory(p)
        self.store.audit('craft', [p['id']], {'recipe': recipe['id']})
        self.emit(p['id'], 'notice', text='Crafted '+ITEMS[recipe['output']]['name']+'.')

    def storage(self, p, d):
        self.mutable_inventory(p)
        w, x, y = self.target(p, d)
        require(w.tile(x, y) == 'chest', 'That chest no longer exists.')
        chest = w.containers.setdefault((x, y), empty(12))
        require(type(d.get('deposit')) is bool, 'Invalid transfer.')
        if d['deposit']:
            p['inventory'], chest = transfer(p['inventory'], chest, d.get('slot'), d.get('count'))
        else:
            chest, p['inventory'] = transfer(chest, p['inventory'], d.get('slot'), d.get('count'))
        w.containers[(x, y)] = chest
        self.store.container(w.name, x, y, chest)
        self.inventory(p)
        # Everyone with an open chest receives the current slots; all transfers revalidate.
        self.emit('world:'+w.name, 'storage_update', x=x, y=y, slots=chest)
        self.store.audit('storage', [p['id']], {'world': w.name, 'x': x, 'y': y, 'deposit': d['deposit']})

    def travel(self, p, d):
        name = normalize(d.get('world'))
        target = self.world(name)
        x, y = target.spawn()
        old = p['world']
        self.trading.cancel_trade(p)
        p.update(world=name, x=x, y=y, vx=0., vy=0., mining=None)
        self.store.save_player(p)
        self.emit('world:'+old, 'departure', id=p['id'], name=p['name'])
        self.emit(p['id'], 'world', world=target.snapshot())
        self.emit(p['id'], 'notice', text='Welcome to '+name+'.')
        self.unload()

    def create_world(self, p, d):
        require(self.clock()-p.get('last_create', 0) > 5, 'Wait a moment before creating another world.')
        name = normalize(d.get('world'))
        require(d.get('biome') in ('forest', 'desert', 'snow'), 'Choose a valid biome.')
        require(len(self.store.directory()) < 100, 'This development server has reached its 100-world limit.')
        self.worlds[name] = self.store.create_world(name, d['biome'])
        p['last_create'] = self.clock()
        self.travel(p, {'world': name})
        self.emit(p['id'], 'directory', worlds=self.store.directory())

    def permissions(self, p, d):
        w = self.world(p['world'])
        require(w.meta['owner'] == p['id'], 'Only the owner can change permissions.')
        require(type(d.get('guest_build')) is bool, 'Invalid permission.')
        names = d.get('builders', [])
        require(isinstance(names, list) and len(names) <= 20 and all(isinstance(n, str) and len(n) <= 20 for n in names), 'Invalid builder list.')
        builders = []
        builder_names = []
        for name in names:
            row = self.store.db.execute('SELECT id,username FROM accounts WHERE username=? COLLATE NOCASE', (name.strip(),)).fetchone()
            require(row is not None, 'Unknown explorer: '+name)
            builders.append(row[0])
            builder_names.append(row[1])
        w.meta.update(guest_build=d['guest_build'], builders=builders, builder_names=builder_names)
        self.store.save_meta(w.meta)
        self.emit('world:'+w.name, 'metadata', meta=w.meta)
        self.emit(p['id'], 'notice', text='World permissions saved.')

    def tick(self, dt):
        for p in list(self.players.values()):
            w = self.world(p['world'])
            axis = p['input']['axis'] if self.clock()-p['input_time'] < .35 else 0
            accel = MOVE['acceleration'] * (1 if p['grounded'] else MOVE['air_control'])
            target = axis * MOVE['speed']
            amount = (accel if axis else MOVE['friction']) * dt
            p['vx'] += max(-amount, min(amount, target-p['vx']))
            if p['input']['jump'] and p['grounded']:
                p['vy'] = -MOVE['jump']
            p['input']['jump'] = False
            p['vy'] = min(20, p['vy']+MOVE['gravity']*dt)
            # Small axis-separated steps prevent tunneling even under high fall speed.
            steps = max(1, math.ceil(max(abs(p['vx']), abs(p['vy']))*dt/.15))
            for _ in range(steps):
                nx = p['x'] + p['vx']*dt/steps
                if not w.collides(nx, p['y']):
                    p['x'] = nx
                else:
                    p['vx'] = 0
                ny = p['y'] + p['vy']*dt/steps
                if not w.collides(p['x'], ny):
                    p['y'] = ny
                else:
                    p['vy'] = 0
            p['grounded'] = w.collides(p['x'], p['y']+.025)
            self.finish_mining(p)
            if p['trade']:
                trade = self.trades.get(p['trade'])
                if trade and not self.trading.nearby(*[self.players[i] for i in trade['players']]):
                    self.trading.cancel_trade(p, 'Trade cancelled: an explorer moved away.')
            else:
                self.pickup(p, w)

    def pickup(self, p, w):
        for ident, drop in list(w.drops.items()):
            if drop['ready'] > self.clock() or math.hypot(drop['x']-p['x'], drop['y']-p['y']-.7) > 1.6:
                continue
            inv = deepcopy(p['inventory'])
            remainder = add(inv, drop['item'], drop['n'])
            if remainder == drop['n']:
                continue
            with self.store.transaction():
                p['inventory'] = inv
                if remainder:
                    drop['n'] = remainder
                    self.store.drop(w.name, drop)
                    self.emit('world:'+w.name, 'drop', drop=drop)
                else:
                    del w.drops[ident]
                    self.store.db.execute('DELETE FROM drops WHERE id=?', (ident,))
                    self.emit('world:'+w.name, 'drop_removed', id=ident)
                self.inventory(p)

    def snapshot(self, world):
        return [{'id': p['id'], 'name': p['name'], 'x': p['x'], 'y': p['y'], 'vx': p['vx'], 'vy': p['vy'],
                 'grounded': p['grounded'], 'held': (p['inventory'][p['selected']] or {}).get('id'), 'mining': p['mining']}
                for p in self.players.values() if p['world'] == world]
