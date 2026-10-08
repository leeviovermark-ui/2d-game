"""Check browser session persistence and legacy cleanup through real Godot.

Run with the cloud's system Python after exporting the Web client. The regular
game uses real UI authentication and a disposable authority. A separate,
temporary Web export uses actual FileAccess to seed a legacy session fixture;
it never injects game commands or modifies the shipped export.
"""
import asyncio
import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time

from playwright.async_api import async_playwright

from browser_smoke import ARTIFACTS, Client, ROOT

PASSWORD = 'session-browser-password'
CHANGED_PASSWORD = 'session-changed-password'
RESET_PASSWORD = 'session-recovered-password'


def active_sessions(database, ident):
    with sqlite3.connect(database) as db:
        return db.execute('SELECT count(*) FROM sessions WHERE account=? AND expires>?',
                          (ident, time.time())).fetchone()[0]


async def open_account(client):
    await client.key('Escape')
    await client.click('Settings', kind='Button')
    await client.click('Account & saved sessions', kind='Button')
    await client.control(kind='LineEdit', placeholder='Required to change account security')


async def signed_out_form(client):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        buttons = {control.get('text') for control in await client.controls()
                   if control.get('kind') == 'Button'}
        if 'Play WORLDFORGE  →' in buttons:
            await client.click('Play WORLDFORGE  →', kind='Button')
            await client.click('Sign in', kind='Button')
            return
        if 'Sign in & play  →' in buttons:
            return
        if 'Create account & play  →' in buttons:
            await client.click('Sign in', kind='Button')
            return
        await asyncio.sleep(.1)
    raise AssertionError('Logout did not return to an actual account entry screen.')


async def sign_in(client, password):
    before = sum(packet['type'] == 'welcome' for packet in client.messages)
    await client.submit_account('SessionExplorer', password)
    await client.wait(lambda: sum(packet['type'] == 'welcome' for packet in client.messages) > before,
                      'fresh sign-in from actual account form')


async def logout(client, database):
    await open_account(client)
    await client.click('Sign out & forget this device', kind='Button')
    await client.wait(lambda: active_sessions(database, client.id) == 0,
                      'logout revoked the authority session')
    persisted = await client.page.evaluate("() => ({session:localStorage.getItem('worldforge.session.v2'),cleared:localStorage.getItem('worldforge.session.cleared')})")
    assert persisted == {'session': None, 'cleared': '1'}, 'Logout did not synchronously forget the browser session.'


async def idb_session_files(page):
    """Read actual Godot persistence; return filenames only, never contents."""
    return await page.evaluate("""async () => {
        const found = [];
        for (const item of await indexedDB.databases()) {
            if (!item.name) continue;
            const database = await new Promise((resolve,reject) => {
                const request = indexedDB.open(item.name);
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
            });
            try {
                for (const store of database.objectStoreNames) {
                    const keys = await new Promise((resolve,reject) => {
                        const request = database.transaction(store,'readonly').objectStore(store).getAllKeys();
                        request.onsuccess = () => resolve(request.result);
                        request.onerror = () => reject(request.error);
                    });
                    for (const key of keys) if (String(key).endsWith('/session.json')) found.push(String(key));
                }
            } finally { database.close(); }
        }
        return found;
    }""")


