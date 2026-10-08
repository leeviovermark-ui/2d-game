"""Exercise Stage 2 through two real exported Godot clients.

Controls are located through an opt-in, read-only rectangle inspector. Tests
click/type into the real canvas; no account, social, craft or movement requests
are injected. The temporary server's saved terrain supplies nearby stations.
Recovery codes stay in memory and are never photographed or printed.
"""
import asyncio
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

from playwright.async_api import async_playwright
from browser_smoke import ARTIFACTS, Client, ROOT

sys.path.insert(0, str(ROOT))
from server.storage import Store

PASSWORD = 'stage-two-browser-password'
NEW_PASSWORD = 'stage-two-changed-password'
RESET_PASSWORD = 'stage-two-recovered-password'


def active_sessions(database,ident):
    with sqlite3.connect(database) as db:
        return db.execute('SELECT count(*) FROM sessions WHERE account=? AND expires>?',
                          (ident,time.time())).fetchone()[0]


def fixture(database):
    """Saved world data, with no synthetic accounts or granted inventories."""
    store = Store(database)
    try:
        for x,y,item in [(8,20,'water'),(9,20,'loom'),(10,20,'cooking_pot')]:
            store.tile('NEXUS',x,y,item)
        # A mature saved plant checks generalized harvest rewards without
        # shortening the production growth timer or changing the game clock.
        store.tile('NEXUS',12,20,'carrot_crop')
        store.db.execute('INSERT INTO crops(world,x,y,planted) VALUES(?,?,?,?)',
                         ('NEXUS',12,20,time.time()-110))
    finally:
        store.close()


async def start(client,url,shot=None):
    await client.page.add_init_script('window.worldforge_inspect = true;')
    if shot:
        async def slower_download(route):
            await asyncio.sleep(1)
            await route.continue_()
        await client.page.route('**/index.wasm',slower_download)
    await client.page.goto(url,wait_until='domcontentloaded')
    if shot:
        await client.page.screenshot(path=str(ARTIFACTS/'stage2-boot-loading.png'))
    await client.control(kind='Button',text='Play WORLDFORGE  →',timeout=25)
    if shot: await client.page.screenshot(path=str(ARTIFACTS/shot))
    await client.click('Play WORLDFORGE  →',kind='Button')


async def label_contains(client,text,timeout=8):
    await client.control(kind='Label',contains=text,timeout=timeout)


async def open_account(client):
    await client.key('Escape')
    await client.click('Settings',kind='Button')
    await client.click('Account & saved sessions',kind='Button')
    await client.control(kind='LineEdit',placeholder='Required to change account security')


async def signed_out_form(client):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        texts={c.get('text') for c in await client.controls() if c.get('kind')=='Button'}
        if 'Play WORLDFORGE  →' in texts:
            await client.click('Play WORLDFORGE  →',kind='Button')
            return
        if 'I have a recovery code' in texts:
            return
        await asyncio.sleep(.1)
    raise AssertionError('Explicit logout did not return to the account entry screen')


async def travel(client,world):
    await client.key('Escape')
    await client.key('m')
    await client.fill(world,placeholder='Search worlds or their founders')
    await client.click('Visit  →',kind='Button')
    await client.wait(lambda:client.world['meta']['name']==world,'UI travel to '+world)
    await asyncio.sleep(.5)


async def grant(client,item,amount):
    await client.fill(item,placeholder='Search by name or item ID…')
    listing=await client.control(kind='ItemList')
    assert len(listing.get('items',[])) == 1, 'Admin item ID should produce an exact fixture selection'
    r=listing['rect']
    await client.page.mouse.click(r['x']+r['w']*.4,r['y']+22)
    await asyncio.sleep(.15)
    spin=await client.control(kind='SpinBox')
    r=spin['rect']
    await client.page.mouse.click(r['x']+r['w']*.45,r['y']+r['h']/2)
    await client.page.keyboard.press('Control+a')
    await client.page.keyboard.type(str(amount))
    await client.page.keyboard.press('Enter')
    before=client.quantity(item)
    await client.click('Give selected item',kind='Button')
    await client.wait(lambda:client.quantity(item)==before+amount,'admin fixture grant '+item)


