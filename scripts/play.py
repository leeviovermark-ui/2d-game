"""One-click local or same-network play, with graceful shutdown."""
import argparse
import asyncio
from importlib import metadata
import ipaddress
import json
import logging
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import venv
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
HEALTH_MESSAGE = b'WORLDFORGE authority healthy'
RELEASE = 'stage3'
PROTOCOL = 2


def compatible_dependencies():
    try:
        return metadata.version('websockets') == '16.0'
    except metadata.PackageNotFoundError:
        return False


def managed_runtime():
    """Keep first-time package installation in the existing ignored project venv."""
    environment = ROOT / '.venv'
    python = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not python.is_file():
        print('Preparing the local Python environment. This only happens once.', flush=True)
        venv.create(environment, with_pip=True)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')],
                   cwd=ROOT, check=True)
    return python


def health_ready(url):
    try:
        with urlopen(url + '/health', timeout=1) as response:
            return response.status == 200 and response.read(128).startswith(HEALTH_MESSAGE)
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def compatible_server(url):
    """An older healthy server must not silently serve its older browser build."""
    try:
        with urlopen(url + '/version', timeout=1) as response:
            raw = response.read(4097)
            if response.status != 200 or len(raw) > 4096:
                return False
            version = json.loads(raw)
            return (isinstance(version, dict) and version.get('release') == RELEASE
                    and type(version.get('protocol')) is int and version['protocol'] == PROTOCOL)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError):
        return False


def port_busy(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.3):
            return True
    except OSError:
        return False


def lan_addresses():
    """Find usable IPv4 interfaces without sending a network probe."""
    candidates = set()
    try:
        candidates.update(address[4][0] for address in socket.getaddrinfo(
            socket.gethostname(), None, family=socket.AF_INET))
    except OSError:
        pass
    # UDP connect only asks the OS which local interface serves its default
    # route. It sends no packets and needs no DNS or internet service.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect(('192.0.2.1', 9))
            candidates.add(route.getsockname()[0])
    except OSError:
        pass
    addresses = []
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if (address.version == 4 and address.is_private and not address.is_loopback
                and not address.is_unspecified and not address.is_link_local):
            addresses.append(str(address))
    return sorted(addresses, key=lambda value: int(ipaddress.ip_address(value)))


def local_url(host, port):
    browser_host = '127.0.0.1' if host in ('0.0.0.0', 'localhost') else host
    if ':' in browser_host:
        browser_host = '[' + browser_host + ']'
    return f'http://{browser_host}:{port}'


def announce_lan(host, port):
    if host in ('127.0.0.1', 'localhost', '::1'):
        return
    addresses = lan_addresses() if host == '0.0.0.0' else [host]
    print('\nThis computer hosts the shared world. Give friends ONE shared server address:', flush=True)
    for address in addresses:
        print(f'Friends on your Wi-Fi: http://{address}:{port}', flush=True)
    if not addresses:
        command = 'ipconfig in PowerShell' if sys.platform == 'win32' else 'ip -4 addr show in a terminal'
        print('Could not detect your Wi-Fi address. Run ' + command, flush=True)
        print(f'and use your Wi-Fi adapter IPv4 address: http://YOUR-IPV4-ADDRESS:{port}', flush=True)
    print('Use a different explorer account for each player; accounts and worlds belong to this host.', flush=True)
    print('Friends double-click Join-WORLDFORGE-LAN.bat and paste the address above.', flush=True)
    print('The Join launcher opens their local browser client connected to this shared host.', flush=True)
    print('Friends must not start Play-WORLDFORGE.bat or another Host launcher.', flush=True)
    print('If a friend cannot connect, allow Python on Private networks in Windows Firewall.', flush=True)
    print('Both computers need the same Wi-Fi; guest Wi-Fi / client isolation can block access.', flush=True)


def open_browser(url, disabled):
    print('\nPlay at ' + url, flush=True)
    if not disabled:
        try:
            if not webbrowser.open(url, new=2):
                print('Open the address above in Chrome or Edge.', flush=True)
        except (OSError, webbrowser.Error):
            print('Open the address above in Chrome or Edge.', flush=True)