async def ordinary_sessions(browser, url, database):
    context = await browser.new_context(viewport={'width':1440,'height':900})
    client = Client(await context.new_page())
    await client.page.add_init_script('window.worldforge_inspect = true;')
    await client.page.goto(url,wait_until='domcontentloaded')
    await client.click('Play WORLDFORGE  →',kind='Button',timeout=30)
    await client.submit_account('SessionExplorer',PASSWORD,register=True)
    await client.wait(lambda: client.id is not None,'registration through the actual account form')
    recovery = client.last['welcome']['recovery_code']
    await client.dismiss_recovery()
    # Inspect metadata without printing a bearer token or recovery code.
    saved = await client.page.evaluate("() => JSON.parse(localStorage.getItem('worldforge.session.v2'))")
    assert set(saved) == {'token','endpoint','name'} and saved['name'] == 'SessionExplorer'
    assert not await idb_session_files(client.page), 'A new browser session wrote a legacy IndexedDB credential file.'

    before = sum(packet['type'] == 'welcome' for packet in client.messages)
    await client.page.reload(wait_until='domcontentloaded')
    await client.click('Continue as SessionExplorer', kind='Button', timeout=30)
    await client.wait(lambda: sum(packet['type'] == 'welcome' for packet in client.messages) > before,
                      'immediate page reload restores the synchronous saved session')
    for _ in range(3):
        await logout(client, database)
        await client.page.reload(wait_until='domcontentloaded')
        await signed_out_form(client)
        assert not any(control.get('text') == 'Continue as SessionExplorer' for control in await client.controls()), 'A forgotten session returned after reload.'
        await sign_in(client, PASSWORD)
        assert not await idb_session_files(client.page), 'Sign-in recreated a browser IndexedDB credential file.'

    await open_account(client)
    await client.fill(PASSWORD, placeholder='Required to change account security')
    await client.fill(CHANGED_PASSWORD, placeholder='At least 8 characters')
    await client.fill(CHANGED_PASSWORD, placeholder='Confirm the new password')
    await client.click('Change password', kind='Button')
    await client.wait(lambda: client.last.get('account_result',{}).get('action') == 'password_change',
                      'password change preserves the current browser session')
    await logout(client, database)
    await signed_out_form(client)
    await client.click('I have a recovery code', kind='Button')
    await client.fill('SessionExplorer', placeholder='Start with a letter · 3–20 characters')
    await client.fill(recovery, placeholder='The code you saved when creating your account')
    await client.fill(RESET_PASSWORD, placeholder='At least 8 characters')
    await client.fill(RESET_PASSWORD, placeholder='Confirm password')
    await client.click('Reset password', kind='Button')
    await client.wait(lambda: client.last.get('account_result',{}).get('action') == 'recovery_reset',
                      'recovery reset completes without an IndexedDB race')
    await client.dismiss_recovery()
    await sign_in(client, RESET_PASSWORD)
    await logout(client, database)
    await client.page.reload(wait_until='domcontentloaded')
    await client.control(kind='Button', text='Play WORLDFORGE  →', timeout=30)
    await asyncio.sleep(2)
    assert not await idb_session_files(client.page), 'Web account operations created a session file.'
    assert not client.errors, 'Browser runtime errors: ' + str(client.errors)
    assert not [packet for packet in client.messages if packet['type'] == 'error'], 'Unexpected account rejection.'
    await context.close()
    print('Session QA: immediate Continue, repeated logout/reload/sign-in, password change, recovery reset, and zero new IndexedDB credentials passed.', flush=True)


async def blocked_storage(browser, url):
    context = await browser.new_context(viewport={'width':1440,'height':900})
    await context.add_init_script("""window.worldforge_inspect = true;
        Storage.prototype.getItem = function(){throw new DOMException('Storage unavailable','SecurityError');};
        Storage.prototype.setItem = function(){throw new DOMException('Storage unavailable','SecurityError');};
        Storage.prototype.removeItem = function(){throw new DOMException('Storage unavailable','SecurityError');};""")
    client = Client(await context.new_page())
    await client.page.goto(url, wait_until='domcontentloaded')
    await client.click('Play WORLDFORGE  →', kind='Button', timeout=30)
    await client.submit_account('StorageExplorer', PASSWORD, register=True)
    await client.wait(lambda: client.id is not None, 'registration works with browser storage disabled')
    await client.dismiss_recovery()
    await client.control(kind='Label', contains='This browser cannot remember your sign-in')
    await client.wait(lambda: len(client.players) > 0,'storage-disabled player receives actual world snapshots')
    starting_x = client.position()['x']
    await client.move('d',.3)
    assert client.position()['x'] > starting_x + .4, 'Storage-disabled session could not actually play.'
    assert not await idb_session_files(client.page), 'Disabled localStorage fell back to browser credential files.'
    await client.page.reload(wait_until='domcontentloaded')
    await client.control(kind='Button', text='Play WORLDFORGE  →', timeout=30)
    assert not any(control.get('text','').startswith('Continue as') for control in await client.controls()), 'Disabled storage restored a session.'
    assert not client.errors, 'Storage-disabled browser runtime errors: ' + str(client.errors)
    await context.close()
    print('Session QA: disabled browser storage fails closed with helpful feedback and no filesystem fallback.', flush=True)


