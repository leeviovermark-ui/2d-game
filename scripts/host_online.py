"""Host one shared server through a verified temporary HTTPS/WSS tunnel.

The share address only becomes ready after HTTP and WebSocket probes succeed.
The host owns its save database; keeping this process open keeps the room online.
"""
import argparse
import asyncio
import hashlib
import os
from pathlib import Path
import platform
import queue
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

try:
    from . import play
except ImportError:
    import play

ROOT = play.ROOT
CLOUDFLARED_VERSION = '2026.10.0'
CLOUDFLARED_BINARIES = {
    'Linux': ('cloudflared-linux-amd64',
              'd33ff2d14475178d2012c2c56beba87389ac5ded27649519f198a7d3134a99db'),
    'Windows': ('cloudflared-windows-amd64.exe',
                '86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c'),
}
MAX_BINARY_BYTES = 128 * 1024 * 1024
SHARE_ADDRESS = re.compile(r'https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com\b')


def file_digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def cloudflared_binary():
    system = platform.system()
    machine = platform.machine().lower()
    if system not in CLOUDFLARED_BINARIES or machine not in ('amd64', 'x86_64'):
        raise RuntimeError('The one-click internet host supports Windows and Linux on Intel/AMD 64-bit computers. '
                           'Use the LAN launcher or the deployment guide on other systems.')
    filename, expected = CLOUDFLARED_BINARIES[system]
    directory = ROOT / '.tools/cloudflared' / CLOUDFLARED_VERSION
    destination = directory / filename
    if destination.is_file() and file_digest(destination) == expected:
        if system != 'Windows':
            destination.chmod(destination.stat().st_mode | 0o100)
        return destination
    directory.mkdir(parents=True, exist_ok=True)
    url = ('https://github.com/cloudflare/cloudflared/releases/download/'
           + CLOUDFLARED_VERSION + '/' + filename)
    print('Downloading the official Cloudflare tunnel helper (one-time setup).', flush=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix='.download-', delete=False) as target:
            temporary = Path(target.name)
            digest = hashlib.sha256()
            size = 0
            with urlopen(url, timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError('Could not download the tunnel helper.')
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_BINARY_BYTES:
                        raise RuntimeError('Tunnel helper download exceeded its size limit.')
                    digest.update(chunk)
                    target.write(chunk)
            if digest.hexdigest() != expected:
                raise RuntimeError('Tunnel helper checksum did not match the pinned official release. '
                                   'The downloaded file will not be run.')
        if system != 'Windows':
            temporary.chmod(0o755)
        os.replace(temporary, destination)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def child_process(command, **kwargs):
    if sys.platform == 'win32':
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(command, cwd=ROOT, **kwargs)


def stop_process(process, label):
    if process is None or process.poll() is not None:
        return
    print(f'Stopping {label}...', flush=True)
    try:
        process.send_signal(signal.CTRL_BREAK_EVENT if sys.platform == 'win32' else signal.SIGINT)
        process.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def read_tunnel_output(process, messages):
    try:
        for line in process.stdout:
            messages.put(line.rstrip())
    finally:
        messages.put(None)


async def websocket_ready(url):
    from websockets.asyncio.client import connect
    async with connect('wss://' + url.removeprefix('https://'), open_timeout=6,
                       close_timeout=2, compression=None, max_size=65536) as connection:
        pong = await connection.ping()
        await asyncio.wait_for(pong, timeout=5)


def public_ready(url):
    if not play.health_ready(url) or not play.compatible_server(url):
        return False
    try:
        with urlopen(url + '/index.html', timeout=5) as response:
            html = response.read(2 * 1024 * 1024 + 1)
            if (response.status != 200 or len(html) > 2 * 1024 * 1024
                    or 'text/html' not in response.headers.get('Content-Type', '').lower()
                    or b'WORLDFORGE' not in html or b'Engine' not in html):
                return False
    except (HTTPError, URLError, TimeoutError, OSError):
        return False
    try:
        asyncio.run(websocket_ready(url))
        return True
    except (OSError, TimeoutError, ValueError):
        return False
    except Exception as exc:
        # InvalidStatus, proxy and TLS failures are startup failures, never
        # evidence that multiplayer is available. No account is created here.
        from websockets.exceptions import WebSocketException
        if isinstance(exc, WebSocketException):
            return False
        raise


def wait_for_local(server, url):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError('The game server stopped during startup. Check the server message above.')
        if play.health_ready(url) and play.compatible_server(url):
            return
        time.sleep(.2)
    raise RuntimeError('The game server did not become ready. Check the server message above.')


def wait_for_public(server, tunnel, messages, timeout=90):
    deadline = time.monotonic() + timeout
    address = None
    last_probe = 0
    last_status = time.monotonic()
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError('The game server stopped before the internet connection became ready.')
        try:
            line = messages.get(timeout=.2)
        except queue.Empty:
            line = ''
        if line is None:
            if tunnel.poll() is not None:
                raise RuntimeError('Cloudflare could not open an internet tunnel. Check the messages above.')
        elif line:
            # Do not advertise the provisional share URL before it works.
            if 'ERR' in line or 'error' in line.lower() or 'failed' in line.lower():
                print('Tunnel: ' + line[:700], flush=True)
            else:
                match = SHARE_ADDRESS.search(line)
                if match and match.group(0) != 'https://api.trycloudflare.com':
                    address = match.group(0)
        now = time.monotonic()
        if address and now - last_probe >= 2:
            last_probe = now
            if public_ready(address):
                return address
        if now - last_status >= 10:
            print('Still waiting for the public HTTPS and WebSocket connection...', flush=True)
            last_status = now
    raise RuntimeError(f'The public HTTPS/WebSocket checks did not succeed within {timeout:g} seconds. '
                       'The server is not announced as online.')


def parse_args(arguments):
    parser = argparse.ArgumentParser(description='Host a temporary shared WORLDFORGE internet server.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--database', default=str(ROOT / 'data/worldforge.sqlite3'))
    parser.add_argument('--admin', action='append', default=[], metavar='NAME',
                        help='Grant access to an account you have already created and secured locally.')
    parser.add_argument('--no-browser', action='store_true')
    return parser.parse_args(arguments)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(arguments)
    if sys.version_info < (3, 12):
        print('WORLDFORGE needs Python 3.12 or newer. Install it from https://www.python.org/downloads/')
        return 1
    if not 1 <= args.port <= 65535:
        print('Choose a port between 1 and 65535.')
        return 1
    if any(not (ROOT / 'build/web' / filename).is_file()
           for filename in ('index.html', 'index.js', 'index.wasm', 'index.pck')):
        print('Extract the complete WORLDFORGE-playable ZIP before starting the online host.')
        return 1
    if not play.compatible_dependencies():
        try:
            python = play.managed_runtime()
            worker = subprocess.Popen([str(python), str(Path(__file__).resolve()), *arguments], cwd=ROOT)
            try:
                return worker.wait()
            except KeyboardInterrupt:
                try:
                    return worker.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    worker.terminate()
                    worker.wait(timeout=5)
                    return 1
        except (OSError, subprocess.CalledProcessError) as exc:
            print('Could not prepare Python dependencies: ' + str(exc))
            return 1
    if play.port_busy(args.port):
        print('This port is already in use. Stop Play-WORLDFORGE / the existing server with Ctrl+C first.')
        print('The online host starts its own supervised server so it can apply public-server protections.')
        return 1
    server = tunnel = None
    try:
        binary = cloudflared_binary()
        command = [sys.executable, '-m', 'server.main', '--host', '127.0.0.1', '--public',
                   '--trusted-proxy', '127.0.0.1', '--proxy-ip-header', 'CF-Connecting-IP',
                   '--port', str(args.port), '--database', str(args.database)]
        for name in args.admin:
            command.extend(('--admin', name))
        print('Starting the shared internet host. The host keeps the saved worlds and accounts.', flush=True)
        print('Public visitors will not automatically become administrators.', flush=True)
        server = child_process(command)
        local = f'http://127.0.0.1:{args.port}'
        wait_for_local(server, local)
        with tempfile.TemporaryDirectory(prefix='worldforge-tunnel-') as directory:
            config = Path(directory) / 'config.yml'
            config.write_text('{}\n', encoding='utf-8')
            tunnel = child_process([str(binary), 'tunnel', '--config', str(config), '--no-autoupdate',
                                    '--protocol', 'http2', '--url', local, '--metrics', '127.0.0.1:0',
                                    '--grace-period', '5s'], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
            messages = queue.Queue()
            reader = threading.Thread(target=read_tunnel_output, args=(tunnel, messages), daemon=True)
            reader.start()
            print('Opening a temporary HTTPS/WSS tunnel. No router port forwarding is required.', flush=True)
            address = wait_for_public(server, tunnel, messages)
            print('\nPublic HTTPS and WSS connection checks passed.', flush=True)
            print('Share this address with every player: ' + address, flush=True)
            print('Everyone opens that same address and signs in with a different explorer account.', flush=True)
            print('Keep this window and computer running. Closing it takes this server offline.', flush=True)
            print('This temporary address changes on restart. Use the deployment guide for a permanent server.', flush=True)
            play.open_browser(address, args.no_browser)
            while server.poll() is None and tunnel.poll() is None:
                try:
                    line = messages.get(timeout=.5)
                    if line and ('ERR' in line or 'error' in line.lower() or 'failed' in line.lower()):
                        print('Tunnel: ' + line[:700], flush=True)
                except queue.Empty:
                    pass
            if server.poll() is not None or tunnel.poll() is not None:
                raise RuntimeError('The server or tunnel stopped. Players are offline; restart this host to reconnect.')
    except KeyboardInterrupt:
        print('\nSaving the server and closing the internet connection...', flush=True)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print('Could not host WORLDFORGE online: ' + str(exc), flush=True)
        print('For friends on the same Wi-Fi, use Host-WORLDFORGE-LAN.bat instead.', flush=True)
        return 1
    finally:
        stop_process(tunnel, 'the tunnel')
        stop_process(server, 'the game server and saving progress')
        if tunnel is not None and tunnel.stdout is not None:
            tunnel.stdout.close()


if __name__ == '__main__':
    raise SystemExit(main())