def announce_when_ready(url, disabled, stopped, host='127.0.0.1', port=8765):
    deadline = time.monotonic() + 15
    while not stopped.is_set() and time.monotonic() < deadline:
        if health_ready(url) and compatible_server(url):
            open_browser(url, disabled)
            announce_lan(host, port)
            print('Keep this window open while playing. Press Ctrl+C to save and stop.', flush=True)
            return
        stopped.wait(0.2)
    if not stopped.is_set():
        print('Startup is taking longer than expected. Check the messages in this window.', flush=True)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description='Start WORLDFORGE and open its browser client.')
    parser.add_argument('--host', default='127.0.0.1',
                        help='Use 0.0.0.0 to host one shared server for friends on your Wi-Fi.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--database', default=str(ROOT / 'data/worldforge.sqlite3'))
    parser.add_argument('--admin', action='append', default=[], metavar='NAME',
                        help='Assign a named server administrator; can be repeated.')
    parser.add_argument('--no-browser', action='store_true', help='Print the URL without opening a browser.')
    args = parser.parse_args(arguments)
    if sys.version_info < (3, 12):
        print('WORLDFORGE needs Python 3.12 or newer. Install it from https://www.python.org/downloads/')
        return 1
    if not 1 <= args.port <= 65535:
        print('Choose a port between 1 and 65535.')
        return 1
    required = ['index.html', 'index.js', 'index.wasm', 'index.pck']
    if any(not (ROOT / 'build/web' / filename).is_file() for filename in required):
        print('The browser game files are missing. Extract the complete WORLDFORGE-playable ZIP first.')
        print('For source checkouts, run bash scripts/export_web.sh to build the browser client.')
        return 1
    if not compatible_dependencies():
        try:
            python = managed_runtime()
            worker = subprocess.Popen([str(python), str(Path(__file__).resolve()), *arguments], cwd=ROOT)
            try:
                return worker.wait()
            except KeyboardInterrupt:
                # Console Ctrl+C reaches the server too; let it save and close normally.
                try:
                    return worker.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    worker.terminate()
                    worker.wait(timeout=5)
                    return 1
        except (OSError, subprocess.CalledProcessError) as exc:
            print('Could not prepare Python dependencies: ' + str(exc))
            print('Check your internet connection, then start Play-WORLDFORGE.bat again.')
            return 1
    url = local_url(args.host, args.port)
    if port_busy(args.port):
        if health_ready(url):
            if not compatible_server(url):
                print('An older or different WORLDFORGE release is still running on this port.')
                print('Press Ctrl+C in its original server window, then start this launcher again.')
                print('To run a separate server instead, start with --port 8766.')
                return 1
            if args.host not in ('127.0.0.1', 'localhost', '::1'):
                print('A server is already running on this port. Stop it with Ctrl+C in its original window first.')
                print('Then restart this LAN launcher so it can bind to your Wi-Fi interface.')
                return 1
            print('WORLDFORGE is already running. Its original server window controls saving and shutdown.')
            open_browser(url, args.no_browser)
            return 0
        print('Another application is using port ' + str(args.port) + '. Close it or start with --port 8766.')
        return 1
    sys.path.insert(0, str(ROOT))
    from server.main import main as run_server
    stopped = threading.Event()
    watcher = threading.Thread(target=announce_when_ready,
                               args=(url, args.no_browser, stopped, args.host, args.port), daemon=True)
    print('Starting WORLDFORGE. Worlds and characters are saved in ' + str(args.database) + '.', flush=True)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    watcher.start()
    try:
        asyncio.run(run_server(args))
        print('WORLDFORGE stopped. Progress is saved.', flush=True)
        return 0
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print('Could not start WORLDFORGE: ' + str(exc))
        return 1
    finally:
        stopped.set()


if __name__ == '__main__':
    raise SystemExit(main())
