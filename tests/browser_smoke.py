"""Operate two exported Godot clients in Chromium against a temporary real server.

Run with the cloud's system Python (playwright is supplied by the image).
No secrets or credentials are printed. Screenshots are local generated artifacts.
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT/'artifacts'


class Client:
    def __init__(self,page):
        self.page = page
        self.messages = []
        self.errors = []
        self.inventory = []
        self.players = []
        self.id = None
        self.world = None
        self.last = {}
        page.on('console',lambda m: self.errors.append(m.text) if m.type == 'error' else None)
        page.on('pageerror',lambda e:self.errors.append(str(e)))
        page.on('websocket',lambda ws: ws.on('framereceived',self.packet))

    def packet(self,raw):
        if not isinstance(raw,str): return
        m = json.loads(raw)
        self.messages.append(m)
        self.last[m['type']] = m
        if m['type'] == 'welcome':
            self.id,self.inventory,self.world = m['id'],m['slots'],m['world']
        elif m['type'] == 'inventory': self.inventory = m['slots']
        elif m['type'] == 'players': self.players = m['players']
        elif m['type'] == 'world': self.world = m['world']

    async def wait(self,predicate,description,timeout=8):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate(): return
            await asyncio.sleep(.05)
        await self.page.screenshot(path=str(ARTIFACTS/'smoke-failure.png'))
        raise AssertionError('Timed out: '+description+'; runtime errors: '+str(self.errors)+'; server errors: '+str([m['text'] for m in self.messages if m['type']=='error']))

    async def login(self,url,name):
        await self.page.goto(url)
        await asyncio.sleep(3)
        await self.page.mouse.click(1110,324)
        await self.page.keyboard.type(name)
        await self.page.mouse.click(1110,397)
        await self.page.keyboard.type('browser-smoke-password')
        await self.page.mouse.click(1120,562)
        await self.wait(lambda:self.id is not None,'Godot account creation')
        await self.wait(lambda:len(self.players)>0,'Godot player snapshot')
        await asyncio.sleep(.6)

    async def key(self,key):
        await self.page.keyboard.press(key)
        await asyncio.sleep(.25)

    async def move(self,key,seconds):
        await self.page.keyboard.down(key)
        await asyncio.sleep(seconds)
        await self.page.keyboard.up(key)
        await asyncio.sleep(.65)

    def position(self):
        return next(p for p in self.players if p['id']==self.id)

    def tile_screen(self,x,y):
        p = self.position()
        cam_x = max(0,p['x']*32-1400*.44)
        cam_y = max(0,p['y']*32-642*.64)
        return 20+(x+.5)*32-cam_x,94+(y+.5)*32-cam_y

    async def point(self,x,y):
        await self.page.mouse.move(*self.tile_screen(x,y))
        await asyncio.sleep(.15)

    def quantity(self,item):
        return sum(s['n'] for s in self.inventory if s and s['id']==item)


async def run():
    ARTIFACTS.mkdir(exist_ok=True)
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        port = s.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='worldforge-browser-') as temp:
        log = open(Path(temp)/'server.log','w')
        executable = ROOT/'.venv/bin/python'
        server = subprocess.Popen([str(executable),'-m','server.main','--port',str(port),'--database',str(Path(temp)/'test.sqlite3')],cwd=ROOT,stdout=log,stderr=log)
        try:
            await asyncio.sleep(.6)
            async with async_playwright() as p:
                browser = await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
                a = Client(await browser.new_page(viewport={'width':1440,'height':900}))
                b = Client(await browser.new_page(viewport={'width':1440,'height':900}))
                url = 'http://127.0.0.1:'+str(port)
                await a.login(url,'Aster')
                await b.login(url,'Briar')
                await a.wait(lambda:len(a.players)==2,'both real players synchronized')
                await b.move('a',.55)
                assert b.position()['x']<10.5, 'Movement input did not reach the server'
                await a.key('j')  # Keep terrain targeting clear of the field-notes panel.
                await a.key('2')
                await a.point(12,20)
                await a.page.mouse.click(*a.tile_screen(12,20),button='right')
                await a.wait(lambda:a.quantity('dirt')==23,'validated block placement')
                await b.wait(lambda:any(m['type']=='tile' and m.get('item')=='dirt' and m.get('x')==12 for m in b.messages),'block delta reached second client')
                await a.key('4')
                await a.point(10,20)
                await a.page.mouse.click(*a.tile_screen(10,20),button='right')
                await a.wait(lambda:a.quantity('seed')==7,'crop planted')
                await a.page.screenshot(path=str(ARTIFACTS/'two-player-gameplay.png'))
                await a.key('i')
                # Full-stack drag, followed by a right-click to split into an empty slot.
                await a.page.mouse.move(495,369)
                await a.page.mouse.down()
                await a.page.mouse.move(433,431,steps=15)
                await a.page.mouse.up()
                await a.wait(lambda:a.inventory[10] and a.inventory[10]['n']==23,'inventory drag/drop')
                await a.page.mouse.click(433,431,button='right')
                await a.wait(lambda:a.inventory[11] and a.inventory[11]['n']==12,'inventory stack splitting')
                assert a.inventory[10]['n']==11
                await a.page.screenshot(path=str(ARTIFACTS/'inventory.png'))
                await a.key('Escape')
                await a.key('c')
                await a.page.screenshot(path=str(ARTIFACTS/'crafting.png'))
                before = a.quantity('planks')
                await a.page.mouse.click(980,282)
                await a.wait(lambda:a.quantity('planks')==before+4,'craft button produces real items')
                await a.key('Escape')
                await a.move('d',.16)
                await a.point(16,20)
                await a.key('e')
                await a.wait(lambda:'storage' in a.last,'open persistent chest')
                wood_before = a.quantity('wood')
                await a.page.mouse.click(690,496)  # Deposit backpack wood stack.
                await a.wait(lambda:a.quantity('wood')==0,'atomic storage deposit')
                await a.page.mouse.click(443,336)  # Withdraw first chest slot.
                await a.wait(lambda:a.quantity('wood')==wood_before,'atomic storage withdrawal')
                await a.page.screenshot(path=str(ARTIFACTS/'storage.png'))
                await a.key('Escape')
                await a.key('m')
                await a.wait(lambda:'directory' in a.last,'world directory')
                await a.page.screenshot(path=str(ARTIFACTS/'worlds.png'))
                await a.key('Escape')
                await a.key('p')
                await a.page.screenshot(path=str(ARTIFACTS/'social.png'))
                await a.page.mouse.click(791,362)
                await b.wait(lambda:'trade_invite' in b.last,'trade invite to real second client')
                await b.page.mouse.click(1220,132)
                await a.wait(lambda:'trade' in a.last,'trade accepted by second client')
                await b.wait(lambda:'trade' in b.last,'both trade screens')
                await asyncio.sleep(.3)
                await a.page.screenshot(path=str(ARTIFACTS/'trade.png'))
                await a.page.mouse.click(780,431)
                await a.wait(lambda:a.last['trade']['trade']['offers'][a.id]=={'wood_pick':1},'set exact pickaxe offer')
                await b.page.mouse.click(515,431)
                await b.page.keyboard.press('Home')
                for _ in range(3): await b.page.keyboard.press('ArrowDown')
                await b.page.keyboard.press('Enter')
                await b.page.mouse.click(780,431)
                await b.wait(lambda:b.last['trade']['trade']['offers'][b.id]=={'planks':1},'set exact planks offer')
                a_pick,a_planks = a.quantity('wood_pick'),a.quantity('planks')
                await a.page.mouse.click(555,480)
                await a.wait(lambda:a.id in a.last['trade']['trade']['locked'],'first trade lock')
                await b.page.mouse.click(555,480)
                await b.wait(lambda:len(b.last['trade']['trade']['locked'])==2,'second trade lock')
                await a.page.mouse.click(690,480)
                await b.wait(lambda:a.id in b.last['trade']['trade']['confirmed'],'first trade confirmation')
                await b.page.mouse.click(690,501)
                await a.wait(lambda:'trade_closed' in a.last,'atomic browser trade exchange')
                assert a.quantity('wood_pick')==a_pick-1 and a.quantity('planks')==a_planks+1
                await a.key('Escape')
                # The world form and Core permissions must operate through the real UI.
                await a.key('m')
                await a.page.mouse.click(700,590)
                await a.page.keyboard.type('HOME')
                await a.page.mouse.click(720,690)
                await a.wait(lambda:a.world['meta']['name']=='HOME','create and travel to named world')
                await asyncio.sleep(.8)
                await a.key('8')
                await a.point(12,20)
                await a.page.mouse.click(*a.tile_screen(12,20),button='right')
                await a.wait(lambda:a.last.get('metadata',{}).get('meta',{}).get('owner')==a.id,'claim with World Core')
                await a.point(12,20)
                await a.key('e')
                await a.wait(lambda:'open_permissions' in a.last,'open World Core permissions')
                await a.page.screenshot(path=str(ARTIFACTS/'permissions.png'))
                await a.page.mouse.click(700,452)
                await a.page.keyboard.type('Briar')
                await a.page.mouse.click(720,503)
                await a.wait(lambda:b.id in a.last['metadata']['meta']['builders'],'save builder permission')
                await a.key('Escape')
                await b.key('m')
                await asyncio.sleep(.4)
                await b.page.mouse.click(997,278)  # HOME sorts before NEXUS.
                await b.wait(lambda:b.world['meta']['name']=='HOME','second player world travel')
                await a.wait(lambda:len(a.players)==2,'both players in newly claimed world')
                await a.page.screenshot(path=str(ARTIFACTS/'claimed-world.png'))
                await a.key('m')
                await asyncio.sleep(.4)
                await a.page.mouse.click(997,320)
                await a.wait(lambda:a.world['meta']['name']=='NEXUS','return to persistent planted world')
                await asyncio.sleep(.8)
                # Mine through mouse input; then jump over the placed block and collect.
                await a.point(13,21)
                await a.page.mouse.down()
                await asyncio.sleep(.7)
                await a.page.mouse.up()
                await a.wait(lambda:any(m['type']=='tile' and m.get('item') is None and m.get('x')==13 for m in a.messages),'server-timed mining in Godot')
                dirt_before = a.quantity('dirt')
                await a.page.keyboard.down('d')
                await a.page.keyboard.down('Space')
                await asyncio.sleep(.25)
                await a.page.keyboard.up('Space')
                await asyncio.sleep(.30)
                await a.page.keyboard.up('d')
                await a.wait(lambda:a.quantity('dirt')==dirt_before+1,'collect mined item after jumping')
                planted = next(m['planted'] for m in a.messages if m['type']=='tile' and m.get('item')=='crop')
                await a.wait(lambda:time.time()>planted+90.2,'real crop growth while world was unloaded',timeout=92)
                await asyncio.sleep(.8)
                await a.point(10,20)
                await a.key('e')
                await a.wait(lambda:a.quantity('grain')==3,'harvest mature crop through Godot UI')
                await a.page.screenshot(path=str(ARTIFACTS/'harvest.png'))
                await a.key('Enter')
                await a.page.keyboard.type('A little world, a shared adventure.')
                await a.page.keyboard.press('Enter')
                # Return Briar to NEXUS before checking world-scoped chat delivery.
                await b.key('m')
                await asyncio.sleep(.4)
                await b.page.mouse.click(997,320)
                await b.wait(lambda:b.world['meta']['name']=='NEXUS','second client returns to shared refuge')
                await a.key('Enter')
                await a.page.keyboard.type('Welcome back to the meadow.')
                await a.page.keyboard.press('Enter')
                await b.wait(lambda:any(m['type']=='chat' and m.get('name')=='Aster' for m in b.messages),'world chat reached second client')
                # Reconnect using Godot's persisted bearer session (the server owns saves).
                saved_inventory = a.inventory.copy()
                await a.page.reload()
                await asyncio.sleep(3)
                await a.page.screenshot(path=str(ARTIFACTS/'reconnect.png'))
                # Resume is the last form button; current column puts it at y=674.
                await a.page.mouse.click(1140,659)
                await a.wait(lambda:len(a.last.get('welcome',{}).get('slots',[]))==30 and len([m for m in a.messages if m['type']=='welcome'])==2,'saved-session reconnect')
                assert a.inventory == saved_inventory, 'Inventory did not persist across browser reload'
                assert not a.errors and not b.errors, 'Godot browser runtime errors: '+str(a.errors+b.errors)
                assert not [m for m in a.messages+b.messages if m['type']=='error'], 'Unexpected server rejection'
                print('PASS: two Godot Web clients, movement/jump, mining/pickup, synchronized placement, real crop growth/harvest, drag/split, crafting, storage transfers, secure trading, world creation/travel/claim/permissions, chat, reconnect, saved inventory, and no runtime errors.')
                await browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)
            log.close()


if __name__ == '__main__':
    asyncio.run(run())
