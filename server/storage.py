"""SQLite WAL store: changed tiles, crop timestamps, accounts, and atomic economy."""
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from .inventory import require, starter
from .world import World


def encode(value):
    return json.dumps(value, separators=(',', ':'))


class Store:
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
        require(self.db.execute('SELECT version FROM schema_version').fetchone()[0] == 1, 'Unsupported database schema.')
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

    def authenticate(self, username, password, register=False):
        row = self.db.execute('SELECT id,salt,password FROM accounts WHERE username=? COLLATE NOCASE', (username,)).fetchone()
        if register:
            require(row is None, 'That explorer name is already taken.')
            salt = secrets.token_hex(16)
            digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
            ident = secrets.token_hex(12)
            self.db.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?,?,?,?)',
                            (ident, username, salt, digest, encode(starter()), 'NEXUS', 11.5, 19.4, 0, time.time()))
        else:
            # Always do the expensive hash, including for unknown names.
            salt = row[1] if row else '00'*16
            digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
            require(row is not None and hmac.compare_digest(digest, row[2]), 'Incorrect explorer name or password.')
            ident = row[0]
        token = secrets.token_urlsafe(32)
        self.db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), ident, time.time()+30*86400))
        return ident, token

    def resume(self, token):
        row = self.db.execute('SELECT account FROM sessions WHERE token=? AND expires>?',
                              (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        require(row is not None, 'Session expired. Sign in again.')
        return row[0]

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
        self.db.execute('INSERT OR REPLACE INTO worlds VALUES(?,?)', (meta['name'], encode(meta)))

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
