"""Persistent workshop jobs, equipment, fishing and explorer milestones.

Every mutating handler runs in Game.command's synchronous SQL transaction. Jobs
use wall-clock ready timestamps, so processing survives a server restart without
an in-memory timer or a second reward path.
"""
from copy import deepcopy
import json
import math
import random
import secrets

from .definitions import ITEMS, RECIPES, MOVE
from .inventory import require, integer, add, remove, quantity
from .world import normalize


QUESTS = (
    {'id': 'first_build', 'title': 'A place of your own',
     'description': 'Place 20 blocks, decorations or seeds.', 'event': 'build', 'target': 20,
     'reward': {'fiber': 12, 'wood': 12}, 'points': 25},
    {'id': 'deep_roots', 'title': 'Under the meadow',
     'description': 'Mine 30 tiles with your tools.', 'event': 'gather', 'target': 30,
     'reward': {'coal': 8, 'stone': 20}, 'points': 35},
    {'id': 'green_thumb', 'title': 'The patient gardener',
     'description': 'Harvest 5 ripe crops.', 'event': 'farm', 'target': 5,
     'reward': {'seed': 8, 'fiber': 12}, 'points': 35},
    {'id': 'crafting_hands', 'title': 'Made by hand',
     'description': 'Craft or collect 10 workshop jobs.', 'event': 'craft', 'target': 10,
     'reward': {'iron': 4, 'wood': 15}, 'points': 40},
    {'id': 'new_horizons', 'title': 'Beyond the horizon',
     'description': 'Visit 3 different worlds.', 'event': 'discover', 'target': 3,
     'reward': {'crystal': 2, 'sand': 12}, 'points': 50},
    {'id': 'quiet_waters', 'title': 'Beside quiet waters',
     'description': 'Catch 8 fish or waterside treasures.', 'event': 'fish', 'target': 8,
     'reward': {'fiber': 15, 'grain': 8}, 'points': 40},
)
EMOTES = frozenset(('wave', 'cheer', 'heart', 'dance', 'sit'))
EQUIPMENT_SLOTS = frozenset(('hat', 'back', 'outfit'))


def encoded(value):
    return json.dumps(value, separators=(',', ':'))