FIXTURE_SCRIPT = '''extends Node
var ui
func _ready() -> void:
    var seeded = JavaScriptBridge.eval("localStorage.getItem('worldforge.fixture.seeded') === '1'",true)
    if not seeded:
        var host = str(JavaScriptBridge.eval("window.location.host"))
        var file := FileAccess.open("user://session.json",FileAccess.WRITE)
        file.store_string(JSON.stringify({"token":"legacy-fixture-token","endpoint":"ws://"+host,"name":"LegacyExplorer"}))
        file.close()
    ui = load("res://client/ui.gd").new()
    ui.state = ForgeState.new()
    ui.art = ForgeArt.new()
    add_child(ui)
    await get_tree().process_frame
    var checks := {}
    if not seeded:
        checks.migrated = ui.load_session().get("token") == "legacy-fixture-token"
        checks.scrubbed = FileAccess.get_file_as_string("user://session.json").strip_edges() == "{}"
        ui.clear_session()
        checks.forgotten = ui.load_session().is_empty()
        for count in range(8):
            ui.remember_session = true
            ui.state.player_name = "LegacyExplorer"
            ui.save_session("new-fixture-token","ws://"+str(JavaScriptBridge.eval("window.location.host")))
            ui.clear_session()
        checks.stable_path = FileAccess.file_exists("user://session.json") and FileAccess.get_file_as_string("user://session.json").strip_edges() == "{}"
        JavaScriptBridge.eval("localStorage.setItem('worldforge.fixture.seeded','1')")
    else:
        checks.no_resurrection = ui.load_session().is_empty()
        checks.legacy_empty = FileAccess.get_file_as_string("user://session.json").strip_edges() == "{}"
    JavaScriptBridge.eval("window.worldforge_session_fixture="+JSON.stringify(checks))
'''


def export_fixture(temp):
    """Export an isolated test project with the real client and a file fixture."""
    project = temp / 'fixture-project'
    project.mkdir()
    for directory in ('client','assets','shared'):
        shutil.copytree(ROOT / directory, project / directory)
    project.joinpath('.tools').symlink_to(ROOT / '.tools', target_is_directory=True)
    configuration = ROOT.joinpath('project.godot').read_text()
    project.joinpath('project.godot').write_text(configuration.replace('res://client/main.tscn','res://session_fixture.tscn'))
    project.joinpath('export_presets.cfg').write_text(ROOT.joinpath('export_presets.cfg').read_text())
    project.joinpath('session_fixture.gd').write_text(FIXTURE_SCRIPT)
    project.joinpath('session_fixture.tscn').write_text('[gd_scene load_steps=2 format=3]\n\n[ext_resource type="Script" path="res://session_fixture.gd" id="1"]\n\n[node name="SessionFixture" type="Node"]\nscript = ExtResource("1")\n')
    web = temp / 'fixture-web'
    web.mkdir()
    environment = {**os.environ,'XDG_DATA_HOME':str(temp / 'xdg-data'),
                   'XDG_CONFIG_HOME':str(temp / 'xdg-config'),'XDG_CACHE_HOME':str(temp / 'xdg-cache')}
    executable = shutil.which('godot')
    assert executable, 'Godot is required for the actual legacy-file Web fixture.'
    for arguments in (['--editor','--import','--quit'], ['--export-release','Web',str(web / 'index.html')]):
        result = subprocess.run([executable,'--headless','--path',str(project),*arguments],
                                capture_output=True,text=True,env=environment,timeout=90)
        output = result.stdout + result.stderr
        assert result.returncode == 0 and 'SCRIPT ERROR' not in output and '\nERROR:' not in output, 'Legacy fixture export failed: ' + output
    return web


class QuietHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy','same-origin')
        self.send_header('Cross-Origin-Embedder-Policy','require-corp')
        super().end_headers()

    def log_message(self, *_args):
        pass


async def legacy_fixture(browser, web):
    handler = functools.partial(QuietHandler, directory=str(web))
    server = ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        context = await browser.new_context(viewport={'width':1440,'height':900})
        client = Client(await context.new_page())
        url = 'http://127.0.0.1:' + str(server.server_port)
        await client.page.goto(url,wait_until='domcontentloaded')
        try:
            await client.page.wait_for_function('() => !!window.worldforge_session_fixture', timeout=30000)
        except Exception as error:
            body = await client.page.locator('body').inner_text()
            raise AssertionError('Legacy fixture did not start. Runtime errors: ' + str(client.errors) + '; page feedback: ' + body) from error
        checks = await client.page.evaluate('() => window.worldforge_session_fixture')
        assert checks and all(checks.values()), 'Legacy migration, cleanup, or logout failed.'
        # Let the real Godot IDB writer flush the stable, empty file.
        deadline = time.monotonic() + 12
        while not await idb_session_files(client.page) and time.monotonic() < deadline:
            await asyncio.sleep(.25)
        assert await idb_session_files(client.page), 'Legacy test file did not reach the actual browser filesystem.'
        await asyncio.sleep(1)
        await client.page.evaluate("() => {localStorage.removeItem('worldforge.session.v2');localStorage.removeItem('worldforge.session.cleared');}")
        await client.page.reload(wait_until='domcontentloaded')
        await client.page.wait_for_function('() => !!window.worldforge_session_fixture',timeout=30000)
        checks = await client.page.evaluate('() => window.worldforge_session_fixture')
        assert checks and all(checks.values()), 'A legacy credential returned after logout and browser reload.'
        assert not client.errors, 'Legacy browser filesystem errors: ' + str(client.errors)
        await context.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    print('Session QA: actual Godot legacy-file migration, stable credential erasure, repeated saves/logout, IDB flush, and reload without resurrection passed.',flush=True)


async def run(check='all'):
    ARTIFACTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='worldforge-session-browser-') as directory:
        temp = Path(directory)
        web = await asyncio.to_thread(export_fixture,temp)
        with socket.socket() as selected:
            selected.bind(('127.0.0.1',0))
            port = selected.getsockname()[1]
        database = temp / 'sessions.sqlite3'
        with temp.joinpath('server.log').open('w') as log:
            authority = subprocess.Popen([str(ROOT / '.venv/bin/python'),'-m','server.main','--port',str(port),'--database',str(database)],cwd=ROOT,stdout=log,stderr=log)
            try:
                await asyncio.sleep(.6)
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
                    url = 'http://127.0.0.1:' + str(port)
                    if check == 'all': await ordinary_sessions(browser,url,database)
                    if check in ('all','safety'): await blocked_storage(browser,url)
                    await legacy_fixture(browser,web)
                    await browser.close()
                description = {'all':'browser account lifecycle, storage failure, and legacy filesystem',
                               'safety':'browser storage failure and legacy filesystem',
                               'fixture':'legacy browser filesystem'}[check]
                print('PASS: ' + description + ' checks; no browser runtime errors.',flush=True)
            finally:
                authority.terminate()
                authority.wait(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',choices=('all','safety','fixture'),default='all')
    asyncio.run(run(parser.parse_args().check))
