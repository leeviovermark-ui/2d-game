"""Real authority/storage tests; no fake client-side economy."""
import tempfile
import unittest
import uuid
from copy import deepcopy
from pathlib import Path
from server.definitions import HEIGHT, MOVE
from server.game import Game
from server.inventory import Rejected, add, empty, quantity
from server.storage import Store
from server.world import generate, normalize


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'world.sqlite3'
        self.store = Store(self.path)
        self.now = 100000.0
        self.game = Game(self.store, lambda: self.now)
        self.a, self.token = self.store.authenticate('Aster', 'test-password', True)
        self.b, _ = self.store.authenticate('Briar', 'test-password', True)
        self.game.join(self.a)
        self.game.join(self.b)
        self.game.players[self.b]['x'] = 12.7

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def cmd(self, actor, kind, **data):
        self.now += .2
        if kind in ('trade_offer', 'trade_lock', 'trade_confirm', 'trade_cancel'):
            data.setdefault('trade_id', self.p(actor)['trade'])
        self.game.command(actor, {'type': kind, 'request': uuid.uuid4().hex, **data})

    def p(self, actor=None):
        return self.game.players[actor or self.a]

    def simulate(self, seconds):
        for _ in range(int(seconds*30)):
            self.now += 1/30
            self.game.tick(1/30)

    def start_trade(self):
        self.cmd(self.a, 'trade_request', player=self.b)
        self.cmd(self.b, 'trade_accept', player=self.a)
        return self.game.trades[self.p()['trade']]

    def test_account_hash_and_resume(self):
        self.assertEqual(self.store.resume(self.token), self.a)
        self.assertEqual(self.store.authenticate('aster', 'test-password')[0], self.a)
        with self.assertRaises(Rejected):
            self.store.authenticate('Aster', 'wrong-password')
        raw = self.path.read_bytes()
        self.assertNotIn(b'test-password', raw)
        self.assertNotIn(self.token.encode(), raw)

    def test_seeded_biomes_and_valid_names(self):
        self.assertEqual(generate(42,'forest'),generate(42,'forest'))
        self.assertNotEqual(generate(42,'forest'),generate(43,'forest'))
        self.assertIn('sand',generate(42,'desert').values())
        self.assertIn('snow',generate(42,'snow').values())
        self.assertEqual(normalize(' my_world '),'MY_WORLD')
        for name in ['../escape','a','<script>','hello world',None]:
            with self.assertRaises(Rejected): normalize(name)

    def test_movement_jump_collision_and_bounds(self):
        p = self.p()
        self.simulate(.2)
        self.assertTrue(p['grounded'])
        old = p['y']
        self.game.command(self.a,{'type':'input','axis':0,'jump':True,'x':999999})
        self.simulate(.3)
        self.assertLess(p['y'],old-1)
        self.simulate(1.5)
        self.assertTrue(p['grounded'])
        self.assertLess(p['y']+MOVE['height'],21.01)
        self.assertLess(p['x'],144)
        with self.assertRaises(Rejected):
            self.game.command(self.a,{'type':'input','axis':100,'jump':True})

    def test_spawn_validation_when_saved_position_is_blocked(self):
        p = self.p()
        p['x'],p['y'] = 14.5,17.0  # shelter wall
        self.game.leave(self.a)
        p = self.game.join(self.a)
        w = self.game.world(p['world'])
        self.assertFalse(w.collides(p['x'],p['y']))
        self.assertTrue(w.collides(p['x'],p['y']+.03))

    def test_place_is_atomic_and_replay_protected(self):
        self.game.players[self.b]['x'] = 9
        self.cmd(self.a,'select',slot=1)
        before = quantity(self.p()['inventory'],'dirt')
        request = uuid.uuid4().hex
        packet = {'type':'place','request':request,'x':12,'y':20}
        self.game.command(self.a,packet)
        self.assertEqual(quantity(self.p()['inventory'],'dirt'),before-1)
        self.now += 1
        with self.assertRaises(Rejected): self.game.command(self.a,packet)
        with self.assertRaises(Rejected): self.cmd(self.a,'place',x=12,y=20)
        self.assertEqual(quantity(self.p()['inventory'],'dirt'),before-1)
        self.assertEqual(self.game.world('NEXUS').tile(12,20),'dirt')

    def test_place_range_overlap_and_invalid_item(self):
        self.cmd(self.a,'select',slot=1)
        inv = deepcopy(self.p()['inventory'])
        for x,y in [(100,20),(11,20),(-1,20),(145,20)]:
            with self.assertRaises(Rejected): self.cmd(self.a,'place',x=x,y=y)
        self.assertEqual(self.p()['inventory'],inv)
        self.cmd(self.a,'select',slot=0)
        with self.assertRaises(Rejected): self.cmd(self.a,'place',x=10,y=20)

    def test_mining_server_time_tools_and_single_drop(self):
        w = self.game.world('NEXUS')
        self.cmd(self.a,'mine',x=11,y=21)
        self.assertEqual(w.tile(11,21),'grass')
        self.simulate(.1)
        self.assertEqual(w.tile(11,21),'grass')
        self.simulate(.5)
        self.assertIsNone(w.tile(11,21))
        total = sum(quantity(p['inventory'],'dirt') for p in self.game.players.values()) + sum(d['n'] for d in w.drops.values() if d['item']=='dirt')
        self.assertEqual(total,49)
        with self.assertRaises(Rejected): self.cmd(self.a,'mine',x=11,y=HEIGHT-1)
        self.game.world('NEXUS').cells[(12,21)] = 'iron_ore'
        with self.assertRaises(Rejected): self.cmd(self.a,'mine',x=12,y=21)

    def test_crop_timestamp_harvest_and_full_inventory(self):
        self.game.players[self.b]['x'] = 9
        self.cmd(self.a,'select',slot=3)
        self.cmd(self.a,'place',x=12,y=20)
        with self.assertRaises(Rejected): self.cmd(self.a,'interact',x=12,y=20)
        self.now += 91
        before = deepcopy(self.p()['inventory'])
        self.p()['inventory'] = [{'id':'dirt','n':99} for _ in range(30)]
        with self.assertRaises(Rejected): self.cmd(self.a,'interact',x=12,y=20)
        self.assertEqual(self.game.world('NEXUS').tile(12,20),'crop')
        self.p()['inventory'] = before
        self.cmd(self.a,'interact',x=12,y=20)
        self.assertEqual(quantity(self.p()['inventory'],'grain'),3)
        self.assertEqual(quantity(self.p()['inventory'],'seed'),9)
        with self.assertRaises(Rejected): self.cmd(self.a,'interact',x=12,y=20)

    def test_crafting_materials_station_and_capacity(self):
        before = deepcopy(self.p()['inventory'])
        with self.assertRaises(Rejected): self.cmd(self.a,'craft',recipe='stone_pick')
        self.assertEqual(self.p()['inventory'],before)
        add(self.p()['inventory'],'stone',8)
        self.p()['x'] = 8
        with self.assertRaises(Rejected): self.cmd(self.a,'craft',recipe='stone_pick')
        self.p()['x'] = 12
        self.cmd(self.a,'craft',recipe='stone_pick')
        self.assertEqual(quantity(self.p()['inventory'],'stone_pick'),1)
        self.assertEqual(quantity(self.p()['inventory'],'stone'),0)
        with self.assertRaises(Rejected): self.cmd(self.a,'craft',recipe='infinite-money')

    def test_storage_race_and_mining_nonempty_chest(self):
        self.p()['x'] = self.p(self.b)['x'] = 12.5
        self.cmd(self.a,'storage',x=16,y=20,deposit=True,slot=1,count=5)
        self.cmd(self.b,'storage',x=16,y=20,deposit=False,slot=0,count=5)
        with self.assertRaises(Rejected): self.cmd(self.a,'storage',x=16,y=20,deposit=False,slot=0,count=5)
        self.assertEqual(quantity(self.p()['inventory'],'dirt'),19)
        self.assertEqual(quantity(self.p(self.b)['inventory'],'dirt'),29)
        self.cmd(self.a,'storage',x=16,y=20,deposit=True,slot=1,count=1)
        with self.assertRaises(Rejected): self.cmd(self.b,'mine',x=16,y=20)

    def test_two_players_collect_one_drop_and_full_inventory_keeps_it(self):
        w = self.game.world('NEXUS')
        self.game.new_drop(w,12,20,'grain',5,grace=0)
        self.game.pickup(self.p(),w)
        self.game.pickup(self.p(self.b),w)
        self.assertEqual(sum(quantity(p['inventory'],'grain') for p in self.game.players.values()),5)
        self.assertFalse(w.drops)
        self.p()['inventory'] = [{'id':'dirt','n':99} for _ in range(30)]
        self.game.new_drop(w,12,20,'grain',5,grace=0)
        self.game.pickup(self.p(),w)
        self.assertEqual(len(w.drops),1)

    def test_trade_atomic_and_duplicate_confirmation(self):
        t = self.start_trade()
        self.cmd(self.a,'trade_offer',offer={'wood':2})
        self.cmd(self.b,'trade_offer',offer={'dirt':3})
        rev = t['revision']
        self.cmd(self.a,'trade_lock',revision=rev)
        self.cmd(self.b,'trade_lock',revision=rev)
        self.cmd(self.a,'trade_confirm',revision=rev)
        self.cmd(self.b,'trade_confirm',revision=rev)
        self.assertEqual(quantity(self.p()['inventory'],'wood'),6)
        self.assertEqual(quantity(self.p()['inventory'],'dirt'),27)
        self.assertEqual(quantity(self.p(self.b)['inventory'],'wood'),10)
        self.assertEqual(quantity(self.p(self.b)['inventory'],'dirt'),21)
        with self.assertRaises(Rejected): self.cmd(self.b,'trade_confirm',revision=rev)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM audit WHERE kind="trade"').fetchone()[0],1)

    def test_trade_offer_changes_reset_locks_and_freeze_inventory(self):
        self.start_trade()
        self.cmd(self.a,'trade_offer',offer={'wood':2})
        self.cmd(self.a,'trade_lock',revision=1)
        with self.assertRaises(Rejected): self.cmd(self.a,'drop_item',slot=4,count=1)
        with self.assertRaises(Rejected): self.cmd(self.a,'trade_offer',offer={'wood':-1})
        self.cmd(self.b,'trade_offer',offer={'dirt':1})
        t = self.game.trades[self.p()['trade']]
        self.assertEqual(t['locked'],[])
        with self.assertRaises(Rejected): self.cmd(self.a,'trade_confirm',revision=1)

    def test_trade_cancel_disconnect_and_travel_preserve_items(self):
        before = deepcopy(self.p()['inventory'])
        self.start_trade()
        self.cmd(self.a,'trade_offer',offer={'wood':4})
        self.game.leave(self.b)
        self.assertIsNone(self.p()['trade'])
        self.assertEqual(self.p()['inventory'],before)
        self.game.join(self.b)
        self.now += 2
        self.start_trade()
        self.cmd(self.a,'travel',world='NEXUS')
        self.assertFalse(self.game.trades)
        self.assertEqual(self.p()['inventory'],before)

    def test_claim_permissions_and_builder_persistence(self):
        self.cmd(self.a,'create_world',world='HOME',biome='snow')
        self.cmd(self.b,'travel',world='HOME')
        self.p(self.b)['x'] = 9
        self.cmd(self.a,'select',slot=7)
        self.cmd(self.a,'place',x=12,y=20)
        self.cmd(self.b,'select',slot=1)
        with self.assertRaises(Rejected): self.cmd(self.b,'place',x=10,y=20)
        self.cmd(self.a,'permissions',guest_build=False,builders=['Briar'])
        self.cmd(self.b,'place',x=10,y=20)
        with self.assertRaises(Rejected): self.cmd(self.b,'permissions',guest_build=True,builders=[])
        self.assertEqual(self.store.load_world('HOME').meta['builders'],[self.b])

    def test_restart_retains_world_crop_inventory_and_storage(self):
        self.cmd(self.a,'create_world',world='PERSIST',biome='desert')
        self.cmd(self.a,'select',slot=3)
        self.cmd(self.a,'place',x=12,y=20)
        self.p()['x'] = 12.5
        self.cmd(self.a,'storage',x=16,y=20,deposit=True,slot=4,count=3)
        inv = deepcopy(self.p()['inventory'])
        self.game.leave(self.a)
        self.game.leave(self.b)
        self.store.close()
        self.store = Store(self.path)
        self.now += 91
        self.game = Game(self.store,lambda:self.now)
        self.game.join(self.store.resume(self.token))
        w = self.game.world('PERSIST')
        self.assertEqual(w.tile(12,20),'crop')
        self.assertEqual(quantity(w.containers[(16,20)],'wood'),3)
        self.assertEqual(self.p()['inventory'],inv)
        self.cmd(self.a,'interact',x=12,y=20)
        self.assertEqual(quantity(self.p()['inventory'],'grain'),3)

    def test_split_swap_drop_negative_and_malformed_requests(self):
        self.cmd(self.a,'move_slot',**{'from':1,'to':15,'count':12})
        self.assertEqual(self.p()['inventory'][15],{'id':'dirt','n':12})
        self.cmd(self.a,'move_slot',**{'from':15,'to':4,'count':12})
        self.assertEqual(self.p()['inventory'][4],{'id':'dirt','n':12})
        for kind,data in [('drop_item',{'slot':4,'count':-1}),('storage',{'x':16,'y':20,'deposit':True,'slot':True,'count':1}),
                          ('move_slot',{'from':-1,'to':4,'count':1}),('invent_item',{'item':'crystal','count':999})]:
            with self.assertRaises(Rejected): self.cmd(self.a,kind,**data)

    def test_tool_removal_during_mining_cancels_completion(self):
        self.p()['x'] = 12.5
        self.cmd(self.a,'mine',x=12,y=21)
        self.cmd(self.a,'storage',x=16,y=20,deposit=True,slot=0,count=1)
        self.simulate(2)
        self.assertEqual(self.game.world('NEXUS').tile(12,21),'grass')
        self.assertIsNone(self.p()['mining'])

    def test_trade_full_inventory_failure_is_atomic(self):
        self.p()['inventory'] = [{'id':'dirt','n':99} for _ in range(30)]
        before_a, before_b = deepcopy(self.p()['inventory']),deepcopy(self.p(self.b)['inventory'])
        self.start_trade()
        self.cmd(self.b,'trade_offer',offer={'wood':2})
        rev = 1
        self.cmd(self.a,'trade_lock',revision=rev)
        self.cmd(self.b,'trade_lock',revision=rev)
        self.cmd(self.a,'trade_confirm',revision=rev)
        with self.assertRaises(Rejected): self.cmd(self.b,'trade_confirm',revision=rev)
        self.assertEqual(self.p()['inventory'],before_a)
        self.assertEqual(self.p(self.b)['inventory'],before_b)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM audit WHERE kind="trade"').fetchone()[0],0)
        self.assertIsNone(self.p()['trade'])
        self.assertIsNone(self.p(self.b)['trade'])
        self.assertFalse(self.game.trades)
        self.cmd(self.a,'trade_cancel')
        self.assertFalse(self.game.trades)

    def test_craft_capacity_failure_preserves_ingredients(self):
        self.p()['inventory'] = [{'id':'wood','n':99} for _ in range(30)]
        before = deepcopy(self.p()['inventory'])
        with self.assertRaises(Rejected): self.cmd(self.a,'craft',recipe='planks')
        self.assertEqual(self.p()['inventory'],before)

    def test_pickup_disconnect_reconnect_cannot_collect_twice(self):
        w = self.game.world('NEXUS')
        self.game.new_drop(w,11.5,20,'crystal',1,grace=0)
        self.game.pickup(self.p(),w)
        self.game.leave(self.a)
        self.game.join(self.a)
        self.game.pickup(self.p(),self.game.world('NEXUS'))
        self.assertEqual(quantity(self.p()['inventory'],'crystal'),1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM drops').fetchone()[0],0)


if __name__ == '__main__':
    unittest.main()
