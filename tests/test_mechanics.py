"""Persistence, rollback and authorization checks for real workshop mechanics."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import uuid

from server.definitions import ITEMS
from server.game import Game
from server.inventory import Rejected, add, empty, quantity
from server.mechanics import Mechanics
from server.storage import Store


class MechanicsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'mechanics.sqlite3'
        self.store = Store(self.path)
        self.now = 100000.
        self.game = Game(self.store, lambda: self.now)
        self.a, _ = self.store.authenticate('Aster', 'test-password', True)
        self.b, _ = self.store.authenticate('Briar', 'test-password', True)
        self.game.join(self.a)
        self.game.join(self.b)
        self.mechanics = self.game.mechanics
        self.game.players[self.b]['x'] = 12.7

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def p(self, actor=None):
        return self.game.players[actor or self.a]

    def cmd(self, kind, actor=None, **data):
        self.now += .2
        self.game.command(actor or self.a, {'type': kind, 'request': uuid.uuid4().hex, **data})

    def station(self, item='loom', x=12, y=20):
        w = self.game.world('NEXUS')
        w.cells[(x, y)] = item
        self.store.tile(w.name, x, y, item)
        return x, y

    def supplies(self, **items):
        p = self.p()
        p['inventory'] = empty()
        for item, amount in items.items():
            self.assertEqual(add(p['inventory'], item, amount), 0)
        self.game.inventory(p)

    def job(self):
        return self.store.db.execute('SELECT id,ready FROM machine_jobs ORDER BY ready').fetchone()

    def restart(self):
        for ident in list(self.game.players):
            self.game.leave(ident)
        self.store.close()
        self.store = Store(self.path)
        self.game = Game(self.store, lambda: self.now)
        self.mechanics = self.game.mechanics
        self.game.join(self.a)
        self.game.join(self.b)

    def test_workshop_persists_and_collects_exactly_once(self):
        x, y = self.station()
        self.supplies(fiber=8)
        self.cmd('machine_start', x=x, y=y, recipe='cloth', count=2)
        ident, ready = self.job()
        self.assertEqual(quantity(self.p()['inventory'], 'fiber'), 0)
        self.assertGreater(ready, self.now)
        with self.assertRaises(Rejected):
            self.cmd('machine_collect', x=x, y=y, job=ident)
        self.restart()
        self.assertEqual(self.job()[0], ident)
        self.now = ready+1
        self.cmd('machine_collect', x=x, y=y, job=ident)
        self.assertEqual(quantity(self.p()['inventory'], 'cloth'), 2)
        with self.assertRaises(Rejected):
            self.cmd('machine_collect', x=x, y=y, job=ident)
        self.assertEqual(quantity(self.p()['inventory'], 'cloth'), 2)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM machine_jobs').fetchone()[0], 0)

    def test_other_player_cannot_collect_workshop_job(self):
        x, y = self.station()
        self.supplies(fiber=4)
        self.cmd('machine_start', x=x, y=y, recipe='cloth')
        ident, ready = self.job()
        self.now = ready+1
        with self.assertRaises(Rejected):
            self.cmd('machine_collect', actor=self.b, x=x, y=y, job=ident)
        self.assertIsNotNone(self.job())
        self.assertEqual(quantity(self.p(self.b)['inventory'], 'cloth'), 0)

    def test_full_inventory_preserves_completed_job(self):
        x, y = self.station()
        self.supplies(fiber=4)
        self.cmd('machine_start', x=x, y=y, recipe='cloth')
        ident, ready = self.job()
        self.p()['inventory'] = [{'id': 'wood_pick', 'n': 1} for _ in range(30)]
        before = deepcopy(self.p()['inventory'])
        self.now = ready+1
        with self.assertRaises(Rejected):
            self.cmd('machine_collect', x=x, y=y, job=ident)
        self.assertEqual(self.p()['inventory'], before)
        self.assertIsNotNone(self.job())
        self.p()['inventory'][0] = None
        self.cmd('machine_collect', x=x, y=y, job=ident)
        self.assertEqual(quantity(self.p()['inventory'], 'cloth'), 1)

    def test_workshop_queue_serializes_and_cannot_be_mined(self):
        x, y = self.station()
        self.supplies(fiber=20)
        self.cmd('machine_start', x=x, y=y, recipe='cloth')
        first_ready = self.job()[1]
        self.cmd('machine_start', x=x, y=y, recipe='cloth')
        rows = self.store.db.execute('SELECT ready FROM machine_jobs ORDER BY ready').fetchall()
        self.assertEqual(rows[1][0]-first_ready, 6.)
        with self.assertRaises(Rejected):
            self.cmd('mine', x=x, y=y)
        self.cmd('machine_start', x=x, y=y, recipe='cloth')
        self.cmd('machine_start', x=x, y=y, recipe='cloth')
        before = deepcopy(self.p()['inventory'])
        with self.assertRaises(Rejected):
            self.cmd('machine_start', x=x, y=y, recipe='cloth')
        self.assertEqual(self.p()['inventory'], before)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM machine_jobs').fetchone()[0], 4)

    def test_workshop_validates_reach_permission_recipe_and_count(self):
        x, y = self.station()
        self.supplies(fiber=20)
        for data in [{'x': 100, 'y': y, 'recipe': 'cloth'},
                     {'x': x, 'y': y, 'recipe': 'bread'},
                     {'x': x, 'y': y, 'recipe': 'cloth', 'count': True},
                     {'x': x, 'y': y, 'recipe': 'cloth', 'count': 21}]:
            with self.assertRaises(Rejected):
                self.cmd('machine_start', **data)
        w = self.game.world('NEXUS')
        w.meta.update(owner=self.b, guest_build=False)
        with self.assertRaises(Rejected):
            self.cmd('machine_start', x=x, y=y, recipe='cloth')
        self.assertEqual(quantity(self.p()['inventory'], 'fiber'), 20)
        self.assertIsNone(self.job())

    def test_timed_craft_action_uses_nearest_station(self):
        self.station()
        self.supplies(fiber=4)
        self.cmd('craft', recipe='cloth')
        self.assertIsNotNone(self.job())
        self.assertEqual(quantity(self.p()['inventory'], 'cloth'), 0)
        self.assertEqual(quantity(self.p()['inventory'], 'fiber'), 0)
        self.assertTrue(any(message['type'] == 'open_machine' for _, message in self.game.outbox))

    def test_furnace_keeps_instant_recipes_and_supports_atomic_batches(self):
        x, y = self.station('furnace')
        self.supplies(sand=4, coal=2)
        self.cmd('machine_open', x=x, y=y)
        panel = next(m for _, m in reversed(self.game.outbox) if m['type'] == 'open_machine')
        self.assertTrue({'iron', 'glass', 'copper'}.issubset({r['id'] for r in panel['recipes']}))
        self.cmd('machine_start', x=x, y=y, recipe='glass', count=2)
        self.assertEqual(quantity(self.p()['inventory'], 'glass'), 4)
        self.assertEqual(quantity(self.p()['inventory'], 'sand'), 0)
        self.assertIsNone(self.job())

    def test_furnace_instant_batch_insufficient_materials_is_atomic(self):
        x, y = self.station('furnace')
        self.supplies(sand=4, coal=1)
        before = deepcopy(self.p()['inventory'])
        with self.assertRaises(Rejected):
            self.cmd('machine_start', x=x, y=y, recipe='glass', count=2)
        self.assertEqual(self.p()['inventory'], before)
        self.assertEqual(quantity(self.p()['inventory'], 'glass'), 0)

    def test_workshop_replay_never_consumes_twice(self):
        x, y = self.station()
        self.supplies(fiber=8)
        packet = {'type': 'machine_start', 'request': uuid.uuid4().hex, 'x': x, 'y': y, 'recipe': 'cloth'}
        self.game.command(self.a, packet)
        self.now += 1
        with self.assertRaises(Rejected):
            self.game.command(self.a, packet)
        self.assertEqual(quantity(self.p()['inventory'], 'fiber'), 4)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM machine_jobs').fetchone()[0], 1)

    def test_equipment_is_not_duplicated_and_persists(self):
        self.supplies(straw_hat=1, cape=1, sage_outfit=1)
        self.cmd('equip', slot=0)
        self.cmd('equip', slot=1)
        self.cmd('equip', slot=2)
        self.assertEqual(self.p()['appearance'], {'hat': 'straw_hat', 'back': 'cape', 'outfit': 'sage_outfit'})
        self.assertEqual(sum(s['n'] for s in self.p()['inventory'] if s), 0)
        self.restart()
        self.assertEqual(self.p()['appearance']['hat'], 'straw_hat')
        self.cmd('equip', slot=-1, equipment='hat')
        self.assertEqual(quantity(self.p()['inventory'], 'straw_hat'), 1)
        self.assertNotIn('hat', self.p()['appearance'])
        with self.assertRaises(Rejected):
            self.cmd('equip', slot=-1, equipment='hat')
        self.assertEqual(quantity(self.p()['inventory'], 'straw_hat'), 1)

    def test_equipment_swap_with_full_inventory_and_takeoff_capacity(self):
        self.supplies(straw_hat=1)
        self.cmd('equip', slot=0)
        self.p()['inventory'] = [{'id': 'wood_pick', 'n': 1} for _ in range(30)]
        self.p()['inventory'][0] = {'id': 'explorer_hat', 'n': 1}
        self.cmd('equip', slot=0)
        self.assertEqual(self.p()['appearance']['hat'], 'explorer_hat')
        self.assertEqual(quantity(self.p()['inventory'], 'straw_hat'), 1)
        with self.assertRaises(Rejected):
            self.cmd('equip', slot=-1, equipment='hat')
        self.assertEqual(self.p()['appearance']['hat'], 'explorer_hat')

    def test_food_restore_and_full_energy_does_not_consume(self):
        self.supplies(bread=2)
        self.p()['energy'] = 50.
        self.cmd('use_item', slot=0)
        self.assertEqual(self.p()['energy'], 70.)
        self.assertEqual(quantity(self.p()['inventory'], 'bread'), 1)
        self.p()['energy'] = 100.
        with self.assertRaises(Rejected):
            self.cmd('use_item', slot=0)
        self.assertEqual(quantity(self.p()['inventory'], 'bread'), 1)
        self.restart()
        self.assertEqual(quantity(self.p()['inventory'], 'bread'), 1)

    def test_fishing_cooldown_rod_water_capacity_and_persistence(self):
        self.station('water')
        self.supplies(fishing_rod=1)
        self.mechanics.rng = type('Predictable', (), {'random': lambda self: .5})()
        self.cmd('fish', x=12, y=20)
        self.assertEqual(quantity(self.p()['inventory'], 'trout'), 1)
        self.assertEqual(self.p()['energy'], 90.)
        with self.assertRaises(Rejected):
            self.cmd('fish', x=12, y=20)
        self.restart()
        with self.assertRaises(Rejected):
            self.cmd('fish', x=12, y=20)
        self.now += 4
        self.cmd('fish', x=12, y=20)
        self.assertEqual(quantity(self.p()['inventory'], 'trout'), 2)
        self.p()['inventory'] = [{'id': 'fishing_rod', 'n': 1} for _ in range(30)]
        self.now += 4
        with self.assertRaises(Rejected):
            self.cmd('fish', x=12, y=20)
        self.assertEqual(self.p()['energy'], 80.)
        with self.assertRaises(Rejected):
            self.cmd('fish', x=11, y=21)

    def test_fishing_rare_pearl_and_no_client_selected_reward(self):
        self.station('water')
        self.supplies(fishing_rod=1)
        self.mechanics.rng = type('Predictable', (), {'random': lambda self: .01})()
        self.cmd('fish', x=12, y=20, reward='crystal', count=999)
        self.assertEqual(quantity(self.p()['inventory'], 'pearl'), 1)
        self.assertEqual(quantity(self.p()['inventory'], 'crystal'), 0)

    def test_water_interaction_casts_when_holding_fishing_rod(self):
        x, y = self.station('water')
        self.supplies(fishing_rod=1)
        self.mechanics.rng = type('Predictable', (), {'random': lambda self: .5})()
        self.cmd('interact', x=x, y=y)
        self.assertEqual(quantity(self.p()['inventory'], 'trout'), 1)

    def test_milestone_progress_and_claim_survive_restart_exactly_once(self):
        with self.store.transaction():
            self.mechanics.event(self.p(), 'build', 20)
        self.restart()
        self.cmd('claim_quest', quest='first_build')
        self.assertEqual(quantity(self.p()['inventory'], 'fiber'), 16)
        with self.assertRaises(Rejected):
            self.cmd('claim_quest', quest='first_build')
        self.restart()
        with self.assertRaises(Rejected):
            self.cmd('claim_quest', quest='first_build')
        self.assertEqual(quantity(self.p()['inventory'], 'fiber'), 16)
        self.cmd('progression')
        progression = next(m for _, m in reversed(self.game.outbox) if m['type'] == 'progression')
        quest = next(q for q in progression['quests'] if q['id'] == 'first_build')
        self.assertEqual(quest['status'], 'claimed')
        self.assertEqual(progression['points'], 25)

    def test_milestone_claim_capacity_is_atomic(self):
        with self.store.transaction():
            self.mechanics.event(self.p(), 'build', 20)
        self.p()['inventory'] = [{'id': 'wood_pick', 'n': 1} for _ in range(30)]
        with self.assertRaises(Rejected):
            self.cmd('claim_quest', quest='first_build')
        self.assertFalse(self.store.db.execute('SELECT 1 FROM quest_claims').fetchone())
        self.p()['inventory'] = empty()
        self.cmd('claim_quest', quest='first_build')
        self.assertEqual(quantity(self.p()['inventory'], 'fiber'), 12)

    def test_discovery_counts_distinct_worlds(self):
        self.store.create_world('CANYON', 'desert')
        self.store.create_world('SUMMIT', 'snow')
        for destination in ['CANYON', 'NEXUS', 'CANYON', 'SUMMIT', 'NEXUS']:
            self.cmd('travel', world=destination)
        self.cmd('progression')
        progression = next(m for _, m in reversed(self.game.outbox) if m['type'] == 'progression')
        quest = next(q for q in progression['quests'] if q['id'] == 'new_horizons')
        self.assertEqual(quest['current'], 3)
        self.assertEqual(quest['status'], 'ready')

    def test_emote_enum_cooldown_and_public_state(self):
        self.cmd('emote', emote='wave')
        self.assertEqual(self.game.public_player(self.p())['emote'], 'wave')
        with self.assertRaises(Rejected):
            self.cmd('emote', emote='wave')
        self.now += 2
        with self.assertRaises(Rejected):
            self.cmd('emote', emote='<script>')
        self.now += 4
        self.assertEqual(self.game.public_player(self.p())['emote'], '')

    def test_portal_configuration_persists_guest_travel_and_permission(self):
        x, y = self.station('portal')
        self.store.create_world('FARAWAY', 'snow')
        w = self.game.world('NEXUS')
        w.meta.update(owner=self.a, guest_build=False)
        self.store.save_meta(w.meta)
        with self.assertRaises(Rejected):
            self.cmd('portal_config', actor=self.b, x=x, y=y, world='FARAWAY')
        self.cmd('portal_config', x=x, y=y, world='FARAWAY')
        self.restart()
        self.cmd('interact', actor=self.b, x=x, y=y)
        self.assertEqual(self.p(self.b)['world'], 'FARAWAY')
        with self.assertRaises(Rejected):
            self.cmd('portal_config', x=x, y=y, world='MISSING')

    def test_unlinked_portal_opens_configuration_for_builder(self):
        x, y = self.station('portal')
        self.cmd('interact', x=x, y=y)
        panel = next(m for _, m in reversed(self.game.outbox) if m['type'] == 'open_portal')
        self.assertEqual(panel['destination'], '')
        self.assertEqual((panel['x'], panel['y']), (x, y))
        self.assertTrue(any(w['name'] == 'NEXUS' for w in panel['worlds']))

    def test_transaction_failure_rolls_back_job_and_inventory(self):
        x, y = self.station()
        self.supplies(fiber=4)
        # Fail after the job INSERT and the in-memory ingredient removal, so this
        # checks SQL and Game cache rollback together rather than early rejection.
        self.store.db.execute("CREATE TRIGGER reject_inventory BEFORE UPDATE OF inventory ON accounts BEGIN SELECT RAISE(ABORT,'simulated disk failure'); END")
        before = deepcopy(self.p()['inventory'])
        with self.assertRaises(Exception):
            self.cmd('machine_start', x=x, y=y, recipe='cloth')
        self.assertEqual(self.p()['inventory'], before)
        self.assertIsNone(self.job())
        self.assertEqual(self.store.player(self.a)['inventory'], before)

    def test_collection_save_failure_keeps_reward_collectable(self):
        x, y = self.station()
        self.supplies(fiber=4)
        self.cmd('machine_start', x=x, y=y, recipe='cloth')
        ident, ready = self.job()
        self.now = ready+1
        self.store.db.execute("CREATE TRIGGER reject_inventory BEFORE UPDATE OF inventory ON accounts BEGIN SELECT RAISE(ABORT,'simulated disk failure'); END")
        before = deepcopy(self.p()['inventory'])
        with self.assertRaises(Exception):
            self.cmd('machine_collect', x=x, y=y, job=ident)
        self.assertEqual(self.p()['inventory'], before)
        self.assertEqual(self.job()[0], ident)
        self.store.db.execute('DROP TRIGGER reject_inventory')
        self.cmd('machine_collect', x=x, y=y, job=ident)
        self.assertEqual(quantity(self.p()['inventory'], 'cloth'), 1)

    def test_equipment_save_failure_restores_inventory_and_appearance(self):
        self.supplies(straw_hat=1)
        self.store.db.execute("CREATE TRIGGER reject_inventory BEFORE UPDATE OF inventory ON accounts BEGIN SELECT RAISE(ABORT,'simulated disk failure'); END")
        before = deepcopy(self.p()['inventory'])
        with self.assertRaises(Exception):
            self.cmd('equip', slot=0)
        self.assertEqual(self.p()['inventory'], before)
        self.assertEqual(self.p()['appearance'], {})
        row = self.store.db.execute('SELECT equipment FROM player_mechanics WHERE account=?', (self.a,)).fetchone()
        self.assertTrue(row is None or row[0] == '{}')


if __name__ == '__main__':
    unittest.main()
