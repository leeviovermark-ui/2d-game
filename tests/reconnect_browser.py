"""Keep a real exported Godot client open across its authority's restart.

Registration, placement, and movement use the canvas UI. The server process and
database are owned by this check; only those processes are stopped. Credentials
and raw WebSocket packets are never printed or saved as browser artifacts.
"""
import asyncio
from copy import deepcopy
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

from playwright.async_api import async_playwright
from browser_smoke import ARTIFACTS, Client, ROOT


def healthy(url):
    try:
        with urlopen(url + '/health', timeout=.3) as response:
            return response.status == 200 and response.read(128).startswith(b'WORLDFORGE authority healthy')
    except (URLError, TimeoutError, OSError):
        return False


async def ready(server, url):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        assert server.poll() is None, 'The temporary authority stopped during startup.'
        if await asyncio.to_thread(healthy, url):
            return
        await asyncio.sleep(.05)
    raise AssertionError('The temporary authority did not become healthy.')


async def stop(server):
    if server is None or server.poll() is not None:
        return
    server.terminate()
    try:
        await asyncio.to_thread(server.wait, timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()
        await asyncio.to_thread(server.wait, timeout=3)
        raise AssertionError('The temporary authority did not shut down gracefully.')


async def run():
    ARTIFACTS.mkdir(exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = 'http://127.0.0.1:' + str(port)
    with tempfile.TemporaryDirectory(prefix='worldforge-reconnect-') as temporary:
        database = Path(temporary) / 'reconnect.sqlite3'
        with open(Path(temporary) / 'authority.log', 'w') as log:
            command = [str(ROOT / '.venv/bin/python'), '-m', 'server.main',
                       '--port', str(port), '--database', str(database)]
            server = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=log)
            browser = None
            try:
                await ready(server, url)
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(
                        executable_path='/usr/bin/chromium', headless=True,
                        args=['--no-sandbox', '--enable-unsafe-swiftshader'])
                    page = await browser.new_page(viewport={'width': 1440, 'height': 900})
                    client = Client(page)
                    await client.login(url, 'ReconnectExplorer')
                    await client.key('j')
                    await client.key('2')
                    await client.point(12, 20)
                    await page.mouse.click(*client.tile_screen(12, 20), button='right')
                    await client.wait(lambda: client.quantity('dirt') == 23,
                                      'real block placement before restart')
                    first = client.last['welcome']
                    ident, token = first['id'], first['token']
                    epoch = first['player']['epoch']
                    inventory = deepcopy(client.inventory)
                    world = client.world['meta']['name']
                    initial_welcomes = sum(m['type'] == 'welcome' for m in client.messages)
                    await client.key('c')
                    await client.control(kind='Label', text='The workshop')

                    # Graceful WebSocket close 1001 should trigger bounded retry,
                    # unlike an intentional logout or moderation close.
                    await stop(server)
                    server = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=log)
                    await ready(server, url)
                    await client.wait(
                        lambda: sum(m['type'] == 'welcome' for m in client.messages) == initial_welcomes + 1,
                        'automatic saved-session resume after the authority restart', timeout=15)
                    await asyncio.sleep(.4)
                    controls = await client.controls()
                    assert not any(c.get('text') == 'The workshop' for c in controls), 'A stale workshop modal blocked reconnect.'
                    resumed = client.last['welcome']
                    assert resumed['id'] == ident, 'Reconnect created a different account.'
                    assert resumed['token'] == token, 'Reconnect did not resume its existing session.'
                    assert resumed['world']['meta']['name'] == world, 'Reconnect changed the world.'
                    assert resumed['slots'] == inventory, 'Reconnect lost items or granted another starter kit.'
                    assert resumed['player']['epoch'] != epoch, 'Reconnect retained an old movement epoch.'
                    assert resumed.get('recovery_code') is None, 'Reconnect issued another registration recovery code.'
                    assert [12, 20, 'dirt'] in resumed['world']['tiles'], 'The committed block did not survive restart.'
                    with sqlite3.connect(database) as db:
                        assert db.execute('SELECT count(*) FROM accounts').fetchone()[0] == 1
                        assert db.execute('SELECT count(*) FROM sessions WHERE account=? AND expires>?',
                                          (ident, time.time())).fetchone()[0] == 1

                    await client.wait(lambda: any(p['id'] == ident and p.get('epoch') != epoch
                                                   for p in client.players),
                                      'fresh player snapshot after automatic resume')
                    before = client.position()['x']
                    await client.move('a', .35)
                    assert client.position()['x'] < before - .8, 'Movement stopped working after automatic resume.'
                    assert client.inventory == inventory, 'Movement after resume altered the inventory.'
                    assert not [m for m in client.messages if m['type'] == 'error'], 'The authority rejected a reconnect intent.'
                    assert not client.errors, 'Browser runtime errors occurred during reconnect.'
                    print('Live Godot reconnect passed: automatic token resume, saved block/inventory, '
                          'one account/starter kit, fresh movement epoch, and movement after server restart.')
                    await browser.close()
                    browser = None
            finally:
                # The Playwright context may already have closed the browser
                # after a failed assertion; authority cleanup must still run.
                try:
                    if browser is not None:
                        await browser.close()
                finally:
                    await stop(server)


if __name__ == '__main__':
    asyncio.run(run())
