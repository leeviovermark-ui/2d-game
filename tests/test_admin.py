"""Server authorization, persistent moderation, and atomic administrator economy."""
from copy import deepcopy
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
from websockets.exceptions import ConnectionClosedOK
from websockets.frames import Close

from server.game import Game
from server.inventory import Rejected, quantity
from server.main import Gateway
from server.storage import Store


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'world.sqlite3'
        self.store = Store(self.path)
        self.store.configure_admins(['Founder'])
        self.owner, self.owner_token = self.store.authenticate('Founder', 'test-password', True)
        self.player, self.player_token = self.store.authenticate('Visitor', 'test-password', True)
        self.other, _ = self.store.authenticate('Trader', 'test-password', True)
        self.now = 100000.
        self.game = Game(self.store, lambda: self.now)
        self.admin = self.game.admin
        for ident in (self.owner, self.player, self.other):
            self.game.join(ident)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def action(self, action, actor=None, **data):
        self.now += 1
        self.game.command(actor or self.owner, {'type': 'admin_action', 'request': uuid.uuid4().hex,
                                               'action': action, **data})

    def test_no_client_role_can_open_or_mutate_administrator_panel(self):
        visitor = self.game.players[self.player]
        visitor.update(admin=True, role='admin')
        with self.assertRaisesRegex(Rejected, 'Administrator access'):
            self.admin.open(visitor, {'admin': True})
        before = deepcopy(visitor['inventory'])
        for action in ('grant', 'ban', 'kick', 'mute', 'teleport', 'unban', 'unmute'):
            with self.assertRaisesRegex(Rejected, 'Administrator access'):
                self.action(action, actor=self.player, target=self.owner, item='dirt', count=99, world='NEXUS')
        self.assertEqual(self.game.players[self.player]['inventory'], before)
        self.assertFalse(self.store.is_admin(self.player))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM audit WHERE kind LIKE "admin_%" AND kind!="admin_bootstrap"').fetchone()[0], 0)

    def test_panel_contains_catalog_and_status_without_authentication_data(self):
        self.admin.open(self.game.players[self.owner])
        destination, message = self.game.outbox[-1]
        self.assertEqual(destination, self.owner)
        self.assertEqual(message['type'], 'admin_panel')
        self.assertIn('dirt', {item['id'] for item in message['items']})
        visitor = next(p for p in message['players'] if p['id'] == self.player)
        self.assertTrue(visitor['online'])
        self.assertFalse(visitor['admin'])
        self.assertFalse(visitor['banned'])
        self.assertNotIn('password', repr(message))
        self.assertNotIn(self.player_token, repr(message))

    def test_grants_negative_unknown_and_full_inventory_are_atomic(self):
        original = deepcopy(self.game.players[self.player]['inventory'])
        for count in (-1, 0, True, 1.5, 10000):
            with self.assertRaises(Rejected):
                self.action('grant', target=self.player, item='dirt', count=count)
        with self.assertRaises(Rejected):
            self.action('grant', target=self.player, item='fake_coin', count=5)
        self.assertEqual(self.game.players[self.player]['inventory'], original)
        full = [{'id': 'dirt', 'n': 99} for _ in range(30)]
        full[0]['n'] = 98
        self.game.players[self.player]['inventory'] = deepcopy(full)
        self.store.save_player(self.game.players[self.player])
        with self.assertRaisesRegex(Rejected, 'Nothing was granted'):
            self.action('grant', target=self.player, item='dirt', count=2)
        self.assertEqual(self.game.players[self.player]['inventory'], full)
        self.assertEqual(self.store.player(self.player)['inventory'], full)
        self.action('grant', target=self.player, item='dirt', count=1)
        self.assertEqual(quantity(self.game.players[self.player]['inventory'], 'dirt'), 2970)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM audit WHERE kind="admin_grant"').fetchone()[0], 1)

    def test_offline_grant_persists_and_target_name_is_case_insensitive(self):
        self.game.leave(self.player)
        self.action('grant', target='visitor', item='crystal', count=7)
        self.assertEqual(quantity(self.store.player(self.player)['inventory'], 'crystal'), 7)
        self.assertEqual(quantity(self.game.join(self.player)['inventory'], 'crystal'), 7)

    def test_replayed_grant_request_cannot_duplicate_items(self):
        before = quantity(self.game.players[self.player]['inventory'], 'dirt')
        packet = {'type': 'admin_action', 'request': uuid.uuid4().hex, 'action': 'grant',
                  'target': self.player, 'item': 'dirt', 'count': 7}
        self.game.command(self.owner, packet)
        with self.assertRaisesRegex(Rejected, 'already processed'):
            self.game.command(self.owner, packet)
        self.assertEqual(quantity(self.game.players[self.player]['inventory'], 'dirt'), before+7)

    def test_ban_revokes_sessions_prevents_login_and_survives_restart(self):
        inventory = deepcopy(self.game.players[self.player]['inventory'])
        self.action('ban', target=self.player, reason='Repeated griefing')
        self.assertNotIn(self.player, self.game.players)
        self.assertTrue(any(dest == self.player and message['type'] == 'disconnect' for dest, message in self.game.outbox))
        with self.assertRaises(Rejected):
            self.store.resume(self.player_token)
        with self.assertRaisesRegex(Rejected, 'banned'):
            self.store.authenticate('Visitor', 'test-password')
        self.store.close()
        self.store = Store(self.path)
        with self.assertRaisesRegex(Rejected, 'banned'):
            self.store.authenticate('visitor', 'test-password')
        self.assertTrue(self.store.is_admin(self.owner))
        self.store.unban_account(self.player)
        ident, _ = self.store.authenticate('Visitor', 'test-password')
        self.assertEqual(ident, self.player)
        self.assertEqual(self.store.player(ident)['inventory'], inventory)

    def test_unban_audited_and_mute_expires_then_unmute(self):
        self.action('ban', target=self.player)
        self.action('unban', target='Visitor')
        self.assertEqual(self.store.authenticate('Visitor', 'test-password')[0], self.player)
        self.action('mute', target=self.player, minutes=2)
        self.assertTrue(self.store.is_muted(self.player, self.now))
        self.assertFalse(self.store.is_muted(self.player, self.now+121))
        self.store.close()
        self.store = Store(self.path)
        self.game.store = self.store
        self.assertTrue(self.store.is_muted(self.player, self.now))
        self.action('unmute', target=self.player)
        self.assertFalse(self.store.is_muted(self.player, self.now))
        kinds = {kind for kind, in self.store.db.execute('SELECT kind FROM audit')}
        self.assertTrue({'admin_ban', 'admin_unban', 'admin_mute', 'admin_unmute'}.issubset(kinds))

    def test_kick_cancels_trade_and_related_invitations_without_item_loss(self):
        a, b = self.game.players[self.player], self.game.players[self.other]
        before_a, before_b = deepcopy(a['inventory']), deepcopy(b['inventory'])
        self.game.command(self.player, {'type': 'trade_request', 'request': uuid.uuid4().hex, 'player': self.other})
        self.game.command(self.other, {'type': 'trade_accept', 'request': uuid.uuid4().hex, 'player': self.player})
        self.game.invites[self.owner] = (self.player, self.now+20)
        self.action('kick', target=self.player)
        self.assertFalse(self.game.trades)
        self.assertIsNone(self.game.players[self.other]['trade'])
        self.assertFalse(self.game.invites)
        self.assertEqual(self.store.player(self.player)['inventory'], before_a)
        self.assertEqual(self.game.players[self.other]['inventory'], before_b)
        self.assertEqual(self.store.resume(self.player_token), self.player)

    def test_grant_during_active_trade_is_rejected(self):
        self.game.command(self.player, {'type': 'trade_request', 'request': uuid.uuid4().hex, 'player': self.other})
        self.game.command(self.other, {'type': 'trade_accept', 'request': uuid.uuid4().hex, 'player': self.player})
        before = deepcopy(self.game.players[self.player]['inventory'])
        with self.assertRaisesRegex(Rejected, 'trade'):
            self.action('grant', target=self.player, item='dirt', count=1)
        self.assertEqual(self.game.players[self.player]['inventory'], before)
        self.assertTrue(self.game.trades)

    def test_unicode_moderation_reason_fits_websocket_close_frame(self):
        self.action('kick', target=self.player, reason='\u2744'*180)
        message = next(message for dest, message in reversed(self.game.outbox)
                       if dest == self.player and message['type'] == 'disconnect')
        self.assertLessEqual(len(message['reason'].encode('utf-8')), 123)

    def test_database_failure_rolls_back_ban_session_and_connected_player(self):
        before = deepcopy(self.game.players[self.player]['inventory'])
        out_len = len(self.game.outbox)
        with patch.object(self.store, 'audit', side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(sqlite3.OperationalError):
                self.action('ban', target=self.player)
        self.assertIn(self.player, self.game.players)
        self.assertEqual(self.game.players[self.player]['inventory'], before)
        self.assertEqual(self.store.resume(self.player_token), self.player)
        self.store.assert_not_banned(self.player)
        self.assertEqual(len(self.game.outbox), out_len)

    def test_protected_administrators_cannot_be_banned_kicked_or_muted(self):
        self.store.configure_admins(['Visitor'])
        for ident in (self.owner, self.player):
            for action in ('ban', 'kick', 'mute'):
                with self.assertRaisesRegex(Rejected, 'Administrators cannot'):
                    self.action(action, target=ident)
        self.assertIn(self.owner, self.game.players)
        self.assertIn(self.player, self.game.players)

    def test_teleport_uses_safe_spawn_and_ignores_supplied_coordinates(self):
        self.store.create_world('ADMIN_HOME', 'snow', seed=44)
        self.action('teleport', target=self.player, world='admin_home', x=float('inf'), y=-9999)
        p = self.game.players[self.player]
        self.assertEqual(p['world'], 'ADMIN_HOME')
        self.assertFalse(self.game.world(p['world']).collides(p['x'], p['y']))
        self.assertEqual(self.store.player(self.player)['world'], 'ADMIN_HOME')
        self.game.leave(self.player)
        self.action('teleport', target=self.player, world='NEXUS')
        self.assertEqual(self.store.player(self.player)['world'], 'NEXUS')
        with self.assertRaises(Rejected):
            self.action('teleport', target=self.player, world='MISSING_WORLD')


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'world.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_loopback_owner_first_existing_account_only(self):
        owner, _ = self.store.authenticate('Owner', 'test-password', True)
        visitor, _ = self.store.authenticate('Visitor', 'test-password', True)
        self.assertFalse(self.store.has_admins())
        self.store.configure_admins(local_owner=True)
        self.assertTrue(self.store.is_admin(owner))
        self.assertFalse(self.store.is_admin(visitor))
        later, _ = self.store.authenticate('Later', 'test-password', True)
        self.assertFalse(self.store.is_admin(later))

    def test_loopback_owner_first_registration_and_no_public_default(self):
        self.store.configure_admins(local_owner=False)
        public, _ = self.store.authenticate('Public', 'test-password', True)
        self.assertFalse(self.store.is_admin(public))
        self.store.configure_admins(local_owner=True)
        self.assertTrue(self.store.is_admin(public))
        with tempfile.TemporaryDirectory() as other_temp:
            local = Store(Path(other_temp)/'local.sqlite3')
            try:
                local.configure_admins(local_owner=True)
                first, _ = local.authenticate('First', 'test-password', True)
                second, _ = local.authenticate('Second', 'test-password', True)
                self.assertTrue(local.is_admin(first))
                self.assertFalse(local.is_admin(second))
            finally:
                local.close()

    def test_named_pending_owner_persists_and_prevents_auto_admin(self):
        self.store.configure_admins(['NamedOwner'], local_owner=True)
        first, _ = self.store.authenticate('First', 'test-password', True)
        self.assertFalse(self.store.is_admin(first))
        self.store.close()
        self.store = Store(self.path)
        owner, _ = self.store.authenticate('namedowner', 'test-password', True)
        self.assertTrue(self.store.is_admin(owner))
        self.assertFalse(self.store.is_admin(first))

    def test_schema_one_migration_preserves_existing_account_and_session(self):
        owner, token = self.store.authenticate('Legacy', 'test-password', True)
        original = self.store.player(owner)
        self.store.close()
        db = sqlite3.connect(self.path)
        db.executescript('DROP TABLE admin_roles; DROP TABLE pending_admins; DROP TABLE moderation; UPDATE schema_version SET version=1;')
        db.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.db.execute('SELECT version FROM schema_version').fetchone()[0], 2)
        self.assertEqual(self.store.resume(token), owner)
        self.assertEqual(self.store.player(owner)['inventory'], original['inventory'])
        self.assertEqual(self.store.load_world('NEXUS').name, 'NEXUS')


class AdminNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'network.sqlite3'
        self.store = Store(self.path)
        self.store.configure_admins(['NetworkAdmin'])
        self.gateway = Gateway(Game(self.store))
        self.server = await serve(self.gateway.connection, '127.0.0.1', 0, max_size=16384)
        self.port = self.server.sockets[0].getsockname()[1]
        self.clients = []
        self.ticks = asyncio.create_task(self.gateway.run_ticks())

    async def asyncTearDown(self):
        for ws in self.clients:
            await ws.close()
        self.server.close()
        await self.server.wait_closed()
        self.ticks.cancel()
        try:
            await self.ticks
        except asyncio.CancelledError:
            pass
        self.store.close()
        self.temp.cleanup()

    async def receive(self, ws, kind):
        async def messages():
            while True:
                data = json.loads(await ws.recv())
                if data['type'] == kind:
                    return data
                if data['type'] == 'error' and kind != 'error':
                    self.fail(data['text'])
        return await asyncio.wait_for(messages(), 4)

    async def auth(self, name):
        ws = await connect('ws://127.0.0.1:'+str(self.port), max_size=2**22)
        self.clients.append(ws)
        await ws.send(json.dumps({'type': 'auth', 'name': name, 'password': 'network-password', 'register': True}))
        return ws, await self.receive(ws, 'welcome')

    async def command(self, ws, action, **data):
        await ws.send(json.dumps({'type': 'admin_action', 'request': uuid.uuid4().hex, 'action': action, **data}))
        return await self.receive(ws, 'ack')

    async def test_menu_grant_mute_unmute_and_unauthorized_packets(self):
        admin, owner = await self.auth('NetworkAdmin')
        visitor, player = await self.auth('NetworkVisitor')
        self.assertTrue(owner['admin'])
        self.assertFalse(player['admin'])
        await admin.send(json.dumps({'type': 'chat', 'text': '/addomen'}))
        panel = await self.receive(admin, 'admin_panel')
        self.assertEqual(len(panel['players']), 2)
        for request in ({'type': 'chat', 'text': '/addomen'},
                        {'type': 'admin_open', 'request': uuid.uuid4().hex, 'admin': True},
                        {'type': 'admin_action', 'request': uuid.uuid4().hex, 'action': 'grant',
                         'target': player['id'], 'item': 'dirt', 'count': 99, 'role': 'admin'}):
            await visitor.send(json.dumps(request))
            self.assertIn('Administrator', (await self.receive(visitor, 'error'))['text'])
        before = quantity(player['slots'], 'dirt')
        await self.command(admin, 'grant', target=player['id'], item='dirt', count=7)
        inventory = await self.receive(visitor, 'inventory')
        self.assertEqual(quantity(inventory['slots'], 'dirt'), before+7)
        await self.command(admin, 'mute', target=player['id'], minutes=1)
        await visitor.send(json.dumps({'type': 'chat', 'text': 'Muted message'}))
        self.assertIn('muted', (await self.receive(visitor, 'error'))['text'].lower())
        await self.command(admin, 'unmute', target=player['id'])
        await visitor.send(json.dumps({'type': 'chat', 'text': 'Chat restored'}))
        self.assertEqual((await self.receive(admin, 'chat'))['text'], 'Chat restored')

    async def test_ban_closes_live_socket_revokes_resume_and_blocks_password_login(self):
        admin, _ = await self.auth('NetworkAdmin')
        visitor, player = await self.auth('NetworkVisitor')
        await self.command(admin, 'ban', target=player['id'], reason='\u2744'*180)
        await asyncio.wait_for(visitor.wait_closed(), 3)
        self.assertEqual(visitor.close_code, 1008)
        self.assertNotIn(player['id'], self.gateway.game.players)
        for credentials in ({'token': player['token']},
                            {'name': 'NetworkVisitor', 'password': 'network-password', 'register': False}):
            ws = await connect('ws://127.0.0.1:'+str(self.port), max_size=2**22)
            self.clients.append(ws)
            await ws.send(json.dumps({'type': 'auth', **credentials}))
            await self.receive(ws, 'error')
        await self.command(admin, 'unban', target=player['id'])
        ws = await connect('ws://127.0.0.1:'+str(self.port), max_size=2**22)
        self.clients.append(ws)
        await ws.send(json.dumps({'type': 'auth', 'name': 'NetworkVisitor', 'password': 'network-password', 'register': False}))
        self.assertEqual((await self.receive(ws, 'welcome'))['id'], player['id'])

    async def test_disconnected_welcome_cannot_leave_a_ghost_player(self):
        class DisconnectedWelcome:
            remote_address = ('127.0.0.1', 30000)

            def __aiter__(self):
                async def request():
                    yield json.dumps({'type': 'auth', 'name': 'GoneBeforeWelcome', 'password': 'network-password', 'register': True})
                return request()

            async def send(self, message):
                raise ConnectionClosedOK(Close(1000, ''), Close(1000, ''), True)

        await self.gateway.connection(DisconnectedWelcome())
        self.assertFalse(self.gateway.connections)
        self.assertFalse(self.gateway.game.players)

    async def test_failed_account_takeover_preserves_existing_connection_and_trade(self):
        admin, owner = await self.auth('NetworkAdmin')
        _, visitor = await self.auth('NetworkVisitor')
        self.ticks.cancel()
        try:
            await self.ticks
        except asyncio.CancelledError:
            pass
        game = self.gateway.game
        game.command(owner['id'], {'type': 'trade_request', 'request': uuid.uuid4().hex, 'player': visitor['id']})
        game.command(visitor['id'], {'type': 'trade_accept', 'request': uuid.uuid4().hex, 'player': owner['id']})
        player = game.players[owner['id']]
        player['input_sequence'] = 99
        player['input_queue'] = [{'axis': 1, 'jump': False, 'jump_held': False, 'seq': 99}]
        input_before = deepcopy(player['input_queue'])
        trade_id = player['trade']
        original_connection = self.gateway.connections[owner['id']]

        class FailedTakeover:
            remote_address = ('127.0.0.1', 30001)

            def __aiter__(self):
                async def request():
                    yield json.dumps({'type': 'auth', 'token': owner['token']})
                return request()

            async def send(self, message):
                raise ConnectionClosedOK(Close(1000, ''), Close(1000, ''), True)

        await self.gateway.connection(FailedTakeover())
        self.assertIs(self.gateway.connections[owner['id']], original_connection)
        self.assertIn(owner['id'], game.players)
        self.assertEqual(game.players[owner['id']]['trade'], trade_id)
        self.assertIn(trade_id, game.trades)
        self.assertEqual(game.players[owner['id']]['input_sequence'], 99)
        self.assertEqual(game.players[owner['id']]['input_queue'], input_before)
        await admin.send(json.dumps({'type': 'chat', 'text': '/addomen'}))
        await self.receive(admin, 'admin_panel')

    async def test_slow_replaced_socket_does_not_delay_new_account_controls(self):
        original_client, owner = await self.auth('NetworkAdmin')
        old = self.gateway.connections[owner['id']]
        close_started, release_close = asyncio.Event(), asyncio.Event()
        original_close = old.close

        async def delayed_close(code=1000, reason=''):
            close_started.set()
            await release_close.wait()
            await original_close(code, reason)

        with patch.object(old, 'close', side_effect=delayed_close):
            replacement = await connect('ws://127.0.0.1:'+str(self.port), max_size=2**22)
            self.clients.append(replacement)
            try:
                await replacement.send(json.dumps({'type': 'auth', 'token': owner['token']}))
                self.assertEqual((await self.receive(replacement, 'welcome'))['id'], owner['id'])
                await asyncio.wait_for(close_started.wait(), 1)
                await replacement.send(json.dumps({'type': 'chat', 'text': '/addomen'}))
                await asyncio.wait_for(self.receive(replacement, 'admin_panel'), 1)
            finally:
                release_close.set()
                await asyncio.wait_for(original_client.wait_closed(), 3)


class AsyncAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'auth.sqlite3'
        self.store = Store(self.path)

    async def asyncTearDown(self):
        self.store.close()
        self.temp.cleanup()

    async def test_concurrent_registration_of_same_name_creates_exactly_one_account(self):
        self.store.configure_admins(local_owner=True)
        results = await asyncio.gather(self.store.authenticate_async('Concurrent', 'test-password', True),
                                       self.store.authenticate_async('concurrent', 'test-password', True),
                                       return_exceptions=True)
        successes = [result for result in results if isinstance(result, tuple)]
        failures = [result for result in results if isinstance(result, Exception)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], Rejected)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM accounts').fetchone()[0], 1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM sessions').fetchone()[0], 1)
        self.assertTrue(self.store.is_admin(successes[0][0]))

    async def test_scrypt_worker_allows_event_loop_progress_and_preserves_sync_hash(self):
        loop = asyncio.get_running_loop()
        loop_thread = threading.get_ident()
        started, released = asyncio.Event(), threading.Event()
        original_digest = self.store._password_digest
        worker_threads = []

        def held_digest(password, salt):
            worker_threads.append(threading.get_ident())
            loop.call_soon_threadsafe(started.set)
            if not released.wait(1):
                raise RuntimeError('Hash blocked the event loop.')
            return original_digest(password, salt)

        with patch.object(self.store, '_password_digest', side_effect=held_digest):
            task = asyncio.create_task(self.store.authenticate_async('Responsive', 'test-password', True))
            try:
                await asyncio.wait_for(started.wait(), 1)
                await asyncio.sleep(0)
                self.assertFalse(task.done())
                self.assertTrue(worker_threads)
                self.assertNotIn(loop_thread, worker_threads)
            finally:
                released.set()
            ident, token = await task
        self.assertEqual(self.store.resume(token), ident)
        self.assertEqual(self.store.authenticate('Responsive', 'test-password')[0], ident)
        self.assertEqual((await self.store.authenticate_async('Responsive', 'test-password'))[0], ident)

    async def test_ban_applied_during_hash_cannot_issue_a_new_session(self):
        ident, token = self.store.authenticate('Moderated', 'test-password', True)
        loop = asyncio.get_running_loop()
        started, released = asyncio.Event(), threading.Event()
        original_digest = self.store._password_digest

        def held_digest(password, salt):
            loop.call_soon_threadsafe(started.set)
            if not released.wait(1):
                raise RuntimeError('Hash blocked the event loop.')
            return original_digest(password, salt)

        with patch.object(self.store, '_password_digest', side_effect=held_digest):
            task = asyncio.create_task(self.store.authenticate_async('Moderated', 'test-password'))
            try:
                await asyncio.wait_for(started.wait(), 1)
                self.store.ban_account(ident, ident, 'Banned during sign in')
            finally:
                released.set()
            with self.assertRaisesRegex(Rejected, 'banned'):
                await task
        with self.assertRaises(Rejected):
            self.store.resume(token)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)

    async def test_cancelled_hash_cannot_register_or_issue_a_session(self):
        loop = asyncio.get_running_loop()
        started, released = asyncio.Event(), threading.Event()
        original_digest = self.store._password_digest

        def held_digest(password, salt):
            loop.call_soon_threadsafe(started.set)
            released.wait(1)
            return original_digest(password, salt)

        with patch.object(self.store, '_password_digest', side_effect=held_digest):
            task = asyncio.create_task(self.store.authenticate_async('Cancelled', 'test-password', True))
            try:
                await asyncio.wait_for(started.wait(), 1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                released.set()
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM accounts').fetchone()[0], 0)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
