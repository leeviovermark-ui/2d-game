"""Open a local browser client which joins another computer's LAN authority.

Godot's Web export requires a secure browser context. Loopback HTTP provides
that context while gameplay connects to the shared private-network WebSocket.
This launcher serves static client files only; it creates no server or saves.
"""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
from pathlib import Path
import sys
from urllib.parse import quote, unquote, urlsplit
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / 'build/web'
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                         ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def server_address(value):
    """Accept the host's displayed LAN address without DNS or credential URLs."""
    value = value.strip()
    if not value:
        raise ValueError('Paste the shared server address printed by the host.')
    if '://' not in value:
        value = 'http://' + value
    try:
        parts = urlsplit(value)
        port = parts.port
        address = ipaddress.IPv4Address(parts.hostname or '')
    except ValueError as exc:
        raise ValueError('Use a private IPv4 address such as http://192.168.1.20:8765.') from exc
    if (parts.scheme not in ('http', 'ws') or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or parts.path not in ('', '/', '/index.html')
            or parts.netloc.endswith(':') or not any(address in network for network in PRIVATE_NETWORKS)):
        raise ValueError('Use the host\'s private Wi-Fi IPv4 address with no password, query, or extra path. '
                         'For an internet HTTPS address, open it directly in your browser.')
    port = 8765 if port is None else port
    if not 1 <= port <= 65535:
        raise ValueError('The shared server port must be between 1 and 65535.')
    return f'ws://{address}:{port}'


def static_server(port, directory=WEB_ROOT):
    directory = Path(directory).resolve()

    class ClientFiles(SimpleHTTPRequestHandler):
        extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                          '.wasm': 'application/wasm', '.pck': 'application/octet-stream'}

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def translate_path(self, path):
            path = unquote(urlsplit(path).path)
            return str((directory / path.lstrip('/')).resolve())

        def send_head(self):
            target = Path(self.translate_path(self.path))
            if target == directory:
                target = (directory / 'index.html').resolve()
            if not target.is_relative_to(directory) or not target.is_file():
                self.send_error(404, 'Client file not found')
                return None
            return super().send_head()

        def end_headers(self):
            self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
            self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-cache')
            super().end_headers()

        def log_message(self, format, *args):
            # A browser query preselects its endpoint. Never log query values.
            pass

    return ThreadingHTTPServer(('127.0.0.1', port), ClientFiles)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Join one shared WORLDFORGE server on your Wi-Fi.')
    parser.add_argument('--server', help='The host\'s displayed private-network address, such as http://192.168.1.20:8765.')
    parser.add_argument('--port', type=int, default=8770, help='Local browser client port (default: 8770).')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    if sys.version_info < (3, 12):
        print('WORLDFORGE needs Python 3.12 or newer. Install it from https://www.python.org/downloads/')
        return 1
    if not 1 <= args.port <= 65535:
        print('Choose a local browser port between 1 and 65535.')
        return 1
    if any(not (WEB_ROOT / name).is_file() for name in ('index.html', 'index.js', 'index.wasm', 'index.pck')):
        print('Extract the complete WORLDFORGE-playable ZIP before joining the shared server.')
        return 1
    try:
        value = args.server
        if value is None:
            value = input('Paste the server address shown in your friend\'s Host-WORLDFORGE-LAN window: ')
        endpoint = server_address(value)
    except (ValueError, EOFError) as exc:
        print('Could not choose the shared server: ' + str(exc))
        return 1
    except KeyboardInterrupt:
        return 0
    try:
        server = static_server(args.port)
    except OSError as exc:
        print('Could not open the local browser client: ' + str(exc))
        print('Close the existing Join-WORLDFORGE-LAN window, or choose another local port with --port 8771.')
        return 1
    url = f'http://127.0.0.1:{args.port}/?join=' + quote(endpoint, safe='')
    print('\nJoining the shared server at ' + endpoint, flush=True)
    print('This launcher serves only the browser client. Your friend hosts all accounts and worlds.', flush=True)
    print('Play at ' + url, flush=True)
    print('Keep this window open while playing. Press Ctrl+C to close the local client.', flush=True)
    if not args.no_browser:
        try:
            if not webbrowser.open(url, new=2):
                print('Open the address above in Chrome or Edge.', flush=True)
        except (OSError, webbrowser.Error):
            print('Open the address above in Chrome or Edge.', flush=True)
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        print('\nLocal browser client closed. The shared host keeps your saved progress.', flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
