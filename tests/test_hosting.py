"""Real shared LAN authority, launcher shutdown, and tunnel download integrity."""
import asyncio
import hashlib
import io
import json
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import ProxyHandler, build_opener
from urllib.error import HTTPError
from urllib.parse import quote

from websockets.asyncio.client import connect
from scripts import host_online, join_lan, play
from server.storage import Store


def available_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


async def receive(ws, kind, predicate=lambda packet: True):
    async def wait():
        while True:
            packet = json.loads(await ws.recv())
            if packet['type'] == 'error':
                raise AssertionError(packet['text'])
            if packet['type'] == kind and predicate(packet):
                return packet
    return await asyncio.wait_for(wait(), 5)


class HostingFunctionalTests(unittest.IsolatedAsyncioTestCase):
    async def test_lan_launcher_serves_one_authority_to_two_interface_clients(self):
        addresses = play.lan_addresses()
        if not addresses:
            self.skipTest('No usable private IPv4 interface on this test machine.')
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'lan.sqlite3'
            port = available_port()
            worker = subprocess.Popen([sys.executable, str(play.ROOT / 'scripts/play.py'),
                                       '--host', '0.0.0.0', '--port', str(port), '--database', str(database),
                                       '--no-browser'], cwd=play.ROOT,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                local = f'http://127.0.0.1:{port}'
                for _ in range(100):
                    self.assertIsNone(worker.poll(), 'LAN launcher stopped during startup.')
                    if await asyncio.to_thread(play.health_ready, local):
                        break
                    await asyncio.sleep(.05)
                self.assertTrue(await asyncio.to_thread(play.compatible_server, local))
                remote = f'http://{addresses[0]}:{port}'
                opener = build_opener(ProxyHandler({}))
                def fetch_remote():
                    with opener.open(remote + '/', timeout=3) as response:
                        return response.status, response.read(30000)
                status, html = await asyncio.to_thread(fetch_remote)
                self.assertEqual(status, 200)
                self.assertIn(b'WORLDFORGE', html)
                async with connect(f'ws://127.0.0.1:{port}', max_size=2**22, proxy=None) as first, \
                           connect(f'ws://{addresses[0]}:{port}', max_size=2**22, proxy=None) as second:
                    for ws, name in ((first, 'LanHost'), (second, 'LanFriend')):
                        await ws.send(json.dumps({'type': 'auth', 'name': name,
                                                  'password': 'test-lan-password', 'register': True,
                                                  'protocol': play.PROTOCOL}))
                    host = await receive(first, 'welcome')
                    friend = await receive(second, 'welcome')
                    self.assertNotEqual(host['id'], friend['id'])
                    players = await receive(first, 'players', lambda packet: len(packet['players']) == 2)
                    self.assertEqual({player['id'] for player in players['players']}, {host['id'], friend['id']})
                    await first.send(json.dumps({'type': 'select', 'slot': 1, 'request': 'lan-select'}))
                    await receive(first, 'ack')
                    await first.send(json.dumps({'type': 'place', 'x': 12, 'y': 20, 'request': 'lan-place'}))
                    await receive(first, 'ack')
                    delta = await receive(second, 'tile', lambda packet: packet['x'] == 12 and packet['y'] == 20)
                    self.assertEqual(delta['item'], 'dirt')
                    await second.send(json.dumps({'type': 'chat', 'text': 'We share this server.'}))
                    message = await receive(first, 'chat', lambda packet: packet['text'] == 'We share this server.')
                    self.assertEqual(message['name'], 'LanFriend')
                await asyncio.to_thread(host_online.stop_process, worker, 'the test host')
                self.assertEqual(worker.returncode, 0)
                output = worker.stdout.read()
                self.assertIn('Friends on your Wi-Fi:', output)
                self.assertIn('Friends double-click Join-WORLDFORGE-LAN.bat', output)
                store = Store(database)
                try:
                    self.assertEqual(store.resume(host['token']), host['id'])
                    self.assertEqual(store.resume(friend['token']), friend['id'])
                    self.assertEqual(store.db.execute(
                        'SELECT item FROM tiles WHERE world=? AND x=? AND y=?', ('NEXUS', 12, 20)).fetchone()[0], 'dirt')
                finally:
                    store.close()
            finally:
                if worker.poll() is None:
                    await asyncio.to_thread(host_online.stop_process, worker, 'the test host')
                worker.stdout.close()

    async def test_existing_local_server_is_not_mistaken_for_a_lan_host(self):
        with tempfile.TemporaryDirectory() as directory:
            port = available_port()
            worker = subprocess.Popen([sys.executable, '-m', 'server.main', '--port', str(port),
                                       '--database', str(Path(directory) / 'local.sqlite3')], cwd=play.ROOT,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    if await asyncio.to_thread(play.health_ready, f'http://127.0.0.1:{port}'):
                        break
                    await asyncio.sleep(.05)
                result = await asyncio.to_thread(subprocess.run,
                    [sys.executable, str(play.ROOT / 'scripts/play.py'), '--host', '0.0.0.0',
                     '--port', str(port), '--no-browser'], cwd=play.ROOT, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 1)
                self.assertIn('bind to your Wi-Fi interface', result.stdout)
                self.assertIsNone(worker.poll())
            finally:
                await asyncio.to_thread(host_online.stop_process, worker, 'the test server')


class JoinLauncherTests(unittest.TestCase):
    def test_accepts_host_addresses_and_rejects_targets_outside_private_lan(self):
        for address, expected in (
            ('http://192.168.1.20:8765', 'ws://192.168.1.20:8765'),
            (' 192.168.1.20:8766 ', 'ws://192.168.1.20:8766'),
            ('ws://10.2.3.4:8765/', 'ws://10.2.3.4:8765'),
            ('http://172.31.3.4/index.html', 'ws://172.31.3.4:8765'),
        ):
            with self.subTest(address=address):
                self.assertEqual(join_lan.server_address(address), expected)
        for address in ('http://127.0.0.1:8765', 'http://8.8.8.8:8765',
                        'http://169.254.1.1:8765', 'http://172.32.1.2:8765',
                        'http://localhost:8765', 'https://192.168.1.20:8765',
                        'http://user:password@192.168.1.20:8765',
                        'http://192.168.1.20:8765?token=secret', 'http://192.168.1.20:8765#secret',
                        'http://192.168.1.20:8765/other.html', 'http://192.168.1.20:70000',
                        'http://192.168.1.20:0', 'http://192.168.1.20:',
                        'http://[::1]:8765', 'http://192.168.1.20.invalid:8765', ''):
            with self.subTest(address=address):
                with self.assertRaises(ValueError):
                    join_lan.server_address(address)

    def test_static_client_headers_and_traversal_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            web = directory / 'web'
            web.mkdir()
            (web / 'index.html').write_text('<title>WORLDFORGE</title>')
            (web / 'index.wasm').write_bytes(b'wasm-fixture')
            (directory / 'private-save.sqlite3').write_text('private saves must not be served')
            server = join_lan.static_server(0, web)
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
            thread.start()
            origin = f'http://127.0.0.1:{server.server_address[1]}'
            opener = build_opener(ProxyHandler({}))
            try:
                with opener.open(origin + '/?join=ws%3A%2F%2F192.168.1.20%3A8765', timeout=2) as response:
                    self.assertIn(b'WORLDFORGE', response.read())
                    self.assertEqual(response.headers['Cross-Origin-Opener-Policy'], 'same-origin')
                    self.assertEqual(response.headers['Cross-Origin-Embedder-Policy'], 'require-corp')
                    self.assertEqual(response.headers['Cache-Control'], 'no-cache')
                with opener.open(origin + '/index.wasm', timeout=2) as response:
                    self.assertEqual(response.headers['Content-Type'], 'application/wasm')
                    self.assertEqual(response.read(), b'wasm-fixture')
                for path in ('/../private-save.sqlite3', '/%2e%2e/private-save.sqlite3', '/%2e%2e%2fprivate-save.sqlite3'):
                    with self.subTest(path=path), self.assertRaises(HTTPError) as failure:
                        opener.open(origin + path, timeout=2)
                    self.assertEqual(failure.exception.code, 404)
                if sys.platform != 'win32':
                    (web / 'outside.txt').symlink_to(directory / 'private-save.sqlite3')
                    (web / 'index.html').unlink()
                    (web / 'index.html').symlink_to(directory / 'private-save.sqlite3')
                    for path in ('/outside.txt', '/'):
                        with self.subTest(path=path), self.assertRaises(HTTPError) as failure:
                            opener.open(origin + path, timeout=2)
                        self.assertEqual(failure.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    @unittest.skipIf(sys.platform == 'win32', 'POSIX subprocess fixture uses SIGINT to close the foreground client.')
    def test_actual_join_launcher_runs_without_installed_dependencies_or_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            port = available_port()
            worker = subprocess.Popen([sys.executable, '-S', str(play.ROOT / 'scripts/join_lan.py'),
                                       '--server', 'http://192.168.1.20:8765', '--port', str(port), '--no-browser'],
                                      cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            origin = f'http://127.0.0.1:{port}'
            opener = build_opener(ProxyHandler({}))
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    self.assertIsNone(worker.poll(), 'Join launcher stopped before serving its local client.')
                    try:
                        with opener.open(origin + '/?join=' + quote('ws://192.168.1.20:8765', safe=''), timeout=.3) as response:
                            html = response.read(100000)
                            self.assertIn(b'WORLDFORGE', html)
                            break
                    except OSError:
                        time.sleep(.025)
                else:
                    self.fail('Join launcher did not serve its local client.')
                with self.assertRaises(HTTPError) as failure:
                    opener.open(origin + '/health', timeout=1)
                self.assertEqual(failure.exception.code, 404)
                self.assertEqual(list(Path(directory).iterdir()), [])
                worker.send_signal(signal.SIGINT)
                worker.wait(timeout=5)
                self.assertEqual(worker.returncode, 0)
                output = worker.stdout.read()
                self.assertIn('serves only the browser client', output)
                self.assertNotIn('Starting WORLDFORGE', output)
            finally:
                if worker.poll() is None:
                    worker.terminate()
                    worker.wait(timeout=5)
                worker.stdout.close()


class TunnelIntegrityTests(unittest.TestCase):
    def response(self, contents):
        stream = io.BytesIO(contents)
        stream.status = 200
        return stream

    def test_wrong_digest_cannot_replace_or_execute_cached_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / '.tools/cloudflared' / host_online.CLOUDFLARED_VERSION / 'helper'
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b'corrupt old download')
            expected = hashlib.sha256(b'verified official helper').hexdigest()
            with patch.object(host_online, 'ROOT', root), \
                 patch.object(host_online, 'CLOUDFLARED_BINARIES', {'Linux': ('helper', expected)}), \
                 patch('scripts.host_online.platform.system', return_value='Linux'), \
                 patch('scripts.host_online.platform.machine', return_value='x86_64'), \
                 patch('scripts.host_online.urlopen', return_value=self.response(b'tampered download')):
                with self.assertRaisesRegex(RuntimeError, 'checksum'):
                    host_online.cloudflared_binary()
            self.assertEqual(destination.read_bytes(), b'corrupt old download')
            self.assertEqual(list(destination.parent.glob('.download-*')), [])

    def test_verified_download_replaces_corrupt_cache_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contents = b'verified official helper'
            expected = hashlib.sha256(contents).hexdigest()
            with patch.object(host_online, 'ROOT', root), \
                 patch.object(host_online, 'CLOUDFLARED_BINARIES', {'Linux': ('helper', expected)}), \
                 patch('scripts.host_online.platform.system', return_value='Linux'), \
                 patch('scripts.host_online.platform.machine', return_value='x86_64'), \
                 patch('scripts.host_online.urlopen', return_value=self.response(contents)) as download:
                destination = host_online.cloudflared_binary()
                self.assertEqual(destination.read_bytes(), contents)
                self.assertEqual(host_online.cloudflared_binary(), destination)
                self.assertEqual(download.call_count, 1)
                self.assertTrue(download.call_args.args[0].startswith('https://github.com/cloudflare/cloudflared/releases/download/'))

    def test_tunnel_failure_never_announces_a_provisional_address(self):
        from contextlib import redirect_stdout
        from unittest.mock import Mock
        import queue
        server, tunnel = Mock(), Mock()
        server.poll.return_value = None
        tunnel.poll.return_value = 1
        messages = queue.Queue()
        provisional = 'https://unready-test-world.trycloudflare.com'
        messages.put('Allocated ' + provisional)
        messages.put('ERR Connection refused')
        messages.put(None)
        output = io.StringIO()
        with patch('scripts.host_online.public_ready', return_value=False), redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, 'internet tunnel'):
                host_online.wait_for_public(server, tunnel, messages, timeout=1)
        self.assertNotIn(provisional, output.getvalue())

    def test_failed_api_request_reports_cause_without_treating_api_as_a_game_url(self):
        from contextlib import redirect_stdout
        from unittest.mock import Mock
        import queue
        server, tunnel = Mock(), Mock()
        server.poll.return_value = None
        tunnel.poll.return_value = 1
        messages = queue.Queue()
        messages.put('failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": DNS connection refused')
        messages.put(None)
        output = io.StringIO()
        with patch('scripts.host_online.public_ready') as probe, redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, 'internet tunnel'):
                host_online.wait_for_public(server, tunnel, messages, timeout=1)
        probe.assert_not_called()
        self.assertIn('DNS connection refused', output.getvalue())

    @unittest.skipIf(sys.platform == 'win32', 'The portable Linux fixture uses an executable shebang.')
    def test_failed_tunnel_stops_its_real_server_and_releases_the_port(self):
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            helper = directory / 'unavailable-tunnel'
            helper.write_text('#!' + sys.executable + '\nprint("ERR Tunnel unavailable for this test")\n', encoding='utf-8')
            helper.chmod(0o755)
            database = directory / 'public.sqlite3'
            port = available_port()
            output = io.StringIO()
            with patch('scripts.host_online.cloudflared_binary', return_value=helper), redirect_stdout(output):
                result = host_online.main(['--port', str(port), '--database', str(database), '--no-browser'])
            self.assertEqual(result, 1)
            self.assertFalse(play.port_busy(port))
            self.assertNotIn('Public HTTPS and WSS connection checks passed', output.getvalue())
            self.assertNotIn('Share this address', output.getvalue())
            self.assertIn('Host-WORLDFORGE-LAN.bat', output.getvalue())
            self.assertTrue(database.is_file())
            store = Store(database)
            try:
                self.assertEqual(store.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
