"""Regression coverage for stale trade packets and safe world arrivals."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import uuid
import sqlite3
from unittest.mock import patch

from server.definitions import HEIGHT, MOVE, WIDTH
from server.game import Game
from server.inventory import Rejected, empty, quantity, transfer
from server.storage import Store
from server.world import World


class TradeRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'regressions.sqlite3')
        self.now = 100000.
        self.game = Game(self.store, lambda: self.now)
        self.a, _ = self.store.authenticate('TradeA', 'test-password', True)
        self.b, _ = self.store.authenticate('TradeB', 'test-password', True)
        self.game.join(self.a)
        self.game.join(self.b)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def command(self, actor, kind, **data):
        self.now += .2
        self.game.command(actor, {'type': kind, 'request': uuid.uuid4().hex, **data})

    def start_trade(self):
        self.now += 2
        self.command(self.a, 'trade_request', player=self.b)
        self.command(self.b, 'trade_accept', player=self.a)
        return self.game.players[self.a]['trade']

    def lock_trade(self, trade_id):
        self.command(self.b, 'trade_offer', trade_id=trade_id, offer={'wood': 2})
        for actor in (self.a, self.b):
            self.command(actor, 'trade_lock', trade_id=trade_id, revision=1)
        self.command(self.a, 'trade_confirm', trade_id=trade_id, revision=1)

    def assert_cancelled_without_exchange(self, before):
        self.assertFalse(self.game.trades)
        for actor, inventory in before.items():
            self.assertIsNone(self.game.players[actor]['trade'])
            self.assertEqual(self.game.players[actor]['inventory'], inventory)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM audit WHERE kind="trade"').fetchone()[0], 0)
        closed = {destination for destination, message in self.game.outbox if message['type'] == 'trade_closed'}
        self.assertEqual(closed, {self.a, self.b})

    def test_stale_packets_cannot_affect_replacement_trade(self):
        old_id = self.start_trade()
        self.command(self.a, 'trade_cancel', trade_id=old_id)
        new_id = self.start_trade()
        for kind, data in [('trade_offer', {'offer': {'wood': 2}}),
                           ('trade_lock', {'revision': 0}),
                           ('trade_confirm', {'revision': 0}),
                           ('trade_cancel', {})]:
            with self.assertRaises(Rejected):
                self.command(self.a, kind, trade_id=old_id, **data)
            current = self.game.trades[new_id]
            self.assertEqual(current['offers'], {self.a: {}, self.b: {}})
            self.assertEqual(current['locked'], [])
            self.assertEqual(current['confirmed'], [])
            self.assertEqual(self.game.players[self.a]['trade'], new_id)

    def test_trade_packets_must_name_active_trade(self):
        trade_id = self.start_trade()
        for kind, data in [('trade_offer', {'offer': {}}), ('trade_lock', {'revision': 0}),
                           ('trade_confirm', {'revision': 0}), ('trade_cancel', {})]:
            with self.assertRaises(Rejected):
                self.command(self.a, kind, **data)
        self.assertIn(trade_id, self.game.trades)

    def test_boolean_revision_cannot_lock_trade(self):
        trade_id = self.start_trade()
        self.command(self.a, 'trade_offer', trade_id=trade_id, offer={'wood': 1})
        with self.assertRaises(Rejected):
            self.command(self.a, 'trade_lock', trade_id=trade_id, revision=True)
        self.assertEqual(self.game.trades[trade_id]['locked'], [])

    def test_no_inventory_space_cancels_and_preserves_both_inventories(self):
        self.game.players[self.a]['inventory'] = [{'id': 'dirt', 'n': 99} for _ in range(30)]
        trade_id = self.start_trade()
        self.lock_trade(trade_id)
        before = {actor: deepcopy(self.game.players[actor]['inventory']) for actor in (self.a, self.b)}
        self.game.outbox.clear()
        with self.assertRaises(Rejected):
            self.command(self.b, 'trade_confirm', trade_id=trade_id, revision=1)
        self.assert_cancelled_without_exchange(before)

    def test_missing_offer_at_final_validation_cancels_without_partial_exchange(self):
        trade_id = self.start_trade()
        self.lock_trade(trade_id)
        # Simulate an authoritative inventory correction after the first confirm.
        self.game.players[self.b]['inventory'] = empty()
        before = {actor: deepcopy(self.game.players[actor]['inventory']) for actor in (self.a, self.b)}
        self.game.outbox.clear()
        with self.assertRaises(Rejected):
            self.command(self.b, 'trade_confirm', trade_id=trade_id, revision=1)
        self.assert_cancelled_without_exchange(before)

    def test_partner_moving_away_before_tick_cancels_final_confirmation(self):
        trade_id = self.start_trade()
        self.lock_trade(trade_id)
        self.game.players[self.b]['x'] += 20
        before = {actor: deepcopy(self.game.players[actor]['inventory']) for actor in (self.a, self.b)}
        self.game.outbox.clear()
        with self.assertRaises(Rejected):
            self.command(self.b, 'trade_confirm', trade_id=trade_id, revision=1)
        self.assert_cancelled_without_exchange(before)


class SpawnRegressionTests(unittest.TestCase):
    def world(self, spawn=None):
        meta = {'name': 'SPAWN', 'seed': 71051, 'biome': 'forest', 'owner': None,
                'builders': [], 'guest_build': True, 'spawn': spawn or [11.5, 19.4]}
        return World(meta)

    def test_floating_platform_does_not_hijack_ground_spawn(self):
        world = self.world()
        world.cells[(11, 10)] = 'stone'
        x, y = world.spawn()
        self.assertEqual(x, 11.5)
        self.assertAlmostEqual(y, 21 - MOVE['height'] - .001)
        self.assertFalse(world.collides(x, y))
        self.assertTrue(world.collides(x, y + .03))

    def test_blocked_preferred_column_uses_nearby_ground_before_high_roof(self):
        world = self.world()
        for y in range(10, 21):
            world.cells[(11, y)] = 'stone'
        x, y = world.spawn()
        self.assertLessEqual(abs(x - 11.5), 1)
        self.assertAlmostEqual(y, 21 - MOVE['height'] - .001)

    def test_spawn_near_world_bottom_is_supported(self):
        world = self.world([11.5, 53.4])
        world.cells = {(x, HEIGHT - 1): 'stone' for x in range(WIDTH)}
        x, y = world.spawn()
        self.assertAlmostEqual(y, HEIGHT - 1 - MOVE['height'] - .001)
        self.assertFalse(world.collides(x, y))

    def test_fully_blocked_world_reports_actionable_rejection(self):
        world = self.world()
        world.cells = {(x, y): 'stone' for x in range(WIDTH) for y in range(HEIGHT)}
        with self.assertRaisesRegex(Rejected, 'no safe spawn'):
            world.spawn()

    def test_nonfinite_saved_position_is_treated_as_blocked(self):
        world = self.world()
        for x, y in [(float('nan'), 19.), (11., float('inf')), (float('-inf'), 19.)]:
            self.assertTrue(world.collides(x, y))


class InventoryRegressionTests(unittest.TestCase):
    def test_rejected_transfer_keeps_both_inventory_inputs_unchanged(self):
        source = [{'id': 'wood', 'n': 5}, None]
        target = [{'id': 'wood', 'n': 98}]
        before = deepcopy((source, target))
        with self.assertRaises(Rejected):
            transfer(source, target, 0, 2)
        self.assertEqual((source, target), before)

    def test_split_transfer_fills_matching_stack_then_empty_slot(self):
        source = [{'id': 'wood', 'n': 5}]
        target = [{'id': 'wood', 'n': 98}, None]
        remaining, received = transfer(source, target, 0, 3)
        self.assertEqual(remaining, [{'id': 'wood', 'n': 2}])
        self.assertEqual(received, [{'id': 'wood', 'n': 99}, {'id': 'wood', 'n': 2}])
        self.assertEqual(source, [{'id': 'wood', 'n': 5}])
        self.assertEqual(target, [{'id': 'wood', 'n': 98}, None])


class PersistenceFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'failed-writes.sqlite3')
        self.now = 100000.
        self.game = Game(self.store, lambda: self.now)
        self.actor, _ = self.store.authenticate('Saver', 'test-password', True)
        self.player = self.game.join(self.actor)
        self.world = self.game.world('NEXUS')

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_failed_mining_save_keeps_tile_and_produces_no_ghost_drop(self):
        self.game.command(self.actor, {'type': 'mine', 'request': uuid.uuid4().hex, 'x': 11, 'y': 21})
        self.now += 2
        self.game.outbox.clear()
        with patch.object(self.store, 'drop', side_effect=sqlite3.OperationalError('simulated write failure')):
            with self.assertRaises(sqlite3.OperationalError):
                self.game.finish_mining(self.player)
        self.assertEqual(self.world.tile(11, 21), 'grass')
        self.assertFalse(self.world.drops)
        self.assertFalse(self.game.outbox)
        self.assertIsNotNone(self.player['mining'])
        self.assertIsNone(self.store.db.execute('SELECT item FROM tiles WHERE world="NEXUS" AND x=11 AND y=21').fetchone())
        self.game.finish_mining(self.player)
        self.assertIsNone(self.world.tile(11, 21))
        self.assertEqual(len(self.world.drops), 1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM drops').fetchone()[0], 1)

    def test_failed_pickup_save_preserves_drop_and_inventory_until_retry(self):
        self.game.new_drop(self.world, self.player['x'], self.player['y'] + .7, 'crystal', 1, grace=0)
        before = deepcopy(self.player['inventory'])
        self.game.outbox.clear()
        with patch.object(self.store, 'save_player', side_effect=sqlite3.OperationalError('simulated write failure')):
            with self.assertRaises(sqlite3.OperationalError):
                self.game.pickup(self.player, self.world)
        self.assertEqual(self.player['inventory'], before)
        self.assertEqual(len(self.world.drops), 1)
        self.assertFalse(self.game.outbox)
        self.game.pickup(self.player, self.world)
        self.game.pickup(self.player, self.world)
        self.assertEqual(quantity(self.player['inventory'], 'crystal'), 1)
        self.assertFalse(self.world.drops)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM drops').fetchone()[0], 0)

    def test_failed_partial_pickup_update_preserves_cached_and_persisted_quantities(self):
        self.player['inventory'] = [{'id': 'dirt', 'n': 99} for _ in range(29)] + [{'id': 'grain', 'n': 98}]
        self.store.save_player(self.player)
        self.game.new_drop(self.world, self.player['x'], self.player['y'] + .7, 'grain', 5, grace=0)
        before = deepcopy(self.player['inventory'])
        drop_id = next(iter(self.world.drops))
        self.game.outbox.clear()
        with patch.object(self.store, 'drop', side_effect=sqlite3.OperationalError('simulated write failure')):
            with self.assertRaises(sqlite3.OperationalError):
                self.game.pickup(self.player, self.world)
        self.assertEqual(self.player['inventory'], before)
        self.assertEqual(self.store.player(self.actor)['inventory'], before)
        self.assertEqual(self.world.drops[drop_id]['n'], 5)
        self.assertEqual(self.store.load_world('NEXUS').drops[drop_id]['n'], 5)
        self.assertFalse(self.game.outbox)
        self.game.pickup(self.player, self.world)
        self.assertEqual(quantity(self.player['inventory'], 'grain'), 99)
        self.assertEqual(self.world.drops[drop_id]['n'], 4)
        self.assertEqual(self.store.load_world('NEXUS').drops[drop_id]['n'], 4)


if __name__ == '__main__':
    unittest.main()
