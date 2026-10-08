"""Administrator actions share Game's atomic request boundary and server roles."""
from copy import deepcopy
from .definitions import ITEMS
from .inventory import add, integer, require
from .world import normalize


class Admin:
    ACTIONS = ('grant', 'ban', 'unban', 'kick', 'mute', 'unmute', 'teleport')

    def __init__(self, game):
        self.game = game

    def authorized(self, p):
        require(self.game.store.is_admin(p['id']), 'Administrator access required.')
        self.game.store.assert_not_banned(p['id'])

    def state(self):
        players = self.game.store.admin_accounts(self.game.clock())
        for account in players:
            p = self.game.players.get(account['id'])
            account['online'] = p is not None
            if p:
                account['world'] = p['world']
        return {'players': players, 'bans': [p for p in players if p['banned']],
                'items': [{'id': ident, 'name': item['name'], 'category': item['category'], 'stack': item['stack']}
                          for ident, item in ITEMS.items()],
                'actions': list(self.ACTIONS)}

    def open(self, p, data=None):
        self.authorized(p)
        self.game.emit(p['id'], 'admin_panel', **self.state())

    def action(self, p, data):
        self.authorized(p)
        action = data.get('action')
        require(isinstance(action, str) and action in self.ACTIONS, 'Unknown administrator action.')
        account = self.game.store.account(data.get('target', p['id']))
        ident = account['id']
        online = self.game.players.get(ident)
        target = online if online is not None else self.game.store.player(ident)
        details = {'target': ident, 'name': account['name']}
        if action in ('ban', 'kick', 'mute'):
            require(ident != p['id'] and not self.game.store.is_admin(ident),
                    'Administrators cannot moderate themselves or another administrator.')
        reason = data.get('reason', 'Removed by an administrator.')
        require(isinstance(reason, str) and len(reason) <= 180, 'Reason is limited to 180 characters.')
        reason = ''.join(c for c in reason.strip() if c.isprintable()) or 'Removed by an administrator.'
        if action == 'grant':
            item, count = data.get('item'), integer(data.get('count'), 1, 9999)
            require(isinstance(item, str) and item in ITEMS, 'Unknown item.')
            self.game.mutable_inventory(target)
            inv = deepcopy(target['inventory'])
            require(add(inv, item, count) == 0, 'Explorer inventory is full. Nothing was granted.')
            target['inventory'] = inv
            target['mining'] = None
            self.game.inventory(target)
            self.game.emit(ident, 'notice', text='Administrator granted '+str(count)+' '+ITEMS[item]['name']+'.')
            details.update(item=item, count=count)
        elif action == 'ban':
            self.game.store.ban_account(ident, p['id'], reason, self.game.clock())
            self.disconnect(target, 'Banned: '+reason)
            details['reason'] = reason
        elif action == 'unban':
            self.game.store.unban_account(ident)
        elif action == 'kick':
            require(online is not None, 'Explorer is offline.')
            self.disconnect(target, 'Kicked: '+reason)
            details['reason'] = reason
        elif action == 'mute':
            minutes = integer(data.get('minutes', 10), 1, 1440)
            until = self.game.clock()+minutes*60
            self.game.store.mute_account(ident, p['id'], until)
            details.update(minutes=minutes, until=until, reason=reason)
            self.game.emit(ident, 'notice', text='Chat muted for '+str(minutes)+' minutes: '+reason)
        elif action == 'unmute':
            self.game.store.mute_account(ident, p['id'], 0)
            self.game.emit(ident, 'notice', text='Your chat mute was removed.')
        elif action == 'teleport':
            name = normalize(data.get('world'))
            world = self.game.world(name)
            # The world chooses a clear, grounded spawn; coordinates from clients are ignored.
            x, y = world.spawn()
            if online is not None:
                self.game.travel(target, {'world': name})
            else:
                target.update(world=name, x=x, y=y, vx=0., vy=0., mining=None)
                self.game.store.save_player(target)
            details['world'] = name
        self.game.store.audit('admin_'+action, [p['id'], ident], details)
        self.game.emit(p['id'], 'notice', text='Administrator action completed: '+action+' — '+account['name']+'.')
        self.game.emit(p['id'], 'admin_state', **self.state())

    def disconnect(self, target, reason):
        ident = target['id']
        if ident in self.game.players:
            self.game.leave(ident)
        # Retire every invitation involving the removed explorer as well as active trades.
        for recipient, invite in list(self.game.invites.items()):
            if recipient == ident or invite[0] == ident:
                del self.game.invites[recipient]
        # WebSocket close control frames permit only 123 UTF-8 bytes of reason.
        close_reason = reason.encode('utf-8')[:120].decode('utf-8', errors='ignore')
        self.game.emit(ident, 'disconnect', reason=close_reason, code=1008)
