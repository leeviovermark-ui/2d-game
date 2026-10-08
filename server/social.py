"""Persistent friendships and a personalized, server-owned world catalogue.

All action handlers run in Game's synchronous request transaction. No account
credentials or inventory are exposed by the social directory.
"""
from collections import Counter
from copy import deepcopy

from .inventory import require
from .world import normalize


MAX_FRIENDS = 100
MAX_REQUESTS = 100


class Social:
    def __init__(self, game):
        self.game = game
        require(not game.store.db.in_transaction, 'Initialize social storage outside a transaction.')
        game.store.db.executescript('''
            CREATE TABLE IF NOT EXISTS friendships(
                low TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                high TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                created REAL NOT NULL, PRIMARY KEY(low,high), CHECK(low < high));
            CREATE INDEX IF NOT EXISTS friendships_high ON friendships(high);
            CREATE TABLE IF NOT EXISTS friend_requests(
                sender TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                recipient TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                created REAL NOT NULL, PRIMARY KEY(sender,recipient), CHECK(sender != recipient));
            CREATE INDEX IF NOT EXISTS friend_requests_recipient ON friend_requests(recipient);
            CREATE TABLE IF NOT EXISTS friend_blocks(
                owner TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                target TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                created REAL NOT NULL, PRIMARY KEY(owner,target), CHECK(owner != target));
            CREATE TABLE IF NOT EXISTS world_favorites(
                account TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                world TEXT NOT NULL REFERENCES worlds(name) ON DELETE CASCADE,
                created REAL NOT NULL, PRIMARY KEY(account,world));
        ''')

    @property
    def db(self):
        return self.game.store.db

    @staticmethod
    def pair(a, b):
        return tuple(sorted((a, b)))

    def friends(self, a, b):
        return self.db.execute('SELECT 1 FROM friendships WHERE low=? AND high=?', self.pair(a, b)).fetchone() is not None

    def blocked(self, a, b):
        """Either explorer's durable block or current chat ignore prevents contact."""
        if self.db.execute('SELECT 1 FROM friend_blocks WHERE (owner=? AND target=?) OR (owner=? AND target=?)',
                           (a, b, b, a)).fetchone():
            return True
        return any(other in self.game.players.get(owner, {}).get('ignore', ()) for owner, other in ((a, b), (b, a)))

    def _count(self, ident):
        return self.db.execute('SELECT count(*) FROM friendships WHERE low=? OR high=?', (ident, ident)).fetchone()[0]

    def _explorer(self, ident, name, requested=None):
        player = self.game.players.get(ident)
        result = {'id': ident, 'name': name, 'online': player is not None,
                  'world': player['world'] if player else ''}
        if requested is not None:
            result['requested'] = requested
        return result

    def state(self, ident):
        rows = self.db.execute('''SELECT a.id,a.username FROM friendships f
            JOIN accounts a ON a.id=CASE WHEN f.low=? THEN f.high ELSE f.low END
            WHERE f.low=? OR f.high=? ORDER BY a.username COLLATE NOCASE LIMIT ?''',
                               (ident, ident, ident, MAX_FRIENDS))
        friends = [{**self._explorer(other, name), 'blocked': self.blocked(ident, other)} for other, name in rows]
        incoming = self.db.execute('''SELECT a.id,a.username,r.created FROM friend_requests r
            JOIN accounts a ON a.id=r.sender WHERE recipient=?
            ORDER BY r.created,a.username COLLATE NOCASE LIMIT ?''', (ident, MAX_REQUESTS))
        outgoing = self.db.execute('''SELECT a.id,a.username,r.created FROM friend_requests r
            JOIN accounts a ON a.id=r.recipient WHERE sender=?
            ORDER BY r.created,a.username COLLATE NOCASE LIMIT ?''', (ident, MAX_REQUESTS))
        blocks = self.db.execute('''SELECT a.id,a.username FROM friend_blocks b
            JOIN accounts a ON a.id=b.target WHERE owner=? ORDER BY a.username COLLATE NOCASE LIMIT ?''',
                                (ident, MAX_FRIENDS))
        return {'friends': friends,
                'incoming': [self._explorer(other, name, created) for other, name, created in incoming],
                'outgoing': [self._explorer(other, name, created) for other, name, created in outgoing],
                'blocked': [self._explorer(other, name) for other, name in blocks], 'max_friends': MAX_FRIENDS}

    def open(self, p, data=None):
        self.game.emit(p['id'], 'social_state', **self.state(p['id']))

    def refresh(self, *idents):
        for ident in set(idents):
            if ident in self.game.players:
                self.open(self.game.players[ident])

    def presence_changed(self, ident):
        """Refresh friends and pending requests only when presence/world changes."""
        related = {ident}
        for low, high in self.db.execute('SELECT low,high FROM friendships WHERE low=? OR high=?', (ident, ident)):
            related.update((low, high))
        for sender, recipient in self.db.execute('SELECT sender,recipient FROM friend_requests WHERE sender=? OR recipient=?',
                                                (ident, ident)):
            related.update((sender, recipient))
        self.refresh(*related)

    def _communicate(self, p, target, chat=True):
        require(not self.blocked(p['id'], target), 'Contact is blocked between these explorers.')
        require(not chat or not self.game.store.is_muted(p['id'], self.game.clock()), 'Your chat is muted by an administrator.')
        self.game.store.assert_not_banned(target)

    def _befriend(self, a, b):
        require(self._count(a) < MAX_FRIENDS and self._count(b) < MAX_FRIENDS, 'An explorer has reached the 100-friend limit.')
        self.db.execute('INSERT INTO friendships VALUES(?,?,?)', (*self.pair(a, b), self.game.clock()))
        self.db.execute('DELETE FROM friend_requests WHERE (sender=? AND recipient=?) OR (sender=? AND recipient=?)', (a, b, b, a))
        self.game.store.audit('friend_accept', [a, b], {})

    def action(self, p, d):
        action = d.get('action')
        require(isinstance(action, str) and action in ('request', 'accept', 'decline', 'remove', 'message', 'join', 'invite',
                                                      'favorite', 'block', 'unblock'), 'Choose a valid social action.')
        if action == 'favorite':
            self._favorite(p, d)
            return
        account = self.game.store.account(d.get('target'))
        target, name = account['id'], account['name']
        require(target != p['id'], 'Choose another explorer.')
        now = self.game.clock()
        if action == 'request':
            self._communicate(p, target)
            require(not self.friends(p['id'], target), 'You are already friends.')
            require(now-p.get('last_friend_request', 0) >= 3, 'Please wait before sending another friend request.')
            if self.db.execute('SELECT 1 FROM friend_requests WHERE sender=? AND recipient=?', (target, p['id'])).fetchone():
                self._befriend(p['id'], target)
                self.game.emit(p['id'], 'notice', text='You and '+name+' are now friends.')
                self.game.emit(target, 'notice', text=p['name']+' accepted your friend request.')
            else:
                require(not self.db.execute('SELECT 1 FROM friend_requests WHERE sender=? AND recipient=?', (p['id'], target)).fetchone(),
                        'A friend request is already pending.')
                require(self._count(p['id']) < MAX_FRIENDS and self._count(target) < MAX_FRIENDS,
                        'An explorer has reached the 100-friend limit.')
                sent = self.db.execute('SELECT count(*) FROM friend_requests WHERE sender=?', (p['id'],)).fetchone()[0]
                received = self.db.execute('SELECT count(*) FROM friend_requests WHERE recipient=?', (target,)).fetchone()[0]
                require(sent < MAX_REQUESTS and received < MAX_REQUESTS, 'Too many pending friend requests.')
                self.db.execute('INSERT INTO friend_requests VALUES(?,?,?)', (p['id'], target, now))
                self.game.emit(p['id'], 'notice', text='Friend request sent to '+name+'.')
                self.game.emit(target, 'notice', text=p['name']+' sent you a friend request.')
            p['last_friend_request'] = now
        elif action == 'accept':
            self._communicate(p, target, chat=False)
            require(self.db.execute('SELECT 1 FROM friend_requests WHERE sender=? AND recipient=?', (target, p['id'])).fetchone(),
                    'That friend request is no longer pending.')
            self._befriend(p['id'], target)
            for ident, other_name in ((p['id'], name), (target, p['name'])):
                self.game.emit(ident, 'notice', text='You and '+other_name+' are now friends.')
        elif action == 'decline':
            # Also allows the sender to withdraw their own outgoing request.
            cursor = self.db.execute('DELETE FROM friend_requests WHERE (sender=? AND recipient=?) OR (sender=? AND recipient=?)',
                                     (p['id'], target, target, p['id']))
            require(cursor.rowcount > 0, 'That friend request is no longer pending.')
        elif action == 'remove':
            require(self.friends(p['id'], target), 'That explorer is not in your friends list.')
            self.db.execute('DELETE FROM friendships WHERE low=? AND high=?', self.pair(p['id'], target))
            self.game.emit(p['id'], 'notice', text=name+' was removed from your friends list.')
        elif action == 'block':
            count = self.db.execute('SELECT count(*) FROM friend_blocks WHERE owner=?', (p['id'],)).fetchone()[0]
            exists = self.db.execute('SELECT 1 FROM friend_blocks WHERE owner=? AND target=?', (p['id'], target)).fetchone()
            require(exists or count < MAX_FRIENDS, 'Your block list is full.')
            self.db.execute('INSERT OR IGNORE INTO friend_blocks VALUES(?,?,?)', (p['id'], target, now))
            self.db.execute('DELETE FROM friend_requests WHERE (sender=? AND recipient=?) OR (sender=? AND recipient=?)',
                            (p['id'], target, target, p['id']))
            trade = self.game.trades.get(p.get('trade'))
            if trade and target in trade['players']:
                self.game.trading.cancel_trade(p, 'Trade cancelled: contact was blocked.')
            # Remove pending trade invitations in either direction as well.
            for recipient, invite in list(self.game.invites.items()):
                if (recipient == p['id'] and invite[0] == target) or (recipient == target and invite[0] == p['id']):
                    del self.game.invites[recipient]
            self.game.emit(p['id'], 'notice', text=name+' is blocked. Unblock them in Friends to restore contact.')
        elif action == 'unblock':
            self.db.execute('DELETE FROM friend_blocks WHERE owner=? AND target=?', (p['id'], target))
            # A durable unblock should also clear an older session-only chat ignore.
            p['ignore'].discard(target)
            self.game.emit(p['id'], 'notice', text=name+' is unblocked.')
        else:
            require(self.friends(p['id'], target), 'Only accepted friends can use this action.')
            self._communicate(p, target, chat=action != 'join')
            other = self.game.players.get(target)
            require(other is not None, 'That friend is offline.')
            if action == 'message':
                text = d.get('text')
                require(isinstance(text, str) and 0 < len(text.strip()) <= 180, 'Messages are limited to 180 characters.')
                text = ''.join(c for c in text.strip() if c.isprintable())
                require(text, 'Write a message first.')
                require(now-p.get('last_social_message', 0) >= .7, 'Please slow down your messages.')
                p['last_social_message'] = now
                self.game.emit(target, 'private_message', id=p['id'], name=p['name'], text=text, sent=False,
                               peer_id=p['id'], peer_name=p['name'], time=now)
                self.game.emit(p['id'], 'private_message', id=p['id'], name=p['name'], text=text, sent=True,
                               peer_id=target, peer_name=name, time=now)
            elif action == 'join':
                # Never accept a client supplied position/world as a friend's location.
                self.game.travel(p, {'world': other['world']})
            elif action == 'invite':
                require(now-p.get('last_world_invite', 0) >= 4, 'Please wait before inviting again.')
                p['last_world_invite'] = now
                self.game.emit(target, 'world_invite', id=p['id'], name=p['name'], world=p['world'],
                               expires=now+120, time=now)
                self.game.emit(p['id'], 'notice', text='World invitation sent to '+name+'.')
            return
        self.refresh(p['id'], target)

    def _favorite(self, p, d):
        name = normalize(d.get('world'))
        require(type(d.get('favorite')) is bool, 'Choose whether to favorite this world.')
        require(self.db.execute('SELECT 1 FROM worlds WHERE name=?', (name,)).fetchone(), 'World not found.')
        if d['favorite']:
            self.db.execute('INSERT OR IGNORE INTO world_favorites VALUES(?,?,?)', (p['id'], name, self.game.clock()))
        else:
            self.db.execute('DELETE FROM world_favorites WHERE account=? AND world=?', (p['id'], name))
        self.directory(p)

    def catalogue(self, p, data=None):
        data = data or {}
        search = data.get('search', '')
        require(isinstance(search, str) and len(search) <= 32, 'World search is limited to 32 characters.')
        biome = data.get('biome', 'all')
        require(biome in ('all', 'forest', 'desert', 'snow'), 'Choose a valid biome filter.')
        sort = data.get('sort', 'featured')
        require(sort in ('featured', 'newest', 'online', 'name', 'favorites'), 'Choose a valid catalogue sort.')
        counts = Counter(player['world'] for player in self.game.players.values())
        favorites = {row[0] for row in self.db.execute('SELECT world FROM world_favorites WHERE account=?', (p['id'],))}
        worlds = []
        for original in self.game.store.directory():
            if biome != 'all' and original['biome'] != biome:
                continue
            if search.strip().casefold() not in (original['name']+' '+original.get('owner_name', '')).casefold():
                continue
            world = deepcopy(original)
            world.update(online=counts[original['name']], favorite=original['name'] in favorites,
                         featured=original['name'] == 'NEXUS', title=original['name'])
            world.setdefault('created', 0)
            worlds.append(world)
        keys = {'featured': lambda w: (not w['featured'], not w['favorite'], -w['online'], -w['created'], w['name']),
                'newest': lambda w: (-w['created'], w['name']),
                'online': lambda w: (-w['online'], not w['featured'], w['name']),
                'name': lambda w: w['name'],
                'favorites': lambda w: (not w['favorite'], not w['featured'], w['name'])}
        worlds.sort(key=keys[sort])
        return worlds

    def directory(self, p, data=None):
        worlds = self.catalogue(p, data)
        self.game.emit(p['id'], 'directory', worlds=worlds, total=len(worlds))

    def broadcast_directory(self):
        for p in list(self.game.players.values()):
            self.directory(p)
