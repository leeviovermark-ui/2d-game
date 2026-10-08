"""Public bootstrap, explicit proxy trust, and live protocol/rate-limit checks."""
import argparse
import asyncio
import ipaddress
import json
from pathlib import Path
import socket
import signal
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.request import urlopen

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.datastructures import Headers

from server.game import Game
from server.inventory import Rejected
from server.main import Gateway, PROTOCOL, RELEASE, client_address, http_request, install_shutdown_handlers, main, proxy_network
from server.storage import Store


class ProxyAddressTests(unittest.TestCase):
    def address(self, peer, header=None, *, trusted=('127.0.0.1',), kind='CF-Connecting-IP'):
        headers = Headers()
        if header is not None:
            headers[kind] = header
        ws = SimpleNamespace(remote_address=(peer, 1234), request=SimpleNamespace(headers=headers))
        return client_address(ws, tuple(proxy_network(value) for value in trusted), kind)

    def test_untrusted_peer_cannot_supply_its_rate_limit_identity(self):
        self.assertEqual(self.address('203.0.113.50', '198.51.100.21'), '203.0.113.50')
        self.assertEqual(self.address('127.0.0.1', '198.51.100.21', trusted=()), '127.0.0.1')
        self.assertEqual(self.address('203.0.113.50', 'invalid'), '203.0.113.50')

    def test_trusted_cloudflare_header_has_one_canonical_address(self):
        self.assertEqual(self.address('127.0.0.1', '198.51.100.21'), '198.51.100.21')
        self.assertEqual(self.address('127.0.0.1', '2001:0db8:0000:0000::21'), '2001:db8::21')
        self.assertEqual(self.address('::ffff:127.0.0.1', '198.51.100.21'), '198.51.100.21')

    def test_missing_forwarding_header_uses_peer(self):
        self.assertEqual(self.address('127.0.0.1'), '127.0.0.1')

    def test_malformed_trusted_headers_fail_closed(self):
        for header in ('', 'unknown', '198.51.100.21,198.51.100.22', '127.0.0.1:8765',
                       '[2001:db8::21]', 'fe80::1%eth0', '0127.0.0.1', 'a' * 1025):
            with self.subTest(header=header), self.assertRaises(Rejected):
                self.address('127.0.0.1', header)

    def test_duplicate_forwarding_headers_are_rejected(self):
        headers = Headers([('CF-Connecting-IP', '198.51.100.21'),
                           ('CF-Connecting-IP', '198.51.100.22')])
        ws = SimpleNamespace(remote_address=('127.0.0.1', 1234),
                             request=SimpleNamespace(headers=headers))
        with self.assertRaises(Rejected):
            client_address(ws, (proxy_network('127.0.0.1'),), 'CF-Connecting-IP')

    def test_xff_ignores_spoofable_left_entries(self):
        self.assertEqual(self.address('127.0.0.1', '192.0.2.90, 198.51.100.21',
                                      kind='X-Forwarded-For'), '198.51.100.21')
        self.assertEqual(self.address('127.0.0.1', '192.0.2.90, 198.51.100.21, 10.2.0.8',
                                      trusted=('127.0.0.1', '10.0.0.0/8'),
                                      kind='X-Forwarded-For'), '198.51.100.21')

    def test_xff_validates_and_bounds_the_entire_chain(self):
        for header in ('invalid,198.51.100.21', '198.51.100.21,',
                       ','.join(['198.51.100.21'] * 17)):
            with self.subTest(header=header), self.assertRaises(Rejected):
                self.address('127.0.0.1', header, kind='X-Forwarded-For')

    def test_trusted_proxy_config_accepts_addresses_and_cidr_only(self):
        self.assertEqual(proxy_network('127.0.0.1'), ipaddress.ip_network('127.0.0.1/32'))
        self.assertEqual(proxy_network('10.4.0.1/16'), ipaddress.ip_network('10.4.0.0/16'))
        for value in ('localhost', 'https://proxy', '127.0.0.1:8080', '10.0.0.1/99'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                proxy_network(value)


class SupervisedShutdownTests(unittest.TestCase):
    def test_windows_control_break_uses_the_graceful_shutdown_path(self):
        stop = Mock()
        loop = Mock()
        loop.add_signal_handler.side_effect = NotImplementedError
        with patch('server.main.signal.SIGBREAK', 21, create=True), patch('server.main.signal.signal') as install:
            install_shutdown_handlers(loop, stop)
        self.assertEqual([call.args[0] for call in install.call_args_list],
                         [signal.SIGTERM, signal.SIGINT, 21])
        install.call_args_list[-1].args[1](21, None)
        loop.call_soon_threadsafe.assert_called_once_with(stop.set)


class OnlineGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temporary.name) / 'online.sqlite3')
        self.gateway = Gateway(Game(self.store), trusted_proxies=('127.0.0.1',),
                               proxy_ip_header='CF-Connecting-IP')
        self.server = await serve(self.gateway.connection, '127.0.0.1', 0, max_size=16384,
                                  process_request=http_request)
        self.url = 'ws://127.0.0.1:' + str(self.server.sockets[0].getsockname()[1])
        self.clients = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        self.server.close()
        await self.server.wait_closed()
        self.store.close()
        self.temporary.cleanup()

    async def client(self, address='198.51.100.21'):
        ws = await connect(self.url, max_size=2 ** 22,
                           additional_headers={'CF-Connecting-IP': address})
        self.clients.append(ws)
        return ws

    async def reply(self, ws, kind):
        async def receive():
            while True:
                result = json.loads(await ws.recv())
                if result.get('type') == kind:
                    return result
                if result.get('type') == 'error' and kind != 'error':
                    self.fail(result['text'])
        return await asyncio.wait_for(receive(), 4)

    async def signup(self, ws, name, **fields):
        await ws.send(json.dumps({'type': 'auth', 'name': name, 'password': 'online-test-password',
                                  'register': True, **fields}))
        return await self.reply(ws, 'welcome')

    async def test_current_protocol_and_legacy_omission_both_share_one_authority(self):
        first = await self.client()
        second = await self.client('198.51.100.22')
        a = await self.signup(first, 'ProtocolExplorer', protocol=PROTOCOL)
        b = await self.signup(second, 'LegacyExplorer')
        self.assertEqual(a['protocol'], PROTOCOL)
        self.assertEqual(a['release'], RELEASE)
        self.assertEqual({a['id'], b['id']}, set(self.gateway.game.players))
        await first.send(json.dumps({'type': 'chat', 'text': 'One shared authority'}))
        self.assertEqual((await self.reply(second, 'chat'))['text'], 'One shared authority')

    async def test_wrong_protocol_cannot_create_an_account(self):
        ws = await self.client()
        for protocol in (PROTOCOL + 1, -1, True, float(PROTOCOL), str(PROTOCOL), None):
            with self.subTest(protocol=protocol):
                await ws.send(json.dumps({'type': 'auth', 'name': 'IncompatibleExplorer',
                                          'password': 'online-test-password', 'register': True,
                                          'protocol': protocol}))
                error = await self.reply(ws, 'error')
                self.assertIn('different multiplayer version', error['text'])
                self.assertEqual(self.store.db.execute('SELECT count(*) FROM accounts').fetchone()[0], 0)
                self.assertFalse(self.gateway.connections)
        await self.signup(ws, 'CompatibleExplorer', protocol=PROTOCOL)

    async def test_version_is_current_and_never_cached_by_online_proxy(self):
        def request():
            with urlopen(self.url.replace('ws://', 'http://') + '/version', timeout=3) as response:
                return response.status, response.headers['Cache-Control'], json.loads(response.read())
        status, cache, version = await asyncio.to_thread(request)
        self.assertEqual(status, 200)
        self.assertEqual(cache, 'no-store')
        self.assertEqual(version, {'release': RELEASE, 'protocol': PROTOCOL})

    async def exhaust_address(self, ws):
        for _ in range(12):
            await ws.send(json.dumps({'type': 'auth', 'name': '!', 'password': 'online-test-password',
                                      'register': True, 'protocol': PROTOCOL}))
            self.assertIn('Name:', (await self.reply(ws, 'error'))['text'])

    async def test_separate_internet_clients_get_independent_signin_limits(self):
        first = await self.client('198.51.100.21')
        await self.exhaust_address(first)
        second = await self.client('198.51.100.22')
        await self.signup(second, 'UnaffectedExplorer', protocol=PROTOCOL)
        await first.send(json.dumps({'type': 'auth', 'name': 'LimitedExplorer',
                                      'password': 'online-test-password', 'register': True}))
        self.assertIn('Too many sign-in attempts', (await self.reply(first, 'error'))['text'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM accounts').fetchone()[0], 1)
        self.assertEqual(set(self.gateway.auth_attempts), {'198.51.100.21', '198.51.100.22'})

    async def test_untrusted_headers_cannot_bypass_limits(self):
        self.gateway.trusted_proxies = ()
        first = await self.client('198.51.100.21')
        await self.exhaust_address(first)
        second = await self.client('198.51.100.22')
        await second.send(json.dumps({'type': 'auth', 'name': 'SpoofedExplorer',
                                       'password': 'online-test-password', 'register': True}))
        self.assertIn('Too many sign-in attempts', (await self.reply(second, 'error'))['text'])
        self.assertEqual(set(self.gateway.auth_attempts), {'127.0.0.1'})
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM accounts').fetchone()[0], 0)

    async def test_invalid_trusted_header_cannot_create_account(self):
        ws = await self.client('198.51.100.21,198.51.100.22')
        await ws.send(json.dumps({'type': 'auth', 'name': 'InvalidHeaderExplorer',
                                  'password': 'online-test-password', 'register': True}))
        self.assertIn('Invalid proxy client address', (await self.reply(ws, 'error'))['text'])
        self.assertFalse(self.gateway.auth_attempts)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM accounts').fetchone()[0], 0)


class PublicStartupTests(unittest.IsolatedAsyncioTestCase):
    async def startup(self, *, public=False, named_admin=False, existing=False):
        with tempfile.TemporaryDirectory() as temporary, socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            listener.close()
            database = Path(temporary) / 'public.sqlite3'
            if existing:
                store = Store(database)
                store.authenticate('OlderExplorer', 'online-test-password', True)
                store.close()
            args = SimpleNamespace(host='127.0.0.1', port=port, database=database,
                                   public=public, admin=['HostExplorer'] if named_admin else [],
                                   trusted_proxy=['127.0.0.1'], proxy_ip_header='CF-Connecting-IP')
            stops = []
            with patch('server.main.install_shutdown_handlers', side_effect=lambda _loop, stop: stops.append(stop)):
                task = asyncio.create_task(main(args))
                ws = None
                try:
                    for _ in range(80):
                        if task.done():
                            await task
                            self.fail('Authority exited before accepting a connection.')
                        try:
                            ws = await connect(f'ws://127.0.0.1:{port}', max_size=2 ** 22,
                                               additional_headers={'CF-Connecting-IP': '198.51.100.21'})
                            break
                        except OSError:
                            await asyncio.sleep(.025)
                    self.assertIsNotNone(ws, 'Authority did not start.')
                    await ws.send(json.dumps({'type': 'auth', 'name': 'HostExplorer',
                                              'password': 'online-test-password', 'register': True,
                                              'protocol': PROTOCOL}))
                    welcome = json.loads(await asyncio.wait_for(ws.recv(), 4))
                    self.assertEqual(welcome['type'], 'welcome')
                    await ws.close()
                    stops[0].set()
                    await asyncio.wait_for(task, 4)
                    store = Store(database)
                    try:
                        count = store.db.execute('SELECT count(*) FROM admin_roles').fetchone()[0]
                        return welcome['admin'], count
                    finally:
                        store.close()
                finally:
                    if ws is not None:
                        await ws.close()
                    if not task.done():
                        if stops:
                            stops[0].set()
                        await asyncio.wait_for(task, 4)

    async def test_loopback_public_listener_never_grants_first_visitor_admin(self):
        self.assertEqual(await self.startup(public=True), (False, 0))

    async def test_public_mode_does_not_promote_oldest_existing_account(self):
        self.assertEqual(await self.startup(public=True, existing=True), (False, 0))

    async def test_public_mode_preserves_explicit_named_admin(self):
        self.assertEqual(await self.startup(public=True, named_admin=True), (True, 1))

    async def test_default_local_play_retains_owner_bootstrap(self):
        self.assertEqual(await self.startup(), (True, 1))


if __name__ == '__main__':
    unittest.main()
