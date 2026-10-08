"""Accept a shared, already-running WORLDFORGE host through its real Web UI.

Default mode requires public HTTPS and WSS. Use --allow-lan explicitly for a
private network address; a LAN pass is never reported as internet verification.
LAN Web clients can be served securely from a local join launcher with
--web-client-url http://127.0.0.1:8770/?join=ENCODED_WEBSOCKET_ADDRESS. The
mandatory --url still identifies the shared nonloopback LAN authority; the
actual game WebSocket must connect there rather than to the client launcher.
This runner does not start a server, grant items, or inject game commands. It
creates two ordinary accounts and one uniquely named world on the supplied
server, leaving existing players and worlds alone. Do not use an occupied
production server for repeated runs: development servers allow 100 worlds.
"""
import argparse
import asyncio
from copy import deepcopy
import ipaddress
import os
import secrets
import shutil
import socket
import time
from urllib.parse import parse_qs, unquote, urlsplit

from playwright.async_api import async_playwright

from browser_smoke import ARTIFACTS, Client


def checked_url(raw, allow_lan=False):
    """Refuse accidental localhost checks and public plaintext credentials."""
    parts = urlsplit(raw)
    if (parts.scheme not in ('http', 'https') or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment):
        raise ValueError('Supply an HTTP(S) game URL without credentials, query, or fragment.')
    try:
        port = parts.port or (443 if parts.scheme == 'https' else 80)
    except ValueError as error:
        raise ValueError('The game URL has an invalid port.') from error
    if not 1 <= port <= 65535:
        raise ValueError('The game URL has an invalid port.')
    host = parts.hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith('.localhost'):
        raise ValueError('Localhost is not an external or LAN multiplayer test.')
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = list({ipaddress.ip_address(row[4][0]) for row in
                              socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
        except (OSError, ValueError) as error:
            raise ValueError('The supplied game hostname cannot be resolved.') from error
    if not addresses or any(address.is_loopback or address.is_unspecified for address in addresses):
        raise ValueError('The game address resolves to a loopback or unspecified interface.')
    if parts.scheme == 'http' and any(address.is_global for address in addresses):
        raise ValueError('Public hosts require HTTPS; --allow-lan permits private network HTTP only.')
    if not allow_lan and (parts.scheme != 'https' or any(not address.is_global for address in addresses)):
        raise ValueError('Internet acceptance requires public HTTPS. Use --allow-lan for a same-network test.')
    return raw.rstrip('/'), parts.scheme, host, port


def checked_web_client(raw, target):
    """Accept only the explicit loopback join page for the selected LAN host."""
    parts = urlsplit(raw)
    if (parts.scheme != 'http' or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.fragment):
        raise ValueError('The LAN Web client must be a local HTTP join launcher without credentials or fragment.')
    host = parts.hostname.lower().rstrip('.')
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loopback = host == 'localhost' or host.endswith('.localhost')
    if not is_loopback:
        raise ValueError('--web-client-url must use a loopback client launcher; --url supplies the shared LAN host.')
    try:
        port = parts.port or 80
        parameters = parse_qs(parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise ValueError('The local join launcher URL has an invalid port or query.') from error
    if not 1 <= port <= 65535 or set(parameters) != {'join'} or len(parameters['join']) != 1:
        raise ValueError('The local launcher URL must include exactly one ?join=ENCODED_WEBSOCKET_ADDRESS parameter.')
    endpoint = urlsplit(parameters['join'][0])
    try:
        endpoint_port = endpoint.port or (443 if endpoint.scheme == 'wss' else 80)
    except ValueError as error:
        raise ValueError('The local join parameter has an invalid server port.') from error
    _, scheme, server_host, server_port = target
    try:
        server_address = ipaddress.ip_address(server_host)
    except ValueError as error:
        raise ValueError('The local LAN join test requires a literal private IPv4 authority.') from error
    private_networks = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')
    if server_address.version != 4 or not any(server_address in ipaddress.ip_network(network)
                                              for network in private_networks):
        raise ValueError('The local LAN join test requires a literal private IPv4 authority.')
    if (endpoint.scheme != ('wss' if scheme == 'https' else 'ws')
            or endpoint.hostname != server_host or endpoint_port != server_port
            or endpoint.username is not None or endpoint.password is not None
            or endpoint.path not in ('', '/') or endpoint.query or endpoint.fragment):
        raise ValueError('The local join parameter must select the same shared authority as --url.')
    return raw, host


class HostedClient(Client):
    def __init__(self, page, label):
        super().__init__(page)
        self.label = label
        self.socket_urls = []
        page.on('websocket', lambda websocket: self.socket_urls.append(websocket.url))

    async def wait(self, predicate, description, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            await asyncio.sleep(.05)
        # Registration receipts contain a recovery credential. Inspect labels
        # only and suppress screenshots while any account form is visible.
        if not await self.page.evaluate("() => (window.worldforge_controls || []).some(c => c.text === 'I have saved it — enter the world' || c.placeholder === 'Start with a letter · 3–20 characters')"):
            await self.page.screenshot(path=str(ARTIFACTS / ('hosted-' + self.label + '-failure.png')))
        raise AssertionError('Timed out: ' + description)

    async def register(self, url, name, password):
        await self.page.add_init_script('window.worldforge_inspect = true;')
        response = await self.page.goto(url, wait_until='domcontentloaded', timeout=60000)
        assert response is not None and response.status == 200, 'The supplied game URL did not serve an HTTP 200 game page.'
        # Godot requires a secure context even for its single-thread Web
        # export. Fail immediately on plain LAN HTTP instead of timing out
        # waiting for controls which the browser cannot create.
        if not await self.page.evaluate('window.isSecureContext'):
            raise AssertionError('Godot Web requires a secure context. Serve this LAN host over trusted HTTPS; private-IP HTTP cannot start the game.')
        await self.click('Play WORLDFORGE  →', kind='Button', timeout=60)
        await self.submit_account(name, password, register=True)
        await self.wait(lambda: self.id is not None, 'real hosted account registration', timeout=35)
        await self.dismiss_recovery()
        await self.wait(lambda: any(player['id'] == self.id for player in self.players),
                        'authenticated hosted player snapshot')
        await asyncio.sleep(.6)

    def check_endpoint(self, scheme, host, port):
        assert self.socket_urls, 'The browser never opened a WebSocket connection.'
        expected_scheme = 'wss' if scheme == 'https' else 'ws'
        for raw in self.socket_urls:
            endpoint = urlsplit(raw)
            endpoint_port = endpoint.port or (443 if endpoint.scheme == 'wss' else 80)
            assert (endpoint.scheme, endpoint.hostname.lower().rstrip('.'), endpoint_port) == (
                expected_scheme, host, port), 'The browser connected to a different server or transport.'


async def close_notes(client):
    # Field notes can cover otherwise reachable terrain. Toggle them only if
    # their actual displayed heading is present, including after reloading.
    if any(c.get('kind') == 'Label' and c.get('text', '').startswith('FIELD NOTES')
           for c in await client.controls()):
        await client.key('j')


async def run(args):
    target = checked_url(args.url, args.allow_lan)
    url, scheme, host, port = target
    web_client_host = None
    if args.web_client_url:
        url, web_client_host = checked_web_client(args.web_client_url, target)
    ARTIFACTS.mkdir(exist_ok=True)
    stamp = secrets.token_hex(4)
    first_name, second_name = 'QAa' + stamp, 'QAb' + stamp
    world_name = 'QA_' + stamp.upper()
    password = secrets.token_urlsafe(24)
    scope = ('LAN test with a local Web client and shared LAN WebSocket; this does not prove internet availability'
             if args.web_client_url else ('LAN test; this does not prove internet availability'
             if args.allow_lan else 'public HTTPS/WSS host test'))
    print('Hosted QA scope: ' + scope + '.', flush=True)
    async with async_playwright() as playwright:
        launch = {'executable_path': args.chromium, 'headless': True,
                  'args': ['--no-sandbox', '--enable-unsafe-swiftshader']}
        # Cloud environments may proxy private IP requests to an internet
        # gateway. Bypass that proxy only for this explicitly selected literal
        # LAN interface; public internet requests retain their existing route.
        if args.allow_lan:
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                if address.is_private:
                    inherited = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
                    if inherited:
                        proxy = urlsplit(inherited)
                        if proxy.hostname and proxy.scheme in ('http', 'https', 'socks4', 'socks5'):
                            proxy_host = '[' + proxy.hostname + ']' if ':' in proxy.hostname else proxy.hostname
                            bypass = host + (',' + web_client_host if web_client_host else '')
                            settings = {'server': proxy.scheme + '://' + proxy_host
                                        + (':' + str(proxy.port) if proxy.port else ''), 'bypass': bypass}
                            if proxy.username is not None:
                                settings['username'] = unquote(proxy.username)
                            if proxy.password is not None:
                                settings['password'] = unquote(proxy.password)
                            launch['proxy'] = settings
                    else:
                        bypass = host + (';' + web_client_host if web_client_host else '')
                        launch['args'].append('--proxy-bypass-list=' + bypass)
        browser = await playwright.chromium.launch(**launch)
        try:
            # Distinct browser storage and bearer sessions are essential: two
            # tabs sharing one account do not prove two-player multiplayer.
            contexts = [await browser.new_context(viewport={'width': 1440, 'height': 900})
                        for _ in range(2)]
            a, b = [HostedClient(await context.new_page(), label)
                    for context, label in zip(contexts, ('a', 'b'))]
            await a.register(url, first_name, password)
            await b.register(url, second_name, password)
            a.check_endpoint(scheme, host, port)
            b.check_endpoint(scheme, host, port)
            assert a.id != b.id, 'Both browsers authenticated as the same account.'
            await a.wait(lambda: any(player['id'] == b.id for player in a.players),
                         'first client sees distinct second player')
            await b.wait(lambda: any(player['id'] == a.id for player in b.players),
                         'second client sees distinct first player')
            print('Hosted QA: two independent accounts connected to the selected shared WebSocket host.', flush=True)

            await a.key('p')
            await a.fill(second_name, placeholder='Add a friend by explorer name')
            await a.click('Send request', kind='Button')
            await b.wait(lambda: any(friend['id'] == a.id for friend in
                            b.last.get('social_state', {}).get('incoming', [])), 'shared friend request')
            await b.key('p')
            await b.click(kind='Button', contains='Requests (1)')
            await b.click('Accept', kind='Button')
            await a.wait(lambda: any(friend['id'] == b.id for friend in
                            a.last.get('social_state', {}).get('friends', [])), 'accepted shared friendship')
            await b.key('Escape')
            await b.key('m')
            await b.wait(lambda: 'directory' in b.last, 'live hosted world catalogue')
            assert len(b.last['directory'].get('worlds', [])) < 100, (
                'This host has reached its 100-world limit; use a separate QA host or free capacity.')
            await a.key('Escape')
            await a.key('m')
            await a.fill(world_name, placeholder='MY_FIRST_WORLD')
            await a.click('Create & enter', kind='Button')
            await a.wait(lambda: a.world['meta']['name'] == world_name, 'real unique world creation')
            await b.wait(lambda: any(world['name'] == world_name for world in
                            b.last['directory']['worlds']), 'new world pushed to other client catalogue')
            await b.fill(world_name, placeholder='Search worlds or their founders')
            await b.click('Visit  →', kind='Button')
            await b.wait(lambda: b.world['meta']['name'] == world_name, 'catalogue visit to same authority')
            await a.wait(lambda: any(player['id'] == b.id for player in a.players),
                         'both players share the newly created world')
            await asyncio.sleep(.8)
            await close_notes(a)
            await close_notes(b)

            old_x = b.position()['x']
            await b.move('a', .2)
            await b.wait(lambda: b.position()['x'] < old_x - .4, 'held input moves authoritative second player')
            expected_x = b.position()['x']
            await a.wait(lambda: any(player['id'] == b.id and abs(player['x'] - expected_x) < .08
                                    for player in a.players), 'second player movement reaches first browser')
            marker = len(b.messages)
            dirt_before = a.quantity('dirt')
            await a.key('2')
            await a.point(12, 20)
            await a.page.mouse.click(*a.tile_screen(12, 20), button='right')
            await a.wait(lambda: a.quantity('dirt') == dirt_before - 1, 'ordinary inventory-funded placement')
            await b.wait(lambda: any(packet['type'] == 'tile' and packet.get('x') == 12
                                    and packet.get('y') == 20 and packet.get('item') == 'dirt'
                                    for packet in b.messages[marker:]), 'placed block reaches second browser')
            # Auto-pickup belongs to whichever explorer reaches the drop first.
            # Move the builder clear so this step specifically verifies the
            # miner collects the item rather than racing a stationary friend.
            await a.move('a', .35)
            marker = len(a.messages)
            b_dirt_before = b.quantity('dirt')
            await b.key('1')
            await b.point(12, 20)
            await b.page.mouse.down()
            try:
                await a.wait(lambda: any(packet['type'] == 'tile' and packet.get('x') == 12
                                        and packet.get('y') == 20 and packet.get('item') is None
                                        for packet in a.messages[marker:]), 'real server-timed mining reaches first browser')
            finally:
                await b.page.mouse.up()
            await b.move('d', .2)
            await b.wait(lambda: b.quantity('dirt') == b_dirt_before + 1, 'mined item collected through real movement')
            # Leave one known player-built tile for a later fresh snapshot check.
            await a.point(12, 20)
            await a.page.mouse.click(*a.tile_screen(12, 20), button='right')
            await a.wait(lambda: a.quantity('dirt') == dirt_before - 2, 'persistent shared block placement')

            chat_text = 'Hosted multiplayer check ' + stamp
            marker = len(b.messages)
            await a.key('Enter')
            await a.page.keyboard.type(chat_text)
            await a.page.keyboard.press('Enter')
            await b.wait(lambda: any(packet['type'] == 'chat' and packet.get('name') == first_name
                                    and packet.get('text') == chat_text for packet in b.messages[marker:]),
                         'shared world chat crosses browser contexts')
            print('Hosted QA: distinct accounts, same endpoint, live catalogue, friendship, movement, placement, mining/pickup and chat passed.', flush=True)

            await a.key('p')
            await a.click('Nearby', kind='Button')
            await a.click('Trade', kind='Button')
            await b.wait(lambda: 'trade_invite' in b.last, 'nearby trade invitation')
            await b.click(kind='Button', contains='wants to trade')
            await a.wait(lambda: 'trade' in a.last, 'first trade screen opens')
            await b.wait(lambda: 'trade' in b.last, 'second trade screen opens')
            await a.choose(None, 'Earth (' + str(a.quantity('dirt')) + ')')
            await a.click('Set item', kind='Button')
            await a.wait(lambda: a.last['trade']['trade']['offers'][a.id] == {'dirt': 1}, 'exact first trade offer')
            await b.choose(None, 'Cedar planks (' + str(b.quantity('planks')) + ')')
            await b.click('Set item', kind='Button')
            await b.wait(lambda: b.last['trade']['trade']['offers'][b.id] == {'planks': 1}, 'exact second trade offer')
            before_a = (a.quantity('dirt'), a.quantity('planks'))
            before_b = (b.quantity('dirt'), b.quantity('planks'))
            await a.click('Lock my offer', kind='Button')
            await a.wait(lambda: a.id in a.last['trade']['trade']['locked'], 'first trade offer locked')
            await b.click('Lock my offer', kind='Button')
            await b.wait(lambda: len(b.last['trade']['trade']['locked']) == 2, 'both trade offers locked')
            await a.click('Confirm exchange', kind='Button')
            await b.wait(lambda: a.id in b.last['trade']['trade']['confirmed'], 'first exchange confirmation')
            await b.click('Confirm exchange', kind='Button')
            await a.wait(lambda: 'trade_closed' in a.last, 'confirmed atomic trade completes')
            await b.wait(lambda: 'trade_closed' in b.last, 'both trade screens close')
            assert (a.quantity('dirt'), a.quantity('planks')) == (before_a[0] - 1, before_a[1] + 1)
            assert (b.quantity('dirt'), b.quantity('planks')) == (before_b[0] + 1, before_b[1] - 1)

            saved_id, saved_inventory = a.id, deepcopy(a.inventory)
            before_welcomes = sum(packet['type'] == 'welcome' for packet in a.messages)
            await a.page.reload(wait_until='domcontentloaded', timeout=60000)
            await a.click('Continue as ' + first_name, kind='Button', timeout=60)
            await a.wait(lambda: sum(packet['type'] == 'welcome' for packet in a.messages) > before_welcomes,
                         'saved bearer session resumes through the real Continue button', timeout=35)
            assert a.id == saved_id and a.inventory == saved_inventory, 'Account identity or inventory failed to persist.'
            assert a.world['meta']['name'] == world_name, 'Reload lost the saved shared world.'
            assert [12, 20, 'dirt'] in a.world['tiles'], 'Player-built tile is absent from the fresh saved world snapshot.'
            await a.wait(lambda: any(friend['id'] == b.id for friend in
                            a.last.get('social_state', {}).get('friends', [])), 'saved friendship after reconnect')
            a.check_endpoint(scheme, host, port)
            await a.wait(lambda: any(player['id'] == b.id for player in a.players),
                         'reconnected browser sees its friend')
            await a.page.screenshot(path=str(ARTIFACTS / 'hosted-shared-world.png'))
            assert not a.errors and not b.errors, 'The hosted Godot browser clients reported runtime errors.'
            assert not any(packet['type'] == 'error' for packet in a.messages + b.messages), (
                'The shared authority rejected an acceptance step.')
            print('PASS: ' + scope + '; two independent Godot browser sessions on the same host, '
                  'shared catalogue/friends/movement/building/mining/chat, confirmed atomic trade, '
                  'saved Continue login, identity/world/inventory/tile persistence, no runtime errors.', flush=True)
        finally:
            await browser.close()


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='Already-running shared game URL; public HTTPS is required by default.')
    parser.add_argument('--allow-lan', action='store_true', help='Explicitly test a private network URL; this is not internet verification.')
    parser.add_argument('--web-client-url', '--local-client-url', help='Only with --allow-lan: secure-context local join launcher URL including its ?join= parameter; game sockets still use --url.')
    parser.add_argument('--chromium', default=shutil.which('chromium') or shutil.which('google-chrome'),
                        help='Chromium executable path (default: a system Chromium/Chrome installation).')
    args = parser.parse_args()
    if not args.chromium:
        parser.error('Install Chromium or supply --chromium /path/to/chromium.')
    try:
        target = checked_url(args.url, args.allow_lan)
        if args.web_client_url:
            if not args.allow_lan:
                raise ValueError('--web-client-url requires explicit --allow-lan mode.')
            checked_web_client(args.web_client_url, target)
    except ValueError as error:
        parser.error(str(error))
    return args


if __name__ == '__main__':
    asyncio.run(run(arguments()))
