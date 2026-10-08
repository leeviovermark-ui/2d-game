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
from websockets.protocol import State
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
        self.send_queues = {}
        self.ready_connections = set()
        self.auth_slots = asyncio.Semaphore(4)

    def enqueue(self, ws, message):
        queue = self.send_queues.get(ws)
        if queue is None:
            return
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait({'type': 'disconnect', 'code': 1008, 'reason': 'Connection cannot keep up. Reconnect.'})

    async def flush(self):
        pending, self.game.outbox = self.game.outbox, []
        for dest, message in pending:
            ids = [p['id'] for p in self.game.players.values() if 'world:'+p['world'] == dest] if dest.startswith('world:') else [dest]
            encoded = json.dumps(message, separators=(',', ':')) if message['type'] != 'disconnect' else None
            for ident in ids:
                ws = self.connections.get(ident)
                if ws in self.ready_connections:
                    self.enqueue(ws, message if encoded is None else encoded)

    async def writer(self, ws, queue):
        try:
            while True:
                message = await queue.get()
                if isinstance(message, dict):
                    await ws.close(message['code'], message['reason'])
                    return
                await asyncio.wait_for(ws.send(message), 1)
        except ConnectionClosed:
            pass
        except asyncio.TimeoutError:
            await ws.close(1008, 'Connection cannot keep up. Reconnect.')

    async def connection(self, ws):
        ident = None
        candidate = None
        history = deque()
        queue = asyncio.Queue(maxsize=128)
        self.send_queues[ws] = queue
        writer = asyncio.create_task(self.writer(ws, queue))
        action_history = deque()
        address = ws.remote_address[0] if ws.remote_address else 'unknown'
        try:
            async for raw in ws:
                now = time.monotonic()
                while history and history[0] < now-1:
                    history.popleft()
                history.append(now)
                if len(history) > 150:
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
                            candidate = self.game.store.resume(data['token'])
                            token = data['token']
                        else:
                            name, password = data.get('name'), data.get('password')
                            require(isinstance(name, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{2,19}', name), 'Name: 3–20 letters, numbers, underscores.')
                            require(isinstance(password, str) and 8 <= len(password) <= 128, 'Use a password with 8–128 characters.')
                            require(type(data.get('register')) is bool, 'Choose sign in or create account.')
                            async with self.auth_slots:
                                candidate, token = await self.game.store.authenticate_async(name, password, data['register'])
                        p = self.game.join(candidate)
                        old = self.connections.get(candidate)
                        movement_keys = ('input', 'input_queue', 'input_time', 'input_sequence', 'processed_input',
                                         'coyote', 'jump_buffer', 'movement_epoch', 'ack_state')
                        previous_movement = {key: p[key] for key in movement_keys}
                        if old and old != ws:
                            self.game.reset_movement(p)
                        ident = candidate
                        self.connections[ident] = ws
                        try:
                            await ws.send(json.dumps({'type': 'welcome', 'id': candidate, 'name': p['name'], 'token': token,
                                                      'slots': p['inventory'], 'selected': p['selected'], 'server_time': time.time(),
                                                      'admin': self.game.store.is_admin(candidate), 'player': self.game.public_player(p),
                                                      'world': self.game.world(p['world']).snapshot()}))
                        except BaseException:
                            if old and old.state == State.OPEN:
                                self.connections[candidate] = old
                                p.update(previous_movement)
                                ident = None
                            raise
                        self.ready_connections.add(ws)
                        if old and old != ws:
                            self.game.trading.cancel_trade(p, 'Trade cancelled: account connected elsewhere.')
                            self.enqueue(old, {'type':'disconnect', 'code':1008, 'reason':'Account connected elsewhere'})
                    else:
                        require(self.connections.get(ident) == ws, 'Connection replaced.')
                        if data['type'] != 'input':
                            while action_history and action_history[0] < now-1:
                                action_history.popleft()
                            require(len(action_history) < 30, 'Please slow down your actions.')
                            action_history.append(now)
                        self.game.command(ident, data)
                    await self.flush()
                except (Rejected, ValueError, TypeError, KeyError, OverflowError) as exc:
                    self.enqueue(ws, json.dumps({'type': 'error', 'text': str(exc) if isinstance(exc, Rejected) else 'Malformed request.'}))
                    await self.flush()
                except ConnectionClosed:
                    raise
                except Exception:
                    LOG.exception('Request failed')
                    self.enqueue(ws, json.dumps({'type': 'error', 'text': 'Server could not save the action. No exchange was completed.'}))
        except ConnectionClosed:
            pass
        finally:
            if ident is None and candidate is not None and candidate not in self.connections:
                self.game.leave(candidate)
            if ident and self.connections.get(ident) == ws:
                del self.connections[ident]
                self.game.leave(ident)
                await self.flush()
            self.ready_connections.discard(ws)
            self.send_queues.pop(ws, None)
            writer.cancel()
            try:
                await writer
            except asyncio.CancelledError:
                pass

    async def run_ticks(self):
        tick = 0
        deadline = time.monotonic()
        while True:
            self.game.tick(1/60)
            tick += 1
            if tick % 3 == 0:
                for world in {p['world'] for p in self.game.players.values()}:
                    self.game.emit('world:'+world, 'players', players=self.game.snapshot(world), server_time=time.time())
                await self.flush()
            if tick % 120 == 0:
                try:
                    with self.game.store.transaction():
                        for p in self.game.players.values():
                            self.game.store.save_player(p)
                except Exception:
                    LOG.exception('Could not save player checkpoint')
            deadline += 1/60
            if deadline < time.monotonic()-.1:
                deadline = time.monotonic()
            await asyncio.sleep(max(0, deadline-time.monotonic()))


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


def install_shutdown_handlers(loop, stop):
    """Windows Proactor loops don't implement add_signal_handler."""
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            signal.signal(sig, lambda _signum, _frame: loop.call_soon_threadsafe(stop.set))


async def main(args):
    store = Store(args.database)
    store.configure_admins(getattr(args, 'admin', []), local_owner=args.host in ('127.0.0.1', 'localhost', '::1'))
    gateway = Gateway(Game(store))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    install_shutdown_handlers(loop, stop)
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
    parser.add_argument('--admin', action='append', default=[], metavar='NAME', help='Grant server administrator access to this account name (repeatable).')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--database', default=str(ROOT / 'data/worldforge.sqlite3'))
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    asyncio.run(main(parser.parse_args()))
