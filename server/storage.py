"""SQLite WAL store: changed tiles, crop timestamps, accounts, and atomic economy."""
import asyncio
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path
from .inventory import Rejected, require, starter
from .world import World


def encode(value):
    return json.dumps(value, separators=(',', ':'))


class SessionExpired(Rejected):
    """A recognizable rejection lets clients replace a stale saved session."""
    code = 'session_expired'


class Store:
    SESSION_LIMIT = 8

    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
            INSERT INTO schema_version SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM schema_version);
            CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE,
                salt TEXT NOT NULL, password TEXT NOT NULL, inventory TEXT NOT NULL, world TEXT NOT NULL,
                x REAL NOT NULL, y REAL NOT NULL, selected INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(id), expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS worlds(name TEXT PRIMARY KEY, metadata TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tiles(world TEXT NOT NULL REFERENCES worlds(name), x INTEGER, y INTEGER, item TEXT,
                PRIMARY KEY(world,x,y));
            CREATE TABLE IF NOT EXISTS crops(world TEXT REFERENCES worlds(name), x INTEGER, y INTEGER, planted REAL,
                PRIMARY KEY(world,x,y));
            CREATE TABLE IF NOT EXISTS containers(world TEXT REFERENCES worlds(name), x INTEGER, y INTEGER, inventory TEXT,
                PRIMARY KEY(world,x,y));
            CREATE TABLE IF NOT EXISTS drops(id TEXT PRIMARY KEY, world TEXT REFERENCES worlds(name), state TEXT);
            CREATE TABLE IF NOT EXISTS requests(account TEXT, request TEXT, created REAL, PRIMARY KEY(account,request));
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, created REAL, kind TEXT, actors TEXT, details TEXT);
        ''')
        version = self.db.execute('SELECT version FROM schema_version').fetchone()[0]
        require(version in (1, 2), 'Unsupported database schema.')
        # Additive migration: existing worlds, accounts, sessions and economy remain intact.
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS admin_roles(account TEXT PRIMARY KEY REFERENCES accounts(id), created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS pending_admins(username TEXT PRIMARY KEY COLLATE NOCASE);
            CREATE TABLE IF NOT EXISTS moderation(account TEXT PRIMARY KEY REFERENCES accounts(id),
                ban_reason TEXT, ban_by TEXT, banned REAL, muted_until REAL NOT NULL DEFAULT 0, muted_by TEXT);
            CREATE TABLE IF NOT EXISTS accounts_security(account TEXT PRIMARY KEY REFERENCES accounts(id),
                recovery_hash TEXT, recovery_expires REAL NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS sessions_account_expires ON sessions(account,expires);
            CREATE INDEX IF NOT EXISTS sessions_expires ON sessions(expires);
            UPDATE schema_version SET version=2;
        ''')
        self._local_owner_enabled = False
        self._registration_recovery = {}
        self.db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
        self.db.execute('DELETE FROM requests WHERE created < ?', (time.time() - 30*86400,))
        if not self.db.execute('SELECT 1 FROM worlds WHERE name="NEXUS"').fetchone():
            self.create_world('NEXUS', 'forest', seed=71051)

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def remember(self, account, request):
        require(not self.db.execute('SELECT 1 FROM requests WHERE account=? AND request=?', (account, request)).fetchone(),
                'This request was already processed.')
        self.db.execute('INSERT INTO requests VALUES(?,?,?)', (account, request, time.time()))

    @staticmethod
    def _password_digest(password, salt):
        """CPU work only: safe on a worker thread; never touch the SQLite store."""
        return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

    @staticmethod
    def validate_name(username):
        require(isinstance(username, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{2,19}', username),
                'Name: 3–20 letters, numbers, underscores.')
        return username

    @staticmethod
    def validate_password(password):
        require(isinstance(password, str) and 8 <= len(password) <= 128,
                'Use a password with 8–128 characters.')
        try:
            password.encode('utf-8')
        except UnicodeEncodeError:
            require(False, 'Use valid text for your password.')
        return password

    @staticmethod
    def session_hash(token):
        require(isinstance(token, str) and 1 <= len(token) <= 128, 'Invalid session.')
        require(re.fullmatch(r'[A-Za-z0-9_-]+', token), 'Invalid session.')
        return hashlib.sha256(token.encode()).hexdigest()

    def _prepare_authentication(self, username, register):
        self.validate_name(username)
        require(type(register) is bool, 'Choose sign in or create account.')
        row = self.db.execute('SELECT id,salt,password FROM accounts WHERE username=? COLLATE NOCASE', (username,)).fetchone()
        if register:
            require(row is None, 'That explorer name is already taken.')
            salt = secrets.token_hex(16)
        else:
            # Always do the expensive hash, including for unknown names.
            salt = row[1] if row else '00'*16
        return {'username': username, 'register': register, 'row': row, 'salt': salt}

    def _finish_authentication(self, plan, digest):
        # Finalization has no await. Recheck account state after an async hash so
        # concurrent registrations and moderation cannot use a stale lookup.
        with nullcontext() if self.db.in_transaction else self.transaction():
            username, expected = plan['username'], plan['row']
            current = self.db.execute('SELECT id,salt,password FROM accounts WHERE username=? COLLATE NOCASE', (username,)).fetchone()
            if plan['register']:
                require(current is None, 'That explorer name is already taken.')
                ident = secrets.token_hex(12)
                self.db.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?,?,?,?)',
                                (ident, username, plan['salt'], digest, encode(starter()), 'NEXUS', 11.5, 19.4, 0, time.time()))
                # Import here keeps recovery/account settings separate from storage.
                from .accounts import new_recovery_code, recovery_digest, RECOVERY_LIFETIME
                recovery = new_recovery_code()
                self.db.execute('INSERT INTO accounts_security VALUES(?,?,?,0)',
                                (ident, recovery_digest(recovery), time.time()+RECOVERY_LIFETIME))
                pending = self.db.execute('SELECT 1 FROM pending_admins WHERE username=? COLLATE NOCASE', (username,)).fetchone()
                if pending or (self._local_owner_enabled and not self.has_admins()):
                    self._add_admin(ident, 'named_bootstrap' if pending else 'local_owner')
            else:
                require(expected is not None and current is not None and expected[:2] == current[:2]
                        and hmac.compare_digest(digest, current[2]), 'Incorrect explorer name or password.')
                ident = current[0]
            self.assert_not_banned(ident)
            token = secrets.token_urlsafe(32)
            self.db.execute('DELETE FROM sessions WHERE expires <= ?', (time.time(),))
            self.db.execute('INSERT INTO sessions VALUES(?,?,?)',
                            (hashlib.sha256(token.encode()).hexdigest(), ident, time.time()+30*86400))
            # Keep this just-issued token and the seven newest other sessions.
            # This bounds saved bearer credentials even after repeated sign-ins.
            self.db.execute('''DELETE FROM sessions WHERE account=? AND token!=? AND token NOT IN
                (SELECT token FROM sessions WHERE account=? AND token!=? ORDER BY expires DESC,token LIMIT ?)''',
                (ident, self.session_hash(token), ident, self.session_hash(token), self.SESSION_LIMIT-1))
        if plan['register']:
            # Delivery only once, after commit. Codes are never persisted in plaintext.
            if len(self._registration_recovery) >= 128:
                self._registration_recovery.pop(next(iter(self._registration_recovery)))
            self._registration_recovery[ident] = recovery
        return ident, token

    def authenticate(self, username, password, register=False):
        self.validate_password(password)
        plan = self._prepare_authentication(username, register)
        return self._finish_authentication(plan, self._password_digest(password, plan['salt']))

    async def authenticate_async(self, username, password, register=False):
        self.validate_password(password)
        plan = self._prepare_authentication(username, register)
        digest = await asyncio.to_thread(self._password_digest, password, plan['salt'])
        return self._finish_authentication(plan, digest)

    def resume(self, token):
        row = self.db.execute('SELECT account FROM sessions WHERE token=? AND expires>?',
                              (self.session_hash(token), time.time())).fetchone()
        if row is None:
            raise SessionExpired('Session expired. Sign in again.')
        self.assert_not_banned(row[0])
        return row[0]

    def take_registration_recovery(self, ident):
        return self._registration_recovery.pop(ident, None)

    def revoke_session(self, ident, token):
        self.db.execute('DELETE FROM sessions WHERE token=? AND account=?', (self.session_hash(token), ident))

    def has_admins(self):
        return bool(self.db.execute('SELECT 1 FROM admin_roles LIMIT 1').fetchone()
                    or self.db.execute('SELECT 1 FROM pending_admins LIMIT 1').fetchone())

    def _add_admin(self, ident, source):
        if not self.is_admin(ident):
            self.db.execute('INSERT INTO admin_roles VALUES(?,?)', (ident, time.time()))
            self.audit('admin_bootstrap', [ident], {'source': source})

    def configure_admins(self, names=(), local_owner=False):
        """Explicit server bootstrap; never derive authorization from client packets.

        The caller enables local_owner only for a loopback listener. Named admins
        persist, including a name whose account has not yet been registered.
        """
        import re
        require(type(local_owner) is bool, 'Invalid server owner configuration.')
        require(isinstance(names, (list, tuple)), 'Invalid admin names.')
        require(all(isinstance(name, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{2,19}', name)
                    for name in names), 'Admin names: 3–20 letters, numbers, underscores.')
        with self.transaction():
            for name in names:
                self.db.execute('INSERT OR IGNORE INTO pending_admins VALUES(?)', (name,))
                row = self.db.execute('SELECT id FROM accounts WHERE username=? COLLATE NOCASE', (name,)).fetchone()
                if row:
                    self._add_admin(row[0], 'named_bootstrap')
            if local_owner and not self.has_admins():
                row = self.db.execute('SELECT id FROM accounts ORDER BY created,id LIMIT 1').fetchone()
                if row:
                    self._add_admin(row[0], 'local_owner')
        self._local_owner_enabled = local_owner

    def is_admin(self, ident):
        return self.db.execute('SELECT 1 FROM admin_roles WHERE account=?', (ident,)).fetchone() is not None

    def assert_not_banned(self, ident):
        row = self.db.execute('SELECT ban_reason FROM moderation WHERE account=?', (ident,)).fetchone()
        require(row is None or row[0] is None, 'This account is banned from this server.')

    def is_muted(self, ident, now=None):
        row = self.db.execute('SELECT muted_until FROM moderation WHERE account=?', (ident,)).fetchone()
        return row is not None and row[0] > (time.time() if now is None else now)

    def account(self, target):
        require(isinstance(target, str) and 1 <= len(target) <= 64, 'Choose an explorer.')
        # ID wins over a username; usernames are case-insensitive.
        row = self.db.execute('SELECT id,username FROM accounts WHERE id=?', (target,)).fetchone()
        if row is None:
            row = self.db.execute('SELECT id,username FROM accounts WHERE username=? COLLATE NOCASE', (target,)).fetchone()
        require(row is not None, 'Explorer not found.')
        return {'id': row[0], 'name': row[1]}

    def admin_accounts(self, now=None):
        now = time.time() if now is None else now
        rows = self.db.execute('''SELECT a.id,a.username,a.world,r.account,m.ban_reason,m.muted_until
            FROM accounts a LEFT JOIN admin_roles r ON r.account=a.id
            LEFT JOIN moderation m ON m.account=a.id ORDER BY a.username COLLATE NOCASE LIMIT 200''')
        return [{'id': ident, 'name': name, 'world': world, 'admin': role is not None,
                 'banned': reason is not None, 'ban_reason': reason or '',
                 'muted': (until or 0) > now, 'muted_until': until or 0}
                for ident, name, world, role, reason, until in rows]

    def ban_account(self, ident, actor, reason, now=None):
        self.db.execute('''INSERT INTO moderation(account,ban_reason,ban_by,banned) VALUES(?,?,?,?)
            ON CONFLICT(account) DO UPDATE SET ban_reason=excluded.ban_reason,ban_by=excluded.ban_by,banned=excluded.banned''',
            (ident, reason, actor, time.time() if now is None else now))
        self.db.execute('DELETE FROM sessions WHERE account=?', (ident,))

    def unban_account(self, ident):
        self.db.execute('UPDATE moderation SET ban_reason=NULL,ban_by=NULL,banned=NULL WHERE account=?', (ident,))

    def mute_account(self, ident, actor, until):
        self.db.execute('''INSERT INTO moderation(account,muted_until,muted_by) VALUES(?,?,?)
            ON CONFLICT(account) DO UPDATE SET muted_until=excluded.muted_until,muted_by=excluded.muted_by''',
            (ident, until, actor))

    def player(self, ident):
        row = self.db.execute('SELECT username,inventory,world,x,y,selected FROM accounts WHERE id=?', (ident,)).fetchone()
        return {'id': ident, 'name': row[0], 'inventory': json.loads(row[1]), 'world': row[2],
                'x': row[3], 'y': row[4], 'selected': row[5], 'vx': 0., 'vy': 0., 'grounded': False,
                'input': {'axis': 0, 'jump': False}, 'input_time': 0., 'mining': None, 'trade': None,
                'last_chat': 0., 'last_action': 0., 'ignore': set()}

    def save_player(self, player):
        self.db.execute('UPDATE accounts SET inventory=?,world=?,x=?,y=?,selected=? WHERE id=?',
                        (encode(player['inventory']), player['world'], player['x'], player['y'], player['selected'], player['id']))

    def create_world(self, name, biome, seed=None):
        require(not self.db.execute('SELECT 1 FROM worlds WHERE name=?', (name,)).fetchone(), 'That world already exists.')
        meta = {'name': name, 'seed': seed if seed is not None else secrets.randbelow(2**31), 'biome': biome,
                'owner': None, 'owner_name': '', 'builders': [], 'builder_names': [], 'guest_build': True,
                'created': time.time(), 'spawn': [11.5, 19.4], 'width': 144, 'height': 56}
        self.save_meta(meta)
        return World(meta)

    def save_meta(self, meta):
        # REPLACE deletes the world row before inserting: this would cascade-delete
        # favorites and can violate references from saved tiles or containers.
        self.db.execute('''INSERT INTO worlds(name,metadata) VALUES(?,?)
            ON CONFLICT(name) DO UPDATE SET metadata=excluded.metadata''', (meta['name'], encode(meta)))

    def load_world(self, name):
        row = self.db.execute('SELECT metadata FROM worlds WHERE name=?', (name,)).fetchone()
        require(row is not None, 'World not found. Create it first.')
        crops = list(self.db.execute('SELECT x,y,planted FROM crops WHERE world=?', (name,)))
        containers = [(x, y, json.loads(inv)) for x, y, inv in self.db.execute('SELECT x,y,inventory FROM containers WHERE world=?', (name,))]
        drops = [json.loads(s) for s, in self.db.execute('SELECT state FROM drops WHERE world=?', (name,))]
        deltas = list(self.db.execute('SELECT x,y,item FROM tiles WHERE world=?', (name,)))
        return World(json.loads(row[0]), deltas, crops, containers, drops)

    def tile(self, world, x, y, item):
        self.db.execute('INSERT OR REPLACE INTO tiles VALUES(?,?,?,?)', (world, x, y, item))

    def crop(self, world, x, y, planted=None):
        if planted is None:
            self.db.execute('DELETE FROM crops WHERE world=? AND x=? AND y=?', (world, x, y))
        else:
            self.db.execute('INSERT OR REPLACE INTO crops VALUES(?,?,?,?)', (world, x, y, planted))

    def container(self, world, x, y, inv):
        self.db.execute('INSERT OR REPLACE INTO containers VALUES(?,?,?,?)', (world, x, y, encode(inv)))

    def drop(self, world, drop):
        self.db.execute('INSERT OR REPLACE INTO drops VALUES(?,?,?)', (drop['id'], world, encode(drop)))

    def audit(self, kind, actors, details):
        self.db.execute('INSERT INTO audit(created,kind,actors,details) VALUES(?,?,?,?)',
                        (time.time(), kind, encode(actors), encode(details)))

    def directory(self):
        return [json.loads(row[0]) for row in self.db.execute('SELECT metadata FROM worlds ORDER BY name LIMIT 100')]

    def close(self):
        self.db.close()
