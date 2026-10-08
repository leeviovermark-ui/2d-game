"""Two real WebSocket clients: auth, synchronized deltas, attacks, and restart."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
import uuid
import socket
import subprocess
import sys
from server.definitions import ROOT
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from server.game import Game
from server.main import Gateway, http_request
from server.storage import Store


class NetworkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'network.sqlite3'
        self.clients = []
        self.accounts = {}
        await self.start()

    async def start(self):
        self.store = Store(self.path)
        self.gateway = Gateway(Game(self.store))
        self.server = await serve(self.gateway.connection,'127.0.0.1',0,max_size=16384,process_request=http_request)
        self.port = self.server.sockets[0].getsockname()[1]
        self.ticks = asyncio.create_task(self.gateway.run_ticks())

    async def stop(self):
        for ws in self.clients:
            await ws.close()
        self.clients.clear()
        self.server.close()
        await self.server.wait_closed()
        self.ticks.cancel()
        try: await self.ticks
        except asyncio.CancelledError: pass
        self.store.close()

    async def asyncTearDown(self):
        await self.stop()
        self.temp.cleanup()

    async def receive(self, ws, kind, predicate=lambda value: True):
        async def wait():
            for _ in range(150):
                value = json.loads(await ws.recv())
                if value.get('type') == kind and predicate(value):
                    return value
                if value.get('type') == 'error' and kind != 'error':
                    self.fail(value['text'])
            self.fail('No '+kind+' received')
        return await asyncio.wait_for(wait(),4)

    async def auth(self,name=None,token=None):
        ws = await connect('ws://127.0.0.1:'+str(self.port),max_size=2**22)
        self.clients.append(ws)
        data = {'type':'auth','token':token} if token else {'type':'auth','name':name,'password':'network-password','register':True}
        await ws.send(json.dumps(data))
        welcome = await self.receive(ws,'welcome')
        self.accounts[ws] = welcome['id']
        return ws, welcome

    async def command(self,ws,kind,**data):
        request = uuid.uuid4().hex
        if kind in ('trade_offer', 'trade_lock', 'trade_confirm', 'trade_cancel'):
            data.setdefault('trade_id', self.gateway.game.players[self.accounts[ws]]['trade'])
        await ws.send(json.dumps({'type':kind,'request':request,**data}))
        await self.receive(ws,'ack')
        await asyncio.sleep(.1)
        return request

    async def test_two_clients_deltas_chat_reconnect_restart(self):
        a,wa = await self.auth('NetworkA')
        b,wb = await self.auth('NetworkB')
        updates = await self.receive(a,'players',lambda v: len(v['players']) == 2)
        self.assertEqual({p['name'] for p in updates['players']},{'NetworkA','NetworkB'})
        await self.command(a,'select',slot=1)
        await self.command(a,'place',x=12,y=20)
        delta = await self.receive(b,'tile')
        self.assertEqual((delta['x'],delta['y'],delta['item']),(12,20,'dirt'))
        await a.send(json.dumps({'type':'chat','text':'<b>Text stays text</b>'}))
        chat = await self.receive(b,'chat')
        self.assertEqual(chat['text'],'<b>Text stays text</b>')
        await self.command(a,'create_world',world='NETWORK_HOME',biome='forest')
        await self.command(a,'select',slot=7)
        await self.command(a,'place',x=12,y=20)
        await self.command(b,'travel',world='NETWORK_HOME')
        updates = await self.receive(a,'players',lambda v: len(v['players']) == 2)
        self.assertEqual(len(updates['players']),2)
        await self.stop()
        await self.start()
        a,restored = await self.auth(token=wa['token'])
        self.assertEqual(restored['world']['meta']['name'],'NETWORK_HOME')
        self.assertEqual(restored['world']['meta']['owner'],wa['id'])
        self.assertIn([12,20,'core'],restored['world']['tiles'])
        self.assertIsNone(restored['slots'][7])

    async def test_malformed_packets_and_replay_do_not_mutate(self):
        ws,welcome = await self.auth('Attacker')
        await ws.send('{not json')
        self.assertEqual((await self.receive(ws,'error'))['text'],'Malformed request.')
        for packet in [[],{'type':'drop_item','request':uuid.uuid4().hex,'slot':1,'count':-100},
                       {'type':'input','axis':10000,'jump':True}, {'type':'place','request':uuid.uuid4().hex,'x':float('inf'),'y':20}]:
            await ws.send(json.dumps(packet))
            await self.receive(ws,'error')
        request = await self.command(ws,'select',slot=1)
        await ws.send(json.dumps({'type':'select','request':request,'slot':3}))
        self.assertIn('already processed',(await self.receive(ws,'error'))['text'])
        p = self.gateway.game.players[welcome['id']]
        self.assertEqual(p['selected'],1)
        self.assertEqual(p['inventory'][1]['n'],24)
        self.assertLess(p['x'],144)
        updates = await self.receive(ws,'players')
        self.assertEqual(len(updates['players']),1)

    async def test_real_trade_and_disconnect_cancel(self):
        a,wa = await self.auth('TraderA')
        b,wb = await self.auth('TraderB')
        await self.command(a,'trade_request',player=wb['id'])
        await self.receive(b,'trade_invite')
        await self.command(b,'trade_accept',player=wa['id'])
        await self.command(a,'trade_offer',offer={'wood':2})
        await self.command(b,'trade_offer',offer={'dirt':3})
        trade = self.gateway.game.trades[self.gateway.game.players[wa['id']]['trade']]
        rev = trade['revision']
        await self.command(a,'trade_lock',revision=rev)
        await self.command(b,'trade_lock',revision=rev)
        await self.command(a,'trade_confirm',revision=rev)
        await self.command(b,'trade_confirm',revision=rev)
        self.assertIsNone(self.gateway.game.players[wa['id']]['trade'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM audit WHERE kind="trade"').fetchone()[0],1)
        await asyncio.sleep(2)
        await self.command(a,'trade_request',player=wb['id'])
        await self.command(b,'trade_accept',player=wa['id'])
        await b.close()
        await self.receive(a,'trade_closed')
        self.assertFalse(self.gateway.game.trades)


class CrashRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_committed_world_and_inventory_survive_sigkill(self):
        with tempfile.TemporaryDirectory() as temp, socket.socket() as listener:
            listener.bind(('127.0.0.1',0))
            port = listener.getsockname()[1]
            listener.close()
            args = [sys.executable,'-m','server.main','--port',str(port),'--database',str(Path(temp)/'crash.sqlite3')]
            process = None
            ws = None

            async def open_server():
                nonlocal process
                process = subprocess.Popen(args,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                for _ in range(50):
                    try: return await connect('ws://127.0.0.1:'+str(port),max_size=2**22)
                    except OSError: await asyncio.sleep(.05)
                self.fail('Server failed to start')

            async def receive(kind):
                while True:
                    data = json.loads(await asyncio.wait_for(ws.recv(),3))
                    if data['type'] == 'error': self.fail(data['text'])
                    if data['type'] == kind: return data

            async def command(kind,**data):
                await ws.send(json.dumps({'type':kind,'request':uuid.uuid4().hex,**data}))
                await receive('ack')
                await asyncio.sleep(.1)

            try:
                ws = await open_server()
                await ws.send(json.dumps({'type':'auth','name':'CrashExplorer','password':'crash-password','register':True}))
                initial = await receive('welcome')
                await command('create_world',world='CRASH_HOME',biome='snow')
                await command('select',slot=7)
                await command('place',x=12,y=20)
                await command('select',slot=3)
                await command('place',x=10,y=20)
                process.kill()
                process.wait(timeout=5)
                await ws.close()
                ws = await open_server()
                await ws.send(json.dumps({'type':'auth','token':initial['token']}))
                restored = await receive('welcome')
                self.assertEqual(restored['world']['meta']['name'],'CRASH_HOME')
                self.assertIn([12,20,'core'],restored['world']['tiles'])
                self.assertIn([10,20,'crop'],restored['world']['tiles'])
                self.assertEqual(len(restored['world']['crops']),1)
                self.assertEqual(restored['slots'][3]['n'],7)
                self.assertIsNone(restored['slots'][7])
            finally:
                if ws: await ws.close()
                if process and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