async def craft(client,title,output,queued=False):
    await client.key('Escape')
    await client.key('c')
    await client.fill(title,placeholder='Find a recipe, material, or station')
    before=client.quantity(output)
    marker=len(client.messages)
    await client.click('Queue batch' if queued else 'Craft',kind='Button')
    if queued:
        await client.wait(lambda:any(m['type']=='open_machine' for m in client.messages[marker:]),'queue real '+title+' recipe')
    else:
        await client.wait(lambda:client.quantity(output)>before,'craft real '+title+' recipe')


async def move_to_hotbar(client,item,slot=0):
    await client.key('Escape')
    await client.key('i')
    index=next(i for i,s in enumerate(client.inventory) if s and s['id']==item)
    controls=await client.controls()
    slots=[c for c in controls if 'slot_index' in c and not c.get('hotbar',False)]
    assert len(slots)==30, 'Inspector must include the thirty real backpack controls'
    source=next(c for c in slots if c['slot_index']==index)['rect']
    destination=next(c for c in slots if c['slot_index']==slot)['rect']
    await client.page.mouse.move(source['x']+source['w']/2,source['y']+source['h']/2)
    await client.page.mouse.down()
    await client.page.mouse.move(destination['x']+destination['w']/2,destination['y']+destination['h']/2,steps=12)
    await client.page.mouse.up()
    await client.wait(lambda:client.inventory[slot] and client.inventory[slot]['id']==item,'drag '+item+' into hotbar')
    await client.key('Escape')
    await client.key(str((slot+1)%10))


