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
from .accounts import Accounts

LOG = logging.getLogger('worldforge')


class Gateway:
    def __init__(self, game):
        self.game = game
        self.accounts = Accounts(game.store)
        self.connections = {}
        self.connection_tokens = {}
        self.connection_accounts = {}
        self.auth_attempts = {}
        self.send_queues = {}
        self.ready_connections = set()
        self.auth_slots = asyncio.Semaphore(4)

    def evict(self, ident):
        """Revoke live authority even when a final position checkpoint fails.

        Valuable inventory changes already commit as part of their own commands.
        A failed disconnect checkpoint must not leave an authenticated ghost.
        """
        try:
            self.game.leave(ident)
        except Exception:
            LOG.exception('Could not save final player checkpoint')
            p = self.game.players.pop(ident, None)
            if p is not None:
                self.game.trading.cancel_trade(p)
                self.game.prune_invites()
                self.game.emit('world:'+p['world'], 'departure', id=ident, name=p['name'])
                try:
                    self.game.social.presence_changed(ident)
                    self.game.social.broadcast_directory()
                except Exception:
                    LOG.exception('Could not publish final player presence')
                self.game.unload()

    def owns_connection(self, ident, ws):
        require(self.connections.get(ident) is ws, 'Connection replaced.')

    def valid_previous_connection(self, ident, ws):
        if ws is None or ws.state != State.OPEN:
            return False
        previous_token = self.connection_tokens.get(ws)
        if previous_token is None:
            return False
        try:
            return self.game.store.resume(previous_token) == ident
        except Rejected:
            return False

    def close_superseded(self, ident, current=None, reason='Account connected elsewhere'):
        # Multiple welcomes can be in flight. Close the entire superseded chain,
        # including a previous socket hidden behind another pending welcome.
        for previous, account in list(self.connection_accounts.items()):
            if account == ident and previous is not current:
                self.enqueue(previous, {'type':'disconnect', 'code':1008, 'reason':reason})

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
        token = None
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
                data = None
                try:
                    data = json.loads(raw)
                    require(isinstance(data, dict) and isinstance(data.get('type'), str), 'Malformed request.')
                    if ident is None:
                        require(data['type'] in ('auth', 'recovery_reset'), 'Sign in before sending game requests.')
                        attempts = [t for t in self.auth_attempts.get(address, []) if t > now-60]
                        require(len(attempts) < 12, 'Too many sign-in attempts. Wait one minute.')
                        self.auth_attempts[address] = attempts + [now]
                        if data['type'] == 'recovery_reset':
                            async with self.auth_slots:
                                result = await self.accounts.handle(None, data)
                            recovered = result.pop('account_id', None)
                            active = self.connections.pop(recovered, None)
                            if active is not None:
                                self.evict(recovered)
                            self.close_superseded(recovered, reason='Password reset. Sign in again.')
                            self.enqueue(ws, json.dumps(result))
                            await self.flush()
                            continue
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
                                         'coyote', 'jump_buffer', 'launch_timer', 'movement_epoch', 'ack_state')
                        previous_movement = {key: p[key] for key in movement_keys}
                        if old and old != ws:
                            self.game.reset_movement(p)
                        ident = candidate
                        self.connections[ident] = ws
                        self.connection_tokens[ws] = token
                        self.connection_accounts[ws] = ident
                        recovery_code = self.game.store.take_registration_recovery(candidate) if data.get('register') else None
                        recovery_expires = self.accounts.info(candidate, token)['recovery_expires'] if recovery_code else None
                        try:
                            await ws.send(json.dumps({'type': 'welcome', 'id': candidate, 'name': p['name'], 'token': token,
                                                      'slots': p['inventory'], 'selected': p['selected'], 'server_time': time.time(),
                                                      'admin': self.game.store.is_admin(candidate), 'player': self.game.public_player(p),
                                                      'recovery_code': recovery_code, 'recovery_expires': recovery_expires,
                                                      'world': self.game.world(p['world']).snapshot()}))
                            self.owns_connection(candidate, ws)
                            require(self.game.store.resume(token) == candidate, 'Sign in again.')
                        except BaseException:
                            if self.connections.get(candidate) is ws and self.valid_previous_connection(candidate, old):
                                self.connections[candidate] = old
                                p.update(previous_movement)
                                ident = None
                            raise
                        self.ready_connections.add(ws)
                        self.game.mechanics.sync(p)
                        self.game.social.presence_changed(ident)
                        self.game.social.broadcast_directory()
                        if old and old != ws:
                            self.game.trading.cancel_trade(p, 'Trade cancelled: account connected elsewhere.')
                        self.close_superseded(ident, current=ws)
                    else:
                        self.owns_connection(ident, ws)
                        if data['type'] != 'input':
                            while action_history and action_history[0] < now-1:
                                action_history.popleft()
                            require(len(action_history) < 30, 'Please slow down your actions.')
                            action_history.append(now)
                        if data['type'].startswith('account_'):
                            if data['type'] in ('account_password', 'account_recovery_rotate', 'account_sessions_clear'):
                                attempts = [t for t in self.auth_attempts.get(address, []) if t > now-60]
                                require(len(attempts) < 12, 'Too many account changes. Wait one minute.')
                                self.auth_attempts[address] = attempts+[now]
                            async with self.auth_slots:
                                result = await self.accounts.handle(ident, data, current_token=token,
                                    authorization_guard=lambda: self.owns_connection(ident, ws))
                            if result['action'] == 'logout':
                                self.connections.pop(ident, None)
                                self.evict(ident)
                            self.enqueue(ws, json.dumps(result))
                            if result['action'] == 'logout':
                                self.enqueue(ws, {'type':'disconnect', 'code':1000, 'reason':'Signed out.'})
                        else:
                            self.game.command(ident, data)
                    await self.flush()
                except (Rejected, ValueError, TypeError, KeyError, OverflowError) as exc:
                    self.enqueue(ws, json.dumps({'type': 'error', 'code': getattr(exc, 'code', 'rejected'), 'request_type': data.get('type') if isinstance(data, dict) else None, 'text': str(exc) if isinstance(exc, Rejected) else 'Malformed request.'}))
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
                self.evict(candidate)
            if ident and self.connections.get(ident) == ws:
                del self.connections[ident]
                self.evict(ident)
                self.close_superseded(ident, reason='Session closed. Sign in again.')
                await self.flush()
            self.ready_connections.discard(ws)
            self.send_queues.pop(ws, None)
            self.connection_tokens.pop(ws, None)
            self.connection_accounts.pop(ws, None)
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
                            if hasattr(self.game, 'mechanics'):
                                self.game.mechanics.persist(p)
                except Exception:
                    LOG.exception('Could not save player checkpoint')
            deadline += 1/60
            if deadline < time.monotonic()-.1:
                deadline = time.monotonic()
            await asyncio.sleep(max(0, deadline-time.monotonic()))


async def http_request(connection, request):
    if request.path == '/version':
        response = connection.respond(HTTPStatus.OK, json.dumps({'release':'stage2', 'protocol':2}))
        response.headers['Content-Type'] = 'application/json'
        return response
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
            gateway.game.mechanics.persist(p)
    store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1', help='Use 0.0.0.0 behind your TLS reverse proxy for remote clients.')
    parser.add_argument('--admin', action='append', default=[], metavar='NAME', help='Grant server administrator access to this account name (repeatable).')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--database', default=str(ROOT / 'data/worldforge.sqlite3'))
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    asyncio.run(main(parser.parse_args()))
