"""WebSocket gateway and fixed-step server loop. Run: python -m server.main."""
import argparse
import asyncio
from collections import deque
import json
import logging
import re
import signal
import time
from http import HTTPStatus
from pathlib import Path
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
from .definitions import ROOT
from .game import Game
from .inventory import Rejected, require
from .storage import Store

LOG = logging.getLogger('worldforge')


class Gateway:
    def __init__(self, game):
        self.game = game
        self.connections = {}
        self.auth_attempts = {}

    async def flush(self):
        pending, self.game.outbox = self.game.outbox, []
        deliveries = {}
        for dest, message in pending:
            ids = [p['id'] for p in self.game.players.values() if 'world:'+p['world'] == dest] if dest.startswith('world:') else [dest]
            encoded = json.dumps(message, separators=(',', ':'))
            for ident in ids:
                if ident in self.connections:
                    deliveries.setdefault(self.connections[ident], []).append(encoded)
        async def deliver(ws, messages):
            try:
                for message in messages:
                    await ws.send(message)
            except ConnectionClosed:
                pass
        # Bound slow consumers; a slow socket must not stall the simulation indefinitely.
        await asyncio.gather(*(asyncio.wait_for(deliver(ws, msgs), 1) for ws, msgs in deliveries.items()), return_exceptions=True)

    async def connection(self, ws):
        ident = None
        history = deque()
        address = ws.remote_address[0] if ws.remote_address else 'unknown'
        try:
            async for raw in ws:
                now = time.monotonic()
                while history and history[0] < now-1:
                    history.popleft()
                history.append(now)
                if len(history) > 80:
                    await ws.close(1008, 'Too many requests')
                    break
                try:
                    data = json.loads(raw)
                    require(isinstance(data, dict) and isinstance(data.get('type'), str), 'Malformed request.')
                    if ident is None:
                        require(data['type'] == 'auth', 'Sign in before sending game requests.')
                        attempts = [t for t in self.auth_attempts.get(address, []) if t > now-60]
                        require(len(attempts) < 12, 'Too many sign-in attempts. Wait one minute.')
                        self.auth_attempts[address] = attempts + [now]
                        if data.get('token'):
                            require(isinstance(data['token'], str) and len(data['token']) <= 128, 'Invalid session.')
                            ident = self.game.store.resume(data['token'])
                            token = data['token']
                        else:
                            name, password = data.get('name'), data.get('password')
                            require(isinstance(name, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{2,19}', name), 'Name: 3–20 letters, numbers, underscores.')
                            require(isinstance(password, str) and 8 <= len(password) <= 128, 'Use a password with 8–128 characters.')
                            require(type(data.get('register')) is bool, 'Choose sign in or create account.')
                            ident, token = self.game.store.authenticate(name, password, data['register'])
                        old = self.connections.get(ident)
                        self.connections[ident] = ws
                        if old and old != ws:
                            self.game.trading.cancel_trade(self.game.players[ident], 'Trade cancelled: account connected elsewhere.')
                            await old.close(1008, 'Account connected elsewhere')
                        p = self.game.join(ident)
                        await ws.send(json.dumps({'type': 'welcome', 'id': ident, 'name': p['name'], 'token': token,
                                                  'slots': p['inventory'], 'selected': p['selected'], 'server_time': time.time(),
                                                  'world': self.game.world(p['world']).snapshot()}))
                    else:
                        require(self.connections.get(ident) == ws, 'Connection replaced.')
                        self.game.command(ident, data)
                    await self.flush()
                except (Rejected, ValueError, TypeError, KeyError, OverflowError) as exc:
                    await ws.send(json.dumps({'type': 'error', 'text': str(exc) if isinstance(exc, Rejected) else 'Malformed request.'}))
                except Exception:
                    LOG.exception('Request failed')
                    await ws.send(json.dumps({'type': 'error', 'text': 'Server could not save the action. No exchange was completed.'}))
        except ConnectionClosed:
            pass
        finally:
            if ident and self.connections.get(ident) == ws:
                del self.connections[ident]
                self.game.leave(ident)
                await self.flush()

    async def run_ticks(self):
        tick = 0
        while True:
            start = time.monotonic()
            self.game.tick(1/30)
            tick += 1
            if tick % 2 == 0:
                for world in {p['world'] for p in self.game.players.values()}:
                    self.game.emit('world:'+world, 'players', players=self.game.snapshot(world), server_time=time.time())
                await self.flush()
            if tick % 60 == 0:
                with self.game.store.transaction():
                    for p in self.game.players.values():
                        self.game.store.save_player(p)
            await asyncio.sleep(max(0, 1/30 - (time.monotonic()-start)))


async def http_request(connection, request):
    if request.path == '/health':
        return connection.respond(HTTPStatus.OK, 'WORLDFORGE authority healthy\n')
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return None
    path = request.path.split('?')[0]
    if path == '/':
        path = '/index.html'
    root = (ROOT / 'build/web').resolve()
    target = (root / path.lstrip('/')).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        return connection.respond(HTTPStatus.NOT_FOUND, 'Export the Godot Web client with scripts/export_web.sh or run godot --path .')
    from websockets.http11 import Response
    from websockets.datastructures import Headers
    import mimetypes
    return Response(200, 'OK', Headers({'Content-Type': mimetypes.guess_type(str(target))[0] or 'application/octet-stream',
                    'Cross-Origin-Opener-Policy': 'same-origin', 'Cross-Origin-Embedder-Policy': 'require-corp',
                    'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-cache'}), target.read_bytes())


async def main(args):
    store = Store(args.database)
    gateway = Gateway(Game(store))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    async with serve(gateway.connection, args.host, args.port, max_size=16384, max_queue=32,
                     ping_interval=20, ping_timeout=20, process_request=http_request, compression=None):
        LOG.info('WORLDFORGE listening on %s:%s (database: %s)', args.host, args.port, args.database)
        ticks = asyncio.create_task(gateway.run_ticks())
        await stop.wait()
        ticks.cancel()
        try:
            await ticks
        except asyncio.CancelledError:
            pass
        for p in list(gateway.game.players.values()):
            gateway.game.store.save_player(p)
    store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1', help='Use 0.0.0.0 behind your TLS reverse proxy for remote clients.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--database', default=str(ROOT / 'data/worldforge.sqlite3'))
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    asyncio.run(main(parser.parse_args()))
