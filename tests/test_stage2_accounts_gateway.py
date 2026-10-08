"""Actual WebSocket account flows, revocation and asynchronous login races."""
import asyncio
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from server.game import Game
from server.main import Gateway
from server.storage import SessionExpired, Store


class AccountsGateway(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'gateway.sqlite3')
        self.gateway = Gateway(Game(self.store))
        self.server = await serve(self.gateway.connection, '127.0.0.1', 0, max_size=16384)
        self.url = 'ws://127.0.0.1:'+str(self.server.sockets[0].getsockname()[1])
        self.clients = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        self.server.close()
        await self.server.wait_closed()
        self.store.close()
        self.temp.cleanup()

    async def client(self):
        ws = await connect(self.url, max_size=2**23)
        self.clients.append(ws)
        return ws

    async def receive(self, ws, kind):
        async def wait():
            while True:
                data = json.loads(await ws.recv())
                if data['type'] == kind:
                    return data
                if data['type'] == 'error' and kind != 'error':
                    self.fail(data['text'])
        return await asyncio.wait_for(wait(), 4)

    async def send(self, ws, kind, **data):
        await ws.send(json.dumps({'type':kind, **data}))

    async def auth(self, name='Explorer', register=True, token=None, password='network-password'):
        ws = await self.client()
        if token:
            await self.send(ws, 'auth', token=token)
        else:
            await self.send(ws, 'auth', name=name, password=password, register=register)
        return ws, await self.receive(ws, 'welcome')

    async def command(self, ws, kind, **data):
        await self.send(ws, kind, request=uuid.uuid4().hex, **data)
        return await self.receive(ws, 'ack')

    async def server_connection(self, client):
        address = client.local_address
        for _ in range(100):
            for server_ws in self.server.connections:
                if server_ws.remote_address == address:
                    return server_ws
            await asyncio.sleep(.001)
        self.fail('Server connection not found.')

    async def test_registration_code_is_delivered_once_and_normal_login_hides_it(self):
        first, welcome = await self.auth()
        self.assertIsInstance(welcome['recovery_code'], str)
        self.assertGreater(welcome['recovery_expires'], welcome['server_time'])
        _, second = await self.auth(name='EXPLORER', register=False)
        self.assertEqual(second['id'], welcome['id'])
        self.assertIsNone(second['recovery_code'])
        await asyncio.wait_for(first.wait_closed(), 2)

    async def test_password_change_retains_current_client_and_revokes_other_saved_login(self):
        previous, before = await self.auth()
        current, welcome = await self.auth(register=False)
        await asyncio.wait_for(previous.wait_closed(), 2)
        await self.send(current, 'account_password', current_password='network-password', new_password='better-password')
        result = await self.receive(current, 'account_result')
        self.assertEqual(result['action'], 'password_change')
        self.assertEqual(self.store.resume(welcome['token']), welcome['id'])
        denied = await self.client()
        await self.send(denied, 'auth', token=before['token'])
        error = await self.receive(denied, 'error')
        self.assertEqual(error['code'], 'session_expired')
        await self.command(current, 'select', slot=3)
        self.assertEqual(self.gateway.game.players[welcome['id']]['selected'], 3)
        await self.send(denied, 'auth', name='explorer', password='better-password', register=False)
        self.assertEqual((await self.receive(denied, 'welcome'))['id'], welcome['id'])

    async def test_recovery_reset_closes_owner_cancels_real_trade_and_requires_new_password(self):
        owner, account = await self.auth()
        friend, other = await self.auth('Friend')
        await self.command(owner, 'trade_request', player=other['id'])
        await self.receive(friend, 'trade_invite')
        await self.command(friend, 'trade_accept', player=account['id'])
        self.assertTrue(self.gateway.game.trades)
        recovery = await self.client()
        await self.send(recovery, 'recovery_reset', name='Explorer', recovery_code=account['recovery_code'], new_password='reset-password')
        result = await self.receive(recovery, 'account_result')
        self.assertEqual(result['action'], 'recovery_reset')
        self.assertNotIn('account_id', result)
        self.assertNotEqual(result['recovery_code'], account['recovery_code'])
        await asyncio.wait_for(owner.wait_closed(), 2)
        self.assertEqual(owner.close_code, 1008)
        self.assertNotIn(account['id'], self.gateway.game.players)
        self.assertNotIn(account['id'], self.gateway.connections)
        self.assertFalse(self.gateway.game.trades)
        await self.receive(friend, 'trade_closed')
        await self.send(recovery, 'auth', token=account['token'])
        self.assertEqual((await self.receive(recovery, 'error'))['code'], 'session_expired')
        await self.send(recovery, 'auth', name='EXPLORER', password='reset-password', register=False)
        self.assertEqual((await self.receive(recovery, 'welcome'))['id'], account['id'])

    async def test_wrong_password_and_recovery_leave_existing_connection_usable(self):
        owner, account = await self.auth()
        await self.send(owner, 'account_password', current_password='wrong-password', new_password='better-password')
        self.assertEqual((await self.receive(owner, 'error'))['request_type'], 'account_password')
        recovery = await self.client()
        await self.send(recovery, 'recovery_reset', name='Explorer', recovery_code='AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA', new_password='reset-password')
        self.assertEqual((await self.receive(recovery, 'error'))['request_type'], 'recovery_reset')
        self.assertEqual(self.store.resume(account['token']), account['id'])
        await self.command(owner, 'select', slot=4)
        self.assertEqual(self.gateway.game.players[account['id']]['selected'], 4)

    async def test_logout_immediately_blocks_queued_world_creation_during_slow_writer(self):
        owner, account = await self.auth()
        server_ws = self.gateway.connections[account['id']]
        started, release = asyncio.Event(), asyncio.Event()
        original = server_ws.send

        async def delayed(message):
            packet = json.loads(message)
            if packet['type'] == 'account_result' and packet['action'] == 'logout':
                started.set()
                await release.wait()
            await original(message)

        with patch.object(server_ws, 'send', side_effect=delayed):
            try:
                await self.send(owner, 'account_logout')
                await asyncio.wait_for(started.wait(), 2)
                self.assertNotIn(account['id'], self.gateway.connections)
                self.assertNotIn(account['id'], self.gateway.game.players)
                await self.send(owner, 'create_world', request=uuid.uuid4().hex, world='AFTERLOGOUT', biome='forest')
                await asyncio.sleep(.03)
                self.assertIsNone(self.store.db.execute('SELECT 1 FROM worlds WHERE name="AFTERLOGOUT"').fetchone())
            finally:
                release.set()
            self.assertEqual((await self.receive(owner, 'account_result'))['action'], 'logout')
            await asyncio.wait_for(owner.wait_closed(), 2)
        with self.assertRaises(SessionExpired):
            self.store.resume(account['token'])

    async def test_failed_logout_checkpoint_still_evicts_and_keeps_committed_inventory(self):
        owner, account = await self.auth()
        await self.command(owner, 'select', slot=3)
        persisted = self.store.player(account['id'])['inventory']
        with patch.object(self.store, 'save_player', side_effect=sqlite3.OperationalError('simulated checkpoint failure')):
            with self.assertLogs('worldforge', level='ERROR'):
                await self.send(owner, 'account_logout')
                self.assertEqual((await self.receive(owner, 'account_result'))['action'], 'logout')
                await asyncio.wait_for(owner.wait_closed(), 2)
        self.assertNotIn(account['id'], self.gateway.game.players)
        self.assertNotIn(account['id'], self.gateway.connections)
        self.assertEqual(self.store.player(account['id'])['inventory'], persisted)
        with self.assertRaises(SessionExpired):
            self.store.resume(account['token'])

    async def test_pending_account_password_cannot_commit_after_same_token_takeover(self):
        owner, account = await self.auth()
        loop = asyncio.get_running_loop()
        started, release = asyncio.Event(), threading.Event()
        original = self.store._password_digest

        def blocked(password, salt):
            loop.call_soon_threadsafe(started.set)
            if not release.wait(2):
                raise RuntimeError('Hash blocked event loop')
            return original(password, salt)

        with patch.object(self.store, '_password_digest', side_effect=blocked):
            try:
                await self.send(owner, 'account_password', current_password='network-password', new_password='attacker-password')
                await asyncio.wait_for(started.wait(), 1)
                replacement, _ = await self.auth(token=account['token'])
                await self.command(replacement, 'select', slot=2)
            finally:
                release.set()
            await asyncio.wait_for(owner.wait_closed(), 3)
        self.assertEqual(self.store.authenticate('Explorer', 'network-password')[0], account['id'])

    async def test_recovery_during_pending_welcome_cannot_restore_revoked_original(self):
        original_client, account = await self.auth()
        pending = await self.client()
        pending_server = await self.server_connection(pending)
        sent, release = asyncio.Event(), asyncio.Event()
        original_send = pending_server.send

        async def blocked(message):
            await original_send(message)
            if json.loads(message)['type'] == 'welcome':
                sent.set()
                await release.wait()

        with patch.object(pending_server, 'send', side_effect=blocked):
            try:
                await self.send(pending, 'auth', token=account['token'])
                await asyncio.wait_for(sent.wait(), 2)
                await self.receive(pending, 'welcome')
                recovery = await self.client()
                await self.send(recovery, 'recovery_reset', name='Explorer', recovery_code=account['recovery_code'], new_password='reset-password')
                await self.receive(recovery, 'account_result')
                await self.send(recovery, 'auth', name='Explorer', password='reset-password', register=False)
                latest = await self.receive(recovery, 'welcome')
                latest_connection = self.gateway.connections[account['id']]
            finally:
                release.set()
            await asyncio.wait_for(pending.wait_closed(), 2)
        self.assertIs(self.gateway.connections[account['id']], latest_connection)
        self.assertEqual(self.store.resume(latest['token']), account['id'])
        await self.command(recovery, 'select', slot=4)
        self.assertEqual(self.gateway.game.players[account['id']]['selected'], 4)
        await asyncio.wait_for(original_client.wait_closed(), 2)
        self.assertEqual(original_client.close_code, 1008)

    async def test_new_takeover_while_welcome_pending_does_not_restore_old_mapping(self):
        old, account = await self.auth()
        pending = await self.client()
        pending_server = await self.server_connection(pending)
        sent, release = asyncio.Event(), asyncio.Event()
        original_send = pending_server.send

        async def blocked(message):
            await original_send(message)
            if json.loads(message)['type'] == 'welcome':
                sent.set()
                await release.wait()

        with patch.object(pending_server, 'send', side_effect=blocked):
            try:
                await self.send(pending, 'auth', token=account['token'])
                await asyncio.wait_for(sent.wait(), 2)
                await self.receive(pending, 'welcome')
                latest, _ = await self.auth(token=account['token'])
                latest_connection = self.gateway.connections[account['id']]
            finally:
                release.set()
            await asyncio.wait_for(pending.wait_closed(), 2)
        self.assertIs(self.gateway.connections[account['id']], latest_connection)
        await asyncio.wait_for(old.wait_closed(), 2)
        self.assertEqual(old.close_code, 1008)
        await self.command(latest, 'select', slot=5)
        self.assertEqual(self.gateway.game.players[account['id']]['selected'], 5)


if __name__ == '__main__':
    unittest.main()
