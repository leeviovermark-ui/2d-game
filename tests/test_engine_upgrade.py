"""Authoritative input limits and network scheduling regressions."""
import asyncio
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import uuid

from server.game import Game
from server.main import Gateway
from server.storage import Store
from server.definitions import MOVE
from server.inventory import Rejected


class SequencedMovementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'movement.sqlite3')
        self.now = 100000.
        self.game = Game(self.store, lambda: self.now)
        self.id, _ = self.store.authenticate('MovementExplorer', 'movement-password', True)
        self.player = self.game.join(self.id)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def intent(self, seq, **fields):
        self.game.command(self.id, {'type': 'input', 'axis': 1, 'jump': False,
                                   'jump_held': False, 'seq': seq, 'epoch': self.player['movement_epoch'], **fields})

    def tick(self):
        self.now += 1/60
        self.game.tick(1/60)

    def test_burst_input_queue_is_bounded_and_cannot_accelerate_simulation(self):
        start = self.player['x']
        for seq in range(1, 501):
            self.intent(seq)
        self.assertEqual(len(self.player['input_queue']), 8)
        self.assertEqual(self.player['processed_input'], 0)
        self.assertEqual(self.player['x'], start)
        self.tick()
        self.assertEqual(self.player['processed_input'], 493)
        self.assertLessEqual(self.player['x']-start, MOVE['speed']/60)
        for _ in range(7):
            self.tick()
        self.assertEqual(self.player['processed_input'], 500)
        self.assertFalse(self.player['input_queue'])

    def test_stale_duplicate_and_invalid_inputs_cannot_mutate_queue(self):
        self.intent(2)
        self.intent(2, axis=-1)
        self.intent(1, axis=-1)
        self.assertEqual(len(self.player['input_queue']), 1)
        self.assertEqual(self.player['input_queue'][0]['axis'], 1)
        for seq in (True, 1.5, -1, 2**31):
            with self.assertRaises(Rejected):
                self.intent(seq)
        with self.assertRaises(Rejected):
            self.intent(3, jump_held=1)
        self.assertEqual(self.player['input_sequence'], 2)

    def test_world_change_retires_old_epoch_and_accepts_new_sequence(self):
        previous_epoch = self.player['movement_epoch']
        self.intent(100)
        self.game.command(self.id, {'type':'create_world', 'world':'MOVE_HOME', 'biome':'forest', 'request':uuid.uuid4().hex})
        self.assertFalse(self.player['input_queue'])
        self.assertEqual(self.player['input_sequence'], 0)
        self.intent(101, epoch=previous_epoch)
        self.assertFalse(self.player['input_queue'])
        self.intent(1)
        self.tick()
        self.assertEqual(self.player['processed_input'], 1)
        self.assertNotEqual(previous_epoch, self.player['movement_epoch'])
        self.assertEqual(self.player['ack_state']['x'], self.player['x'])

    def test_stale_input_releases_movement_instead_of_draining_old_queue(self):
        for seq in range(1, 9): self.intent(seq)
        self.now += .4
        self.tick()
        self.assertFalse(self.player['input_queue'])
        self.assertEqual(self.player['processed_input'], 0)
        self.assertEqual(self.player['vx'], 0)


class SlowNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_writer_does_not_block_fixed_simulation_ticks(self):
        count = []
        game = SimpleNamespace(players={'explorer': {'id':'explorer','world':'NEXUS'}}, outbox=[],
                               tick=lambda dt:count.append(dt), snapshot=lambda world:[],
                               store=SimpleNamespace(transaction=nullcontext, save_player=lambda p:None))
        game.emit = lambda destination, kind, **fields: game.outbox.append((destination, {'type':kind, **fields}))
        gateway = Gateway(game)
        waiting = asyncio.Event()
        class SlowSocket:
            async def send(self, data):
                await waiting.wait()
            async def close(self, *args):
                return
        socket = SlowSocket()
        queue = asyncio.Queue(maxsize=128)
        gateway.connections['explorer'] = socket
        gateway.send_queues[socket] = queue
        gateway.ready_connections.add(socket)
        writer = asyncio.create_task(gateway.writer(socket, queue))
        ticks = asyncio.create_task(gateway.run_ticks())
        try:
            await asyncio.sleep(.18)
            self.assertGreaterEqual(len(count), 8)
            self.assertTrue(all(dt == 1/60 for dt in count))
            self.assertFalse(writer.done())
        finally:
            for task in (writer, ticks): task.cancel()
            await asyncio.gather(writer, ticks, return_exceptions=True)

    async def test_overflow_closes_slow_client_and_remains_bounded(self):
        gateway = Gateway(SimpleNamespace(outbox=[], players={}, store=None))
        socket = object()
        queue = asyncio.Queue(maxsize=2)
        gateway.send_queues[socket] = queue
        gateway.enqueue(socket, 'first')
        gateway.enqueue(socket, 'second')
        gateway.enqueue(socket, 'third')
        self.assertEqual(queue.qsize(), 1)
        directive = queue.get_nowait()
        self.assertEqual(directive['type'], 'disconnect')
        self.assertEqual(directive['code'], 1008)