async def run():
    ARTIFACTS.mkdir(exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='worldforge-stage2-') as temp:
        database=Path(temp)/'stage2.sqlite3'
        fixture(database)
        with open(Path(temp)/'server.log','w') as log:
            server=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-m','server.main','--port',str(port),
                '--database',str(database),'--admin','Aster'],cwd=ROOT,stdout=log,stderr=log)
            try:
                await asyncio.sleep(.6)
                async with async_playwright() as playwright:
                    browser=await playwright.chromium.launch(executable_path='/usr/bin/chromium',headless=True,
                        args=['--no-sandbox','--enable-unsafe-swiftshader'])
                    a=Client(await browser.new_page(viewport={'width':1440,'height':900}))
                    b=Client(await browser.new_page(viewport={'width':1440,'height':900}))
                    url='http://127.0.0.1:'+str(port)
                    await start(a,url,'stage2-title.png')
                    await a.fill('Aster',placeholder='Start with a letter · 3–20 characters')
                    await a.fill(PASSWORD,placeholder='At least 8 characters')
                    await a.fill(PASSWORD+'-mismatch',placeholder='Confirm password')
                    await a.click('Create account & play  →',kind='Button')
                    await label_contains(a,'Those passwords do not match')
                    assert a.id is None, 'Mismatched confirmation reached registration authority'
                    await a.page.set_viewport_size({'width':1280,'height':720})
                    await a.page.wait_for_function("() => (window.worldforge_controls || []).some(c => c.text === 'Create account & play  →' && c.rect.w < 400)")
                    await a.page.screenshot(path=str(ARTIFACTS/'stage2-signup-720p.png'))
                    await a.page.set_viewport_size({'width':1440,'height':900})
                    await a.page.wait_for_function("() => (window.worldforge_controls || []).some(c => c.text === 'Create account & play  →' && c.rect.w > 400)")
                    await a.fill(PASSWORD,placeholder='Confirm password')
                    await a.click('Create account & play  →',kind='Button')
                    await a.wait(lambda:a.id is not None,'real Stage 2 registration')
                    recovery=a.last['welcome']['recovery_code']
                    assert recovery, 'New registration did not receive a recovery code'
                    await a.dismiss_recovery()
                    await a.page.set_viewport_size({'width':1440,'height':900})
                    await a.wait(lambda:len(a.players)>0,'authenticated first player')
                    await a.key('j')
                    print('Stage 2 QA: signup confirmation, registration, recovery notice and 720p layout passed.',flush=True)

                    # Revoke this temporary account's session, then exercise the
                    # actual Continue button and its visible expiry recovery.
                    with sqlite3.connect(database) as db:
                        db.execute('UPDATE sessions SET expires=0 WHERE account=?',(a.id,))
                    before=sum(m['type']=='welcome' for m in a.messages)
                    marker=len(a.messages)
                    await a.page.reload()
                    await a.click('Continue as Aster',kind='Button',timeout=25)
                    await a.wait(lambda:any(m['type']=='error' for m in a.messages[marker:]),'expired saved-session rejection')
                    await a.click('Sign in',kind='Button')
                    marker=len(a.messages)
                    await a.submit_account('Aster',PASSWORD+'-incorrect')
                    await a.wait(lambda:any(m['type']=='error' for m in a.messages[marker:]),'incorrect password rejection')
                    await a.submit_account('Aster',PASSWORD)
                    await a.wait(lambda:sum(m['type']=='welcome' for m in a.messages)==before+1,'correct sign-in after stale session')
                    expected_errors=[m for m in a.messages if m['type']=='error']
                    assert len(expected_errors)==2, 'Unexpected login rejection during recovery'
                    assert not a.last['welcome'].get('recovery_code'), 'Returning sign-in exposed a registration recovery code'
                    print('Stage 2 QA: expired saved session and wrong-password recovery passed.',flush=True)

                    await start(b,url)
                    await b.submit_account('Briar',PASSWORD,register=True)
                    await b.wait(lambda:b.id is not None,'second real account')
                    await b.dismiss_recovery()
                    await a.wait(lambda:len(a.players)==2,'two-client presence')
                    await a.key('p')
                    await a.fill('Briar',placeholder='Add a friend by explorer name')
                    await a.click('Send request',kind='Button')
                    await b.wait(lambda:len(b.last.get('social_state',{}).get('incoming',[]))==1,'incoming friend request')
                    await b.key('p')
                    await b.click(kind='Button',contains='Requests (1)')
                    await b.click('Accept',kind='Button')
                    await a.wait(lambda:len(a.last.get('social_state',{}).get('friends',[]))==1,'accepted friendship on sender')
                    await b.wait(lambda:len(b.last.get('social_state',{}).get('friends',[]))==1,'accepted friendship on recipient')
                    await a.click('Message',kind='Button')
                    await a.fill('The new horizon looks bright.',placeholder='Write a private message…')
                    await a.click('Send',kind='Button')
                    await b.wait(lambda:b.last.get('private_message',{}).get('text')=='The new horizon looks bright.','cross-client private message')
                    await a.page.screenshot(path=str(ARTIFACTS/'stage2-friends.png'))
                    print('Stage 2 QA: accepted friendship and private messaging passed.',flush=True)

                    # Leave Briar's catalogue open to prove new world entries are
                    # pushed live, rather than appearing only after a refresh.
                    await b.key('Escape')
                    await b.key('m')
                    await a.key('Escape')
                    await a.key('m')
                    await a.fill('HORIZON',placeholder='MY_FIRST_WORLD')
                    await a.choose('NewWorldBiome','Desert · golden dunes')
                    await a.click('Create & enter',kind='Button')
                    await a.wait(lambda:a.world['meta']['name']=='HORIZON','new world creation')
                    await b.wait(lambda:any(w['name']=='HORIZON' for w in b.last.get('directory',{}).get('worlds',[])),'new world pushed into other catalogue')
                    await b.fill('HORIZON',placeholder='Search worlds or their founders')
                    await label_contains(b,'HORIZON')
                    await b.click('☆',kind='Button')
                    await b.wait(lambda:any(w['name']=='HORIZON' and w['favorite'] for w in b.last['directory']['worlds']),'saved catalogue favorite')
                    await b.choose('WorldSort','Favorites')
                    await b.page.screenshot(path=str(ARTIFACTS/'stage2-world-catalogue.png'))
                    await a.key('p')
                    await a.click('Friends',kind='Button')
                    await a.click('Invite here',kind='Button')
                    await b.wait(lambda:b.last.get('world_invite',{}).get('world')=='HORIZON','live world invitation')
                    await b.key('Escape')
                    await b.key('p')
                    await b.click('Visit world',kind='Button')
                    await b.wait(lambda:b.world['meta']['name']=='HORIZON','friend visits invitation through UI')
                    await a.wait(lambda:len(a.players)==2,'both friends in desert world')
                    await a.page.screenshot(path=str(ARTIFACTS/'stage2-multiplayer-desert.png'))
                    await travel(a,'NEXUS')
                    await b.key('p')
                    await b.click('Friends',kind='Button')
                    await b.click('Join',kind='Button')
                    await b.wait(lambda:b.world['meta']['name']=='NEXUS','friend join follows authoritative presence')
                    print('Stage 2 QA: live catalogues, favorites, world invitations and friend joining passed.',flush=True)

                    # Admin fixtures are supplied through the same visible menu
                    # as the player uses; every recipe and mechanic is real UI.
                    await a.key('Enter')
                    await a.page.keyboard.type('/addomen')
                    await a.page.keyboard.press('Enter')
                    await a.wait(lambda:'admin_panel' in a.last,'real administrator menu')
                    await a.choose(None,'Materials')
                    for item,amount in [('rope',2),('iron',1),('grain',6),('cloth',2)]:
                        await grant(a,item,amount)
                    await craft(a,'Willow fishing rod','fishing_rod')
                    await craft(a,'Wayfarer cap','explorer_hat',queued=True)
                    await craft(a,'Sungrain bread','bread',queued=True)
                    await a.control(kind='Button',text='Collect',enabled=True,timeout=9)
                    await a.click('Collect',kind='Button')
                    await a.wait(lambda:a.quantity('bread')==1,'collect timed food workshop job')
                    await a.key('Escape')
                    await a.point(9,20)
                    await a.key('e')
                    await a.control(kind='Button',text='Collect',enabled=True,timeout=9)
                    await a.click('Collect',kind='Button')
                    await a.wait(lambda:a.quantity('explorer_hat')==1,'collect timed wardrobe workshop job')
                    await move_to_hotbar(a,'fishing_rod')
                    await a.point(8,20)
                    await a.key('e')
                    await a.wait(lambda:'fishing_result' in a.last,'visible fishing interaction')
                    await b.wait(lambda:'fish_splash' in b.last,'fishing effect reaches nearby friend')
                    await a.click(kind='Button',contains='Journal  [')
                    await a.click('Equipment & food',kind='Button')
                    await a.click('Wear',kind='Button')
                    await a.wait(lambda:a.last.get('equipment',{}).get('appearance',{}).get('hat')=='explorer_hat','equip crafted wardrobe item')
                    await b.wait(lambda:any(p.get('appearance',{}).get('hat')=='explorer_hat' for p in b.players),'wardrobe synchronizes to another client')
                    await move_to_hotbar(a,'bread',slot=1)
                    await a.page.keyboard.down('Shift')
                    await a.page.keyboard.down('d')
                    await a.wait(lambda:a.position().get('energy',100)<80,'sprint uses authoritative energy',timeout=4)
                    await a.key('f')
                    await a.wait(lambda:a.quantity('bread')==0,'eat crafted food')
                    await a.page.keyboard.up('d')
                    await a.page.keyboard.up('Shift')
                    await a.click(kind='Button',contains='Journal  [')
                    await a.click('Expressions',kind='Button')
                    await a.click(kind='Button',contains='Wave')
                    await b.wait(lambda:b.last.get('emote',{}).get('emote')=='wave','synchronized explorer emote')
                    await a.key('Escape')
                    carrots_before,carrot_seeds_before=a.quantity('carrot'),a.quantity('carrot_seed')
                    await a.point(12,20)
                    await a.key('e')
                    await a.wait(lambda:a.quantity('carrot')==carrots_before+2 and a.quantity('carrot_seed')==carrot_seeds_before+2,'generalized carrot harvest rewards and replenished seeds')
                    # A third distinct world unlocks a real one-time goal reward.
                    await a.key('m')
                    await a.fill('SUNSHORE',placeholder='MY_FIRST_WORLD')
                    await a.click('Create & enter',kind='Button')
                    await a.wait(lambda:a.world['meta']['name']=='SUNSHORE','third explored world')
                    await a.click(kind='Button',contains='Journal  [')
                    await a.click('Goals & rewards',kind='Button')
                    await a.page.mouse.move(900,650)
                    await a.page.mouse.wheel(0,1000)
                    await asyncio.sleep(.3)
                    await a.control(kind='Button',text='Claim reward',enabled=True)
                    await a.click('Claim reward',kind='Button')
                    await a.wait(lambda:a.last.get('progression',{}).get('points')==50,'claim once-only exploration milestone')
                    await a.page.screenshot(path=str(ARTIFACTS/'stage2-journal.png'))
                    print('Stage 2 QA: fishing, food, wardrobe, emotes, harvest and one-time goals passed.',flush=True)

                    # The account UI verifies ownership and keeps this browser's
                    # session active after a password update.
                    await open_account(a)
                    await a.fill(PASSWORD,placeholder='Required to change account security')
                    await a.fill(NEW_PASSWORD,placeholder='At least 8 characters')
                    await a.fill(NEW_PASSWORD,placeholder='Confirm the new password')
                    await a.click('Change password',kind='Button')
                    await a.wait(lambda:a.last.get('account_result',{}).get('action')=='password_change','password change from real account controls')
                    await a.click('Sign out & forget this device',kind='Button')
                    await a.wait(lambda:active_sessions(database,a.id)==0,'explicit logout revoked server session')
                    assert await a.page.evaluate('() => localStorage.getItem("worldforge.session.v2") === null'), 'Logout retained a browser credential'
                    await signed_out_form(a)
                    await a.click('I have a recovery code',kind='Button')
                    await a.fill('Aster',placeholder='Start with a letter · 3–20 characters')
                    await a.fill(recovery,placeholder='The code you saved when creating your account')
                    await a.fill(RESET_PASSWORD,placeholder='At least 8 characters')
                    await a.fill(RESET_PASSWORD,placeholder='Confirm password')
                    await a.click('Reset password',kind='Button')
                    await a.wait(lambda:a.last.get('account_result',{}).get('action')=='recovery_reset','real recovery-code password reset')
                    await a.dismiss_recovery()
                    before=sum(m['type']=='welcome' for m in a.messages)
                    await a.submit_account('Aster',RESET_PASSWORD)
                    await a.wait(lambda:sum(m['type']=='welcome' for m in a.messages)>before,'sign in with recovered password')
                    await open_account(a)
                    await a.click('Sign out & forget this device',kind='Button')
                    await a.wait(lambda:active_sessions(database,a.id)==0,'second explicit logout revoked server session')
                    await signed_out_form(a)
                    await a.click('I have a recovery code',kind='Button')
                    await a.fill('Aster',placeholder='Start with a letter · 3–20 characters')
                    await a.fill(recovery,placeholder='The code you saved when creating your account')
                    await a.fill(NEW_PASSWORD,placeholder='At least 8 characters')
                    await a.fill(NEW_PASSWORD,placeholder='Confirm password')
                    marker=len(a.messages)
                    await a.click('Reset password',kind='Button')
                    await a.wait(lambda:any(m['type']=='error' for m in a.messages[marker:]),'one-use recovery code rejection')
                    errors=[m for m in a.messages if m['type']=='error']
                    assert len(errors)==3, 'Unexpected Stage 2 authority rejection'
                    assert not [m for m in b.messages if m['type']=='error'], 'Unexpected friend client rejection'
                    assert not a.errors and not b.errors, 'Godot browser runtime errors: '+str(a.errors+b.errors)
                    print('PASS: real two-client Stage 2 title/signup/confirmation, stale session and wrong-password recovery, friends/private messages/world invites and joining, live catalogues and favorites, crafted fishing rod, timed food and wardrobe jobs, synchronized fishing/equipment/emotes, generalized crop harvest, one-time milestone, password change/logout/recovery reset and one-use rejection; no client runtime errors.')
                    await browser.close()
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__=='__main__':
    asyncio.run(run())
