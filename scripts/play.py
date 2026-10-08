"""One-click local browser play, with dependency setup and graceful shutdown."""
import argparse
import asyncio
from importlib import metadata
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


def port_busy(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.3):
            return True
    except OSError:
        return False


def open_browser(url, disabled):
    print('\nPlay at ' + url, flush=True)
    if not disabled:
        try:
            if not webbrowser.open(url, new=2):
                print('Open the address above in Chrome or Edge.', flush=True)
        except (OSError, webbrowser.Error):
            print('Open the address above in Chrome or Edge.', flush=True)


def announce_when_ready(url, disabled, stopped):
    deadline = time.monotonic() + 15
    while not stopped.is_set() and time.monotonic() < deadline:
        if health_ready(url):
            open_browser(url, disabled)
            print('Keep this window open while playing. Press Ctrl+C to save and stop.', flush=True)
            return
        stopped.wait(0.2)
    if not stopped.is_set():
        print('Startup is taking longer than expected. Check the messages in this window.', flush=True)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description='Start WORLDFORGE locally and open its browser client.')
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
    url = 'http://127.0.0.1:' + str(args.port)
    if port_busy(args.port):
        if health_ready(url):
            print('WORLDFORGE is already running. Its original server window controls saving and shutdown.')
            open_browser(url, args.no_browser)
            return 0
        print('Another application is using port ' + str(args.port) + '. Close it or start with --port 8766.')
        return 1
    sys.path.insert(0, str(ROOT))
    from server.main import main as run_server
    args.host = '127.0.0.1'
    stopped = threading.Event()
    watcher = threading.Thread(target=announce_when_ready, args=(url, args.no_browser, stopped), daemon=True)
    print('Starting WORLDFORGE. Your existing worlds and characters stay in data/worldforge.sqlite3.', flush=True)
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
