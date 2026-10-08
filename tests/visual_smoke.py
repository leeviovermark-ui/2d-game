"""Capture the upgraded renderer in real exported Godot clients.

Each run creates a temporary saved-world fixture. It never changes a player's
real database. A real admin opens /addomen and grants a new lamp through the UI;
world travel uses the same authenticated WebSocket requests as the travel form.
Run after scripts/export_web.sh with the cloud's system Python.
"""
import asyncio
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import uuid

from playwright.async_api import async_playwright
from browser_smoke import ARTIFACTS, Client, ROOT

sys.path.insert(0, str(ROOT))
from server.storage import Store


def seed_showcase(path):
    store = Store(path)
    try:
        for name, biome in [('GARDEN', 'forest'), ('DUNES', 'desert'), ('FROST', 'snow')]:
            store.create_world(name, biome, seed=71051)
            # This is fixture saved build data, not a change to the seeded generator.
            for x in range(14, 22):
                store.tile(name, x, 16, 'blue_planks')
                store.tile(name, x, 21, 'moss_brick')
            for y in range(17, 21):
                store.tile(name, 14, y, 'red_planks')
            for y in range(17, 20):
                store.tile(name, 21, y, 'reinforced_glass')
            for x,y,item in [(15,19,'bookshelf'), (17,20,'table'), (19,20,'chair'),
                             (17,17,'tapestry'), (18,19,'flower_pot'), (20,19,'iron_lantern'),
                             (17,19,'lumen_lamp'), (22,20,'hedge'), (23,20,'hedge'),
                             (12,20,'flower_pot')]:
                store.tile(name, x, y, item)
            for x,item in enumerate(['slate_brick','sandstone_brick','marble','terracotta','green_planks'], start=22):
                store.tile(name, x, 21, item)
        deep = store.create_world('DEEP', 'forest', seed=71051)
        deep.meta['spawn'] = [11.5, 37.44]
        store.save_meta(deep.meta)
        for x in range(5, 20):
            for y in range(32, 39):
                store.tile('DEEP', x, y, None)
            store.tile('DEEP', x, 39, 'slate_brick')
        for x,y,item in [(7,37,'iron_lantern'),(15,37,'lumen_lamp'),(16,38,'bench'),(17,38,'chest'),(12,38,'rug')]:
            store.tile('DEEP', x, y, item)
    finally:
        store.close()


async def protocol(page, kind, **fields):
    packet = dict(type=kind, request=uuid.uuid4().hex, **fields)
    await page.evaluate('(packet) => window.__forgeSocket.send(JSON.stringify(packet))', packet)


async def run():
    ARTIFACTS.mkdir(exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='worldforge-visual-') as temp:
        database = Path(temp)/'visual.sqlite3'
        seed_showcase(database)
        with open(Path(temp)/'server.log','w') as log:
            server = subprocess.Popen([str(ROOT/'.venv/bin/python'),'-m','server.main',
                '--port',str(port),'--database',str(database),'--admin','Showcase'],cwd=ROOT,stdout=log,stderr=log)
            try:
                await asyncio.sleep(.6)
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(executable_path='/usr/bin/chromium',headless=True,
                        args=['--no-sandbox','--enable-unsafe-swiftshader'])
                    page = await browser.new_page(viewport={'width':1440,'height':900})
                    await page.add_init_script('''(() => {
                        const Original = window.WebSocket;
                        window.WebSocket = new Proxy(Original, {construct(target, args) {
                            const socket = new target(...args);
                            window.__forgeSocket = socket;
                            return socket;
                        }});
                    })();''')
                    client = Client(page)
                    await client.login('http://127.0.0.1:'+str(port),'Showcase')
                    await client.key('j')
                    for world,shot in [('GARDEN','forest'),('DUNES','desert'),('FROST','snow'),('DEEP','cave')]:
                        await protocol(page,'travel',world=world)
                        await client.wait(lambda:client.world['meta']['name']==world,'visual world '+world)
                        await asyncio.sleep(.9)
                        await page.mouse.move(30,78)
                        await page.screenshot(path=str(ARTIFACTS/('upgrade-'+shot+'.png')))
                    await protocol(page,'travel',world='GARDEN')
                    await client.wait(lambda:client.world['meta']['name']=='GARDEN','return to visual garden')
                    await client.key('Enter')
                    await page.keyboard.type('/addomen')
                    await page.keyboard.press('Enter')
                    await client.wait(lambda:'admin_panel' in client.last,'real /addomen admin menu')
                    await asyncio.sleep(.5)
                    await page.screenshot(path=str(ARTIFACTS/'upgrade-catalogue.png'))
                    # The search field and exact catalogue choice exercise procedural
                    # icons and descriptions instead of sending an injected grant.
                    await client.fill('lumen_lamp',placeholder='Search by name or item ID…')
                    listing = await client.control(kind='ItemList')
                    assert len(listing['items']) == 1
                    rect = listing['rect']
                    await page.mouse.click(rect['x']+rect['w']*.4,rect['y']+22)
                    await asyncio.sleep(.2)
                    await page.screenshot(path=str(ARTIFACTS/'upgrade-catalogue-search.png'))
                    before = client.quantity('lumen_lamp')
                    await client.click('Give selected item',kind='Button')
                    await client.wait(lambda:client.quantity('lumen_lamp')>before,'grant new lamp through admin UI')
                    assert not client.errors, 'Browser rendering errors: '+str(client.errors)
                    errors = [m['text'] for m in client.messages if m['type']=='error']
                    assert not errors, 'Server rejections: '+str(errors)
                    print('PASS: forest/desert/snow parallax, saved new building/decor/light items, underground visibility, real /addomen item search and grant, no runtime errors.')
                    await browser.close()
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__ == '__main__':
    asyncio.run(run())