class Mechanics:
    MAX_JOBS = 8
    MAX_OWN_JOBS = 4
    FISH_COOLDOWN = 3.
    FISH_ENERGY = 10.

    def __init__(self, game, rng=None):
        self.game = game
        self.store = game.store
        self.rng = rng or random.SystemRandom()
        self.store.db.executescript('''
            CREATE TABLE IF NOT EXISTS machine_jobs(
                id TEXT PRIMARY KEY, world TEXT NOT NULL REFERENCES worlds(name),
                x INTEGER NOT NULL, y INTEGER NOT NULL,
                owner TEXT NOT NULL REFERENCES accounts(id), recipe TEXT NOT NULL,
                output TEXT NOT NULL, amount INTEGER NOT NULL, ready REAL NOT NULL,
                created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS machine_jobs_tile ON machine_jobs(world,x,y,ready);
            CREATE TABLE IF NOT EXISTS player_mechanics(
                account TEXT PRIMARY KEY REFERENCES accounts(id),
                energy REAL NOT NULL DEFAULT 100, equipment TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS player_progress(
                account TEXT NOT NULL REFERENCES accounts(id), event TEXT NOT NULL,
                amount INTEGER NOT NULL, PRIMARY KEY(account,event));
            CREATE TABLE IF NOT EXISTS quest_claims(
                account TEXT NOT NULL REFERENCES accounts(id), quest TEXT NOT NULL,
                claimed REAL NOT NULL, PRIMARY KEY(account,quest));
            CREATE TABLE IF NOT EXISTS progression_visits(
                account TEXT NOT NULL REFERENCES accounts(id), world TEXT NOT NULL REFERENCES worlds(name),
                PRIMARY KEY(account,world));
            CREATE TABLE IF NOT EXISTS fishing_casts(
                account TEXT PRIMARY KEY REFERENCES accounts(id), cast REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS world_portals(
                world TEXT NOT NULL REFERENCES worlds(name), x INTEGER NOT NULL, y INTEGER NOT NULL,
                destination TEXT NOT NULL REFERENCES worlds(name), PRIMARY KEY(world,x,y));
        ''')

    @property
    def clock(self):
        return self.game.clock()

    def join(self, p):
        row = self.store.db.execute('SELECT energy,equipment FROM player_mechanics WHERE account=?', (p['id'],)).fetchone()
        p['energy'] = min(100., max(0., float(row[0]))) if row else 100.
        appearance = json.loads(row[1]) if row else {}
        p['appearance'] = {slot: item for slot, item in appearance.items()
                           if slot in EQUIPMENT_SLOTS and ITEMS.get(item, {}).get('category') == 'apparel'
                           and ITEMS[item].get('slot') == slot}
        p['emote'], p['emote_until'], p['last_emote'] = '', 0., 0.

    def persist(self, p):
        self.store.db.execute('''INSERT INTO player_mechanics VALUES(?,?,?)
            ON CONFLICT(account) DO UPDATE SET energy=excluded.energy,equipment=excluded.equipment''',
            (p['id'], min(100., max(0., p.get('energy', 100.))), encoded(p.get('appearance', {}))))

    def public(self, p):
        return {'appearance': p.get('appearance', {}),
                'emote': p.get('emote', '') if p.get('emote_until', 0) > self.clock else '',
                'emote_until': p.get('emote_until', 0)}

    def vitals(self, p):
        self.game.emit(p['id'], 'vitals', energy=p.get('energy', 100.), max_energy=100)

    def sync(self, p):
        self.vitals(p)
        self.game.emit(p['id'], 'equipment', appearance=p.get('appearance', {}))
        self.progression(p)

    def is_machine(self, item):
        return any(r.get('station') == item and r.get('duration', 0) > 0 for r in RECIPES.values())

    def has_machine(self, world, x, y):
        return self.store.db.execute('SELECT 1 FROM machine_jobs WHERE world=? AND x=? AND y=? LIMIT 1',
                                     (world, x, y)).fetchone() is not None

    def validate_mine(self, w, x, y):
        require(not self.has_machine(w.name, x, y), 'Collect every workshop job before mining this station.')

    def machine_payload(self, p, w, x, y):
        station = w.tile(x, y)
        recipes = [{**r, 'available': all(quantity(p['inventory'], item) >= count
                    for item, count in r['ingredients'].items())}
                   for r in RECIPES.values() if r.get('station') == station]
        rows = self.store.db.execute('''SELECT j.id,j.owner,a.username,j.recipe,j.output,j.amount,j.ready
            FROM machine_jobs j JOIN accounts a ON a.id=j.owner
            WHERE j.world=? AND j.x=? AND j.y=? ORDER BY j.ready,j.created,j.id''', (w.name, x, y))
        jobs = [{'id': ident, 'owner': owner, 'name': name, 'recipe': recipe, 'output': output,
                 'amount': amount, 'ready': ready, 'complete': ready <= self.clock}
                for ident, owner, name, recipe, output, amount, ready in rows]
        return {'world': w.name, 'x': x, 'y': y, 'station': station,
                'name': ITEMS[station]['name'], 'recipes': recipes, 'jobs': jobs, 'server_time': self.clock}

    def machine_open(self, p, d):
        w, x, y = self.game.target(p, d)
        require(self.is_machine(w.tile(x, y)), 'Point at a processing station.')
        self.game.emit(p['id'], 'open_machine', **self.machine_payload(p, w, x, y))

    def machine_start(self, p, d):
        self.game.mutable_inventory(p)
        w, x, y = self.game.target(p, d)
        recipe = RECIPES.get(d.get('recipe'))
        require(recipe is not None, 'Choose a workshop recipe.')
        require(w.tile(x, y) == recipe.get('station'), 'That recipe needs its matching station.')
        count = integer(d.get('count', 1), 1, 20)
        if recipe.get('duration', 0) <= 0:
            self.game.craft(p, {'recipe': recipe['id'], 'count': count})
            self.game.emit(p['id'], 'open_machine', **self.machine_payload(p, w, x, y))
            return
        rows = self.store.db.execute('SELECT owner,ready FROM machine_jobs WHERE world=? AND x=? AND y=?',
                                     (w.name, x, y)).fetchall()
        require(len(rows) < self.MAX_JOBS, 'This workshop queue is full. Collect a completed job.')
        require(sum(owner == p['id'] for owner, _ in rows) < self.MAX_OWN_JOBS,
                'Collect one of your workshop jobs before starting another.')
        inv = deepcopy(p['inventory'])
        for item, amount in recipe['ingredients'].items():
            remove(inv, item, amount * count)
        ready = max([self.clock, *(ready for _, ready in rows)]) + recipe['duration'] * count
        amount = recipe['amount'] * count
        integer(amount, 1, 9999)
        ident = secrets.token_hex(12)
        self.store.db.execute('INSERT INTO machine_jobs VALUES(?,?,?,?,?,?,?,?,?,?)',
                              (ident, w.name, x, y, p['id'], recipe['id'], recipe['output'], amount, ready, self.clock))
        p['inventory'], p['mining'] = inv, None
        self.game.inventory(p)
        self.store.audit('machine_start', [p['id']], {'job': ident, 'recipe': recipe['id'], 'count': count, 'world': w.name})
        self.game.emit(p['id'], 'open_machine', **self.machine_payload(p, w, x, y))
        self.game.emit('world:'+w.name, 'machine_activity', x=x, y=y, station=w.tile(x, y), ready=ready)

    def start_from_recipe(self, p, d):
        recipe = RECIPES.get(d.get('recipe'))
        require(recipe is not None and recipe.get('duration', 0) > 0, 'Choose a workshop recipe.')
        w = self.game.world(p['world'])
        candidates = [(math.hypot(x+.5-p['x'], y+.5-p['y']-.7), x, y)
                      for x in range(max(0, int(p['x'])-5), min(w.width, int(p['x'])+6))
                      for y in range(max(0, int(p['y'])-5), min(w.height, int(p['y'])+6))
                      if w.tile(x, y) == recipe.get('station')
                      and math.hypot(x+.5-p['x'], y+.5-p['y']-.7) <= MOVE['reach']]
        require(candidates, 'Stand near a '+ITEMS[recipe['station']]['name']+'.')
        # Prefer a station with queue capacity; never redirect to an out-of-reach one.
        candidates.sort()
        selected = next(((x, y) for _, x, y in candidates if self.store.db.execute(
            'SELECT COUNT(*) FROM machine_jobs WHERE world=? AND x=? AND y=?', (w.name, x, y)).fetchone()[0] < self.MAX_JOBS),
            (candidates[0][1], candidates[0][2]))
        self.machine_start(p, {**d, 'x': selected[0], 'y': selected[1]})

    def machine_collect(self, p, d):
        self.game.mutable_inventory(p)
        w, x, y = self.game.target(p, d)
        require(self.is_machine(w.tile(x, y)), 'That processing station is no longer here.')
        ident = d.get('job')
        require(isinstance(ident, str) and 1 <= len(ident) <= 64, 'Choose a workshop job.')
        row = self.store.db.execute('''SELECT owner,output,amount,ready FROM machine_jobs
            WHERE id=? AND world=? AND x=? AND y=?''', (ident, w.name, x, y)).fetchone()
        require(row is not None, 'This workshop job was already collected.')
        owner, item, amount, ready = row
        require(owner == p['id'], 'This workshop job belongs to another explorer.')
        require(ready <= self.clock, 'Your workshop job is still processing.')
        inv = deepcopy(p['inventory'])
        require(add(inv, item, amount) == 0, 'Make room for the finished workshop goods.')
        self.store.db.execute('DELETE FROM machine_jobs WHERE id=?', (ident,))
        p['inventory'], p['mining'] = inv, None
        self.game.inventory(p)
        self.event(p, 'craft')
        self.store.audit('machine_collect', [p['id']], {'job': ident, 'item': item, 'amount': amount})
        self.game.emit(p['id'], 'open_machine', **self.machine_payload(p, w, x, y))
        self.game.emit(p['id'], 'notice', text='Collected '+str(amount)+' '+ITEMS[item]['name']+'.')

    def fish(self, p, d):
        self.game.mutable_inventory(p)
        w, x, y = self.game.target(p, d, permission=False)
        require(ITEMS.get(w.tile(x, y), {}).get('fluid', False), 'Point at nearby open water to fish.')
        held = p['inventory'][p['selected']]
        require(held is not None and ITEMS[held['id']].get('fishing', False), 'Hold a fishing rod on your hotbar.')
        row = self.store.db.execute('SELECT "cast" FROM fishing_casts WHERE account=?', (p['id'],)).fetchone()
        require(row is None or self.clock-row[0] >= self.FISH_COOLDOWN, 'Wait for your line to settle before casting again.')
        require(p.get('energy', 100.) >= self.FISH_ENERGY, 'Rest or eat a meal before fishing again.')
        item = 'pearl' if 'pearl' in ITEMS and self.rng.random() < .1 else 'trout'
        require(item in ITEMS, 'Fishing rewards are unavailable on this server.')
        inv = deepcopy(p['inventory'])
        require(add(inv, item, 1) == 0, 'Make room for your catch.')
        self.store.db.execute('''INSERT INTO fishing_casts VALUES(?,?)
            ON CONFLICT(account) DO UPDATE SET "cast"=excluded."cast"''', (p['id'], self.clock))
        p['inventory'], p['mining'] = inv, None
        p['energy'] = max(0., p.get('energy', 100.)-self.FISH_ENERGY)
        self.persist(p)
        self.game.inventory(p)
        self.event(p, 'fish')
        self.vitals(p)
        self.game.emit(p['id'], 'fishing_result', item=item, amount=1, x=x, y=y)
        self.game.emit('world:'+w.name, 'fish_splash', x=x, y=y, player=p['id'])
        self.store.audit('fish', [p['id']], {'item': item, 'world': w.name})

    def use_item(self, p, d):
        self.game.mutable_inventory(p)
        slot = integer(d.get('slot', p['selected']), 0, 29)
        held = p['inventory'][slot]
        require(held is not None, 'Choose a meal to eat.')
        food = ITEMS[held['id']].get('food')
        require(isinstance(food, dict) and food.get('energy', 0) > 0, 'This item is not food.')
        require(p.get('energy', 100.) < 100., 'Your energy is already full. Save this meal for later.')
        inv = deepcopy(p['inventory'])
        item = held['id']
        remove(inv, item, 1)
        p['inventory'], p['mining'] = inv, None
        p['energy'] = min(100., p.get('energy', 100.)+food['energy'])
        self.persist(p)
        self.game.inventory(p)
        self.vitals(p)
        self.game.emit(p['id'], 'notice', text='Enjoyed '+ITEMS[item]['name']+'.')
        self.game.emit('world:'+p['world'], 'consume', player=p['id'], item=item)

    def equip(self, p, d):
        self.game.mutable_inventory(p)
        slot = integer(d.get('slot'), -1, 29)
        inv = deepcopy(p['inventory'])
        appearance = p.get('appearance', {}).copy()
        if slot == -1:
            equipment = d.get('equipment')
            require(equipment in EQUIPMENT_SLOTS, 'Choose an equipment slot.')
            old = appearance.get(equipment)
            require(old is not None, 'Nothing is equipped in that slot.')
            require(add(inv, old, 1) == 0, 'Make room to take off this equipment.')
            del appearance[equipment]
        else:
            held = inv[slot]
            require(held is not None, 'Choose a piece of clothing.')
            item = held['id']
            definition = ITEMS[item]
            equipment = definition.get('slot')
            require(definition['category'] == 'apparel' and equipment in EQUIPMENT_SLOTS, 'That item cannot be worn.')
            # Removing the chosen item first also permits a one-for-one swap with a full backpack.
            remove(inv, item, 1)
            if old := appearance.get(equipment):
                require(add(inv, old, 1) == 0, 'Make room for the equipment you are replacing.')
            appearance[equipment] = item
        p['inventory'], p['appearance'], p['mining'] = inv, appearance, None
        self.persist(p)
        self.game.inventory(p)
        self.game.emit(p['id'], 'equipment', appearance=appearance)
        self.game.emit('world:'+p['world'], 'appearance', player=p['id'], appearance=appearance)

    def emote(self, p, d):
        emote = d.get('emote')
        require(isinstance(emote, str) and emote in EMOTES, 'Choose an available emote.')
        require(self.clock-p.get('last_emote', 0) >= 1.5, 'Give your previous emote a moment to finish.')
        p['emote'], p['emote_until'], p['last_emote'] = emote, self.clock+3., self.clock
        self.game.emit('world:'+p['world'], 'emote', player=p['id'], emote=emote, until=p['emote_until'])

    def event(self, p, kind, amount=1, item=None):
        require(kind in {quest['event'] for quest in QUESTS}, 'Unknown milestone event.')
        integer(amount, 1, 9999)
        if kind == 'discover':
            world = normalize(item or p['world'])
            changed = self.store.db.execute('INSERT OR IGNORE INTO progression_visits VALUES(?,?)', (p['id'], world)).rowcount
            if not changed:
                return
            amount = 1
        self.store.db.execute('''INSERT INTO player_progress VALUES(?,?,?)
            ON CONFLICT(account,event) DO UPDATE SET amount=amount+excluded.amount''', (p['id'], kind, amount))
        self.game.emit(p['id'], 'progress_update', event=kind, amount=amount)

    def progression(self, p, d=None):
        amounts = dict(self.store.db.execute('SELECT event,amount FROM player_progress WHERE account=?', (p['id'],)))
        claimed = {row[0] for row in self.store.db.execute('SELECT quest FROM quest_claims WHERE account=?', (p['id'],))}
        quests = [{**quest, 'current': min(quest['target'], amounts.get(quest['event'], 0)),
                   'status': 'claimed' if quest['id'] in claimed else
                   ('ready' if amounts.get(quest['event'], 0) >= quest['target'] else 'active')}
                  for quest in QUESTS]
        points = sum(q['points'] for q in QUESTS if q['id'] in claimed)
        self.game.emit(p['id'], 'progression', quests=quests, points=points, level=1+points//100)

    def claim_quest(self, p, d):
        self.game.mutable_inventory(p)
        quest = next((q for q in QUESTS if q['id'] == d.get('quest')), None)
        require(quest is not None, 'Choose an explorer milestone.')
        require(not self.store.db.execute('SELECT 1 FROM quest_claims WHERE account=? AND quest=?',
                                         (p['id'], quest['id'])).fetchone(), 'This milestone reward was already claimed.')
        row = self.store.db.execute('SELECT amount FROM player_progress WHERE account=? AND event=?',
                                    (p['id'], quest['event'])).fetchone()
        require(row is not None and row[0] >= quest['target'], 'Complete this milestone before claiming its reward.')
        inv = deepcopy(p['inventory'])
        for item, amount in quest['reward'].items():
            require(add(inv, item, amount) == 0, 'Make room for your milestone reward.')
        self.store.db.execute('INSERT INTO quest_claims VALUES(?,?,?)', (p['id'], quest['id'], self.clock))
        p['inventory'], p['mining'] = inv, None
        self.game.inventory(p)
        self.progression(p)
        self.store.audit('quest_claim', [p['id']], {'quest': quest['id']})
        self.game.emit(p['id'], 'notice', text='Milestone completed: '+quest['title']+'.')

    def portal_config(self, p, d):
        w, x, y = self.game.target(p, d)
        require(w.tile(x, y) == 'portal', 'Point at a travel gate.')
        destination = normalize(d.get('world'))
        require(destination != w.name, 'Choose a different destination world.')
        require(self.store.db.execute('SELECT 1 FROM worlds WHERE name=?', (destination,)).fetchone(),
                'That destination world does not exist.')
        self.store.db.execute('''INSERT INTO world_portals VALUES(?,?,?,?)
            ON CONFLICT(world,x,y) DO UPDATE SET destination=excluded.destination''', (w.name, x, y, destination))
        self.game.emit('world:'+w.name, 'portal', x=x, y=y, destination=destination)
        self.game.emit(p['id'], 'notice', text='Travel gate linked to '+destination+'. Press E to travel.')

    def interact(self, p, d):
        w, x, y = self.game.target(p, d, permission=False)
        item = w.tile(x, y)
        held = p['inventory'][p['selected']]
        if (ITEMS.get(item, {}).get('fluid', False) and held is not None
                and ITEMS[held['id']].get('fishing', False)):
            self.fish(p, d)
            return True
        if self.is_machine(item):
            self.machine_open(p, d)
            return True
        if item == 'portal':
            row = self.store.db.execute('SELECT destination FROM world_portals WHERE world=? AND x=? AND y=?',
                                        (w.name, x, y)).fetchone()
            if row:
                self.game.travel(p, {'world': row[0]})
            else:
                require(w.allowed(p['id']), 'This travel gate has not been linked by its builder yet.')
                self.game.emit(p['id'], 'open_portal', x=x, y=y, world=w.name, destination='', worlds=self.store.directory())
            return True
        return False

    def removed_tile(self, world, x, y):
        # Call in the same transaction as tile removal; a replacement portal starts unlinked.
        self.store.db.execute('DELETE FROM world_portals WHERE world=? AND x=? AND y=?', (world, x, y))
