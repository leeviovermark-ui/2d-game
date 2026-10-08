"""Stage 2 movement parity, expanded bounds and save compatibility regressions."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid

from server.definitions import ITEMS, MOVE, ROOT
from server.game import Game
from server.inventory import Rejected, add, empty, quantity
from server.physics import FIELDS, step
from server.storage import Store
from server.world import World, generate

DELTA = 1/60


def player(**changes):
    return {'x': 11.5, 'y': 21-MOVE['height']-.001, 'vx': 0., 'vy': 0.,
            'grounded': True, 'coyote': 0., 'jump_buffer': 0., 'energy': 100.,
            'launch_timer': 0., **changes}


def intent(axis=0, sprint=False, jump=False, held=False):
    return {'axis': axis, 'sprint': sprint, 'jump': jump, 'jump_held': held}


def flat_world(width=144, height=56, floor=21, spring=False):
    world = World({'name': 'PHYSICS', 'seed': 71051, 'biome': 'forest',
                   'width': width, 'height': height})
    world.cells = {(x, floor): 'stone' for x in range(width)}
    if spring:
        world.cells[(11, floor-1)] = 'spring'
    return world


def trajectory(initial, inputs, world):
    p, frames = deepcopy(initial), []
    for action in inputs:
        step(p, world, action, DELTA)
        frames.append(deepcopy(p))
    return frames


class Stage2MovementTests(unittest.TestCase):
    def test_sprint_moves_faster_and_spends_authoritative_energy(self):
        w = flat_world()
        start = player()
        walking = trajectory(start, [intent(axis=1)]*60, w)
        sprinting = trajectory(start, [intent(axis=1, sprint=True)]*60, w)
        self.assertGreater(sprinting[-1]['x']-walking[-1]['x'], 2.)
        self.assertAlmostEqual(sprinting[-1]['vx'], MOVE['sprint_speed'])
        self.assertAlmostEqual(sprinting[-1]['energy'], 100-MOVE['sprint_drain'], places=8)
        self.assertEqual(walking[-1]['energy'], 100)
        self.assertTrue(all(not w.collides(p['x'], p['y']) for p in sprinting))

    def test_energy_never_goes_negative_and_rest_recovers_without_movement(self):
        w = flat_world()
        depleted = trajectory(player(energy=.1), [intent(axis=1, sprint=True)]*180, w)
        self.assertTrue(all(0 <= p['energy'] <= 100 for p in depleted))
        rested = trajectory(player(energy=5.), [intent(sprint=True)]*60, w)
        self.assertAlmostEqual(rested[-1]['energy'], 5+MOVE['energy_recovery'], places=8)
        self.assertAlmostEqual(rested[-1]['x'], 11.5)
        full = trajectory(player(energy=99.), [intent()]*60, w)
        self.assertEqual(full[-1]['energy'], 100.)

    def test_spring_bounces_automatically_without_jump_held(self):
        w = flat_world(spring=True)
        frames = trajectory(player(), [intent(held=False)]*45, w)
        self.assertEqual(frames[0]['vy'], -17.)
        self.assertFalse(frames[0]['grounded'])
        self.assertGreater(frames[1]['launch_timer'], .5)
        self.assertLess(frames[1]['vy'], -16.)
        self.assertGreater(player()['y']-min(p['y'] for p in frames), 4.)
        self.assertTrue(all(not w.collides(p['x'], p['y']) for p in frames))

    def test_spring_requires_ground_support(self):
        w = flat_world(spring=True)
        del w.cells[(11, 21)]
        frames = trajectory(player(grounded=False), [intent()]*10, w)
        self.assertTrue(all(p['vy'] > 0 for p in frames))
        self.assertTrue(all(p['launch_timer'] == 0 for p in frames))

    def test_large_world_collision_bounds_use_saved_dimensions(self):
        w = flat_world(width=256, height=80, floor=79)
        self.assertFalse(w.collides(250.5, 79-MOVE['height']-.001))
        self.assertTrue(w.collides(256., 77.))
        self.assertTrue(w.collides(250., 80-MOVE['height']+.01))
        frames = trajectory(player(x=250.5, y=70., grounded=False, vy=20.), [intent()]*60, w)
        self.assertTrue(frames[-1]['grounded'])
        self.assertAlmostEqual(frames[-1]['y']+MOVE['height'], 79, places=3)

    @unittest.skipUnless(shutil.which('godot'), 'Godot unavailable: authority checks still run')
    def test_actual_godot_prediction_matches_sprint_spring_and_expanded_bounds(self):
        ordinary = flat_world()
        spring = flat_world(spring=True)
        expanded = flat_world(width=256, height=80, floor=79)
        cases = [
            ('sprint_and_recover', player(), [intent(axis=1, sprint=True)]*180+[intent()]*120, ordinary),
            ('empty_energy', player(energy=.1), [intent(axis=-1, sprint=True)]*60, ordinary),
            ('spring_released', player(), [intent(held=False)]*150, spring),
            ('spring_sprint', player(), [intent(axis=1, sprint=True)]*100, spring),
            ('expanded_fall', player(x=250.5, y=60, vy=20., grounded=False), [intent()]*90, expanded),
            ('expanded_right_edge', player(x=250.5, y=79-MOVE['height']-.001),
             [intent(axis=1, sprint=True)]*90, expanded),
        ]
        config = {'delta': DELTA, 'items': ITEMS, 'movement': MOVE, 'cases': [
            {'name': name, 'initial': initial, 'inputs': actions,
             'width': w.width, 'height': w.height,
             'tiles': [[x, y, item] for (x, y), item in w.cells.items()]}
            for name, initial, actions, w in cases]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output, runner = root/'input.json', root/'output.json', root/'runner.gd'
            source.write_text(json.dumps(config))
            # Reuse the real movement fixture, adding only per-case dimensions.
            # The production client Movement.step remains the code under test.
            harness = (ROOT/'tests/movement_runner.gd').read_text()
            runner.write_text(harness.replace('\t\tstate.items = config.items',
                '\t\tstate.width = int(case.width)\n\t\tstate.height = int(case.height)\n\t\tstate.items = config.items'))
            result = subprocess.run(['bash', 'scripts/godot.sh', '--headless', '--script', str(runner),
                                     '--', str(source), str(output)], cwd=ROOT,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertNotIn('SCRIPT ERROR', result.stderr)
            self.assertTrue(output.is_file(), result.stdout+result.stderr)
            predictions = json.loads(output.read_text())
        for name, initial, actions, w in cases:
            expected = trajectory(initial, actions, w)
            self.assertEqual(len(expected), len(predictions[name]))
            for frame, (authoritative, predicted) in enumerate(zip(expected, predictions[name])):
                with self.subTest(trajectory=name, frame=frame):
                    for field in FIELDS:
                        if field == 'grounded':
                            self.assertEqual(predicted[field], authoritative[field])
                        else:
                            self.assertAlmostEqual(predicted[field], authoritative[field], delta=.0003,
                                                   msg=f'{name} frame {frame} field {field}')


class Stage2WorldTests(unittest.TestCase):
    def test_original_world_generation_is_byte_for_byte_unchanged(self):
        # Canonical terrain SHA256 from the shipped Stage 1 cf76f98 generator.
        original = {
            'forest': '71c93aa743b2742b441b106d188f79f1d31c6b3d764c18c028a4ad24e6c67634',
            'desert': '3bcc0bc6adffd51a19edca46a63a7ddd0ae2673e6a66c80a1ad64b8389d8c160',
            'snow': '4ed5c0d1d6497ef92cacaed59a1044a7c4c61297d771701acb9346675799a3ff',
        }
        for biome, expected in original.items():
            cells = generate(71051, biome)
            encoded = json.dumps(sorted([x, y, item] for (x, y), item in cells.items()), separators=(',', ':'))
            with self.subTest(biome=biome):
                self.assertEqual(hashlib.sha256(encoded.encode()).hexdigest(), expected)

    def test_expanded_generation_has_accessible_water_and_new_resources(self):
        for biome in ('forest', 'desert', 'snow'):
            cells = generate(71051, biome, width=256, height=80, generation=2)
            counts = Counter(cells.values())
            with self.subTest(biome=biome):
                self.assertTrue(all(0 <= x < 256 and 0 <= y < 80 for x, y in cells))
                for item in ('water', 'clay', 'copper_ore', 'amber', 'amethyst', 'crystal'):
                    self.assertGreater(counts[item], 0, item)
                self.assertGreater(sum(x > 144 for x, y in cells if cells[(x, y)] == 'copper_ore'), 0)
                self.assertTrue(all(y < 30 for (x, y), item in cells.items() if item == 'water'))
                self.assertTrue(all(cells.get((x, 79)) is not None for x in range(256)))
                self.assertEqual(cells[(11, 21)], {'forest': 'grass', 'desert': 'sand', 'snow': 'snow'}[biome])
                if biome == 'snow':
                    self.assertGreater(counts['ice'], 0)

    def test_created_world_catalog_dimensions_and_changes_survive_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'worlds.sqlite3'
            store = Store(path)
            now = [100000.]
            game = Game(store, lambda: now[0])
            actor, _ = store.authenticate('WorldBuilder', 'test-password', True)
            game.join(actor)
            game.command(actor, {'type': 'create_world', 'world': 'BIGGER_HOME', 'biome': 'forest',
                                 'request': uuid.uuid4().hex})
            created = game.world('BIGGER_HOME')
            self.assertEqual((created.width, created.height), (256, 80))
            self.assertEqual(created.meta['generation'], 2)
            self.assertEqual((created.snapshot()['width'], created.snapshot()['height']), (256, 80))
            self.assertTrue(any(w['name'] == 'BIGGER_HOME' for w in store.directory()))
            store.tile('BIGGER_HOME', 210, 65, 'rose_tile')
            store.tile('NEXUS', 11, 20, 'carrot_crop')
            store.crop('NEXUS', 11, 20, now[0])
            generation = deepcopy(created.cells)
            store.close()
            store = Store(path)
            reloaded = store.load_world('BIGGER_HOME')
            self.assertEqual((reloaded.width, reloaded.height), (256, 80))
            self.assertEqual(reloaded.tile(210, 65), 'rose_tile')
            generation[(210, 65)] = 'rose_tile'
            self.assertEqual(reloaded.cells, generation)
            legacy = store.load_world('NEXUS')
            self.assertEqual((legacy.width, legacy.height), (144, 56))
            self.assertEqual(legacy.tile(11, 20), 'carrot_crop')
            self.assertEqual(legacy.crops[(11, 20)], now[0])
            store.close()

    def test_crafting_station_outside_legacy_bounds_is_usable(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp)/'worlds.sqlite3')
            game = Game(store, lambda: 100000.)
            actor, _ = store.authenticate('DistantCrafter', 'test-password', True)
            p = game.join(actor)
            game.command(actor, {'type': 'create_world', 'world': 'FAR_CRAFT', 'biome': 'forest',
                                 'request': uuid.uuid4().hex})
            world = game.world('FAR_CRAFT')
            for x in range(195, 206):
                for y in range(55, 61):
                    world.cells.pop((x, y), None)
                world.cells[(x, 61)] = 'stone'
            world.cells[(200, 60)] = 'loom'
            p.update(x=199.5, y=61-MOVE['height']-.001, inventory=empty())
            add(p['inventory'], 'fiber', 4)
            self.assertFalse(world.collides(p['x'], p['y']))
            game.command(actor, {'type': 'craft', 'recipe': 'cloth', 'request': uuid.uuid4().hex})
            job = store.db.execute('SELECT world,x,y FROM machine_jobs WHERE owner=?', (actor,)).fetchone()
            self.assertEqual(job, ('FAR_CRAFT', 200, 60))
            self.assertEqual(quantity(p['inventory'], 'fiber'), 0)
            store.close()


if __name__ == '__main__':
    unittest.main()
