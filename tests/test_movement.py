"""Meaningful movement trajectories and Python/Godot prediction parity."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from server.definitions import ITEMS, MOVE, ROOT, WIDTH
from server.physics import FIELDS, step
from server.world import World

DELTA = 1 / 60


def player(**changes):
    return {'x': 11.5, 'y': 21 - MOVE['height'] - .001, 'vx': 0., 'vy': 0.,
            'grounded': True, 'coyote': 0., 'jump_buffer': 0., **changes}


def intent(axis=0, jump=False, held=True):
    return {'axis': axis, 'jump': jump, 'jump_held': held}


def flat_world(tiles=None):
    world = World({'name': 'PHYSICS', 'seed': 71051, 'biome': 'forest'})
    world.cells = dict(tiles if tiles is not None else [((x, 21), 'stone') for x in range(WIDTH)])
    return world


def run(initial, inputs, world=None):
    world = world or flat_world()
    p = deepcopy(initial)
    frames = []
    for action in inputs:
        step(p, world, action, DELTA)
        frames.append(deepcopy(p))
    return frames


class MovementTests(unittest.TestCase):
    def test_resting_player_has_no_vertical_bounce(self):
        frames = run(player(), [intent()] * 180)
        heights = [frame['y'] for frame in frames[10:]]
        self.assertLess(max(heights) - min(heights), .00001)
        self.assertTrue(all(frame['grounded'] for frame in frames))

    def test_tap_jump_is_lower_than_held_jump_and_both_land(self):
        initial = player()
        held = run(initial, [intent(jump=True)] + [intent()] * 90)
        tapped = run(initial, [intent(jump=True)] + [intent(held=False)] * 90)
        held_height = initial['y'] - min(p['y'] for p in held)
        tap_height = initial['y'] - min(p['y'] for p in tapped)
        self.assertGreater(held_height, 1.8)
        self.assertLess(tap_height, .8)
        self.assertGreater(held_height - tap_height, 1)
        self.assertTrue(held[-1]['grounded'])
        self.assertTrue(tapped[-1]['grounded'])

    def test_wall_collision_stops_at_surface_without_tunneling(self):
        world = flat_world()
        world.cells.update({(15, y): 'stone' for y in range(10, 21)})
        frames = run(player(), [intent(axis=1)] * 180, world)
        self.assertLessEqual(frames[-1]['x'] + MOVE['width']/2, 15.00011)
        self.assertAlmostEqual(frames[-1]['x'] + MOVE['width']/2, 15, places=3)
        self.assertEqual(frames[-1]['vx'], 0)
        self.assertTrue(all(not world.collides(p['x'], p['y']) for p in frames))

    def test_fall_at_terminal_speed_lands_without_tunneling(self):
        frames = run(player(y=1, vy=20, grounded=False), [intent()] * 120)
        self.assertTrue(frames[-1]['grounded'])
        self.assertAlmostEqual(frames[-1]['y'] + MOVE['height'], 21, places=3)
        self.assertEqual(frames[-1]['vy'], 0)

    def test_coyote_jump_works_only_inside_grace_window(self):
        world = flat_world([((x, 21), 'stone') for x in range(15)])
        inside = run(player(x=15.5, grounded=False, coyote=.08), [intent(axis=1, jump=True)], world)
        expired = run(player(x=15.5, grounded=False, coyote=0), [intent(axis=1, jump=True)], world)
        self.assertLess(inside[0]['vy'], -10)
        self.assertGreater(expired[0]['vy'], 0)

    def test_jump_pressed_before_landing_runs_when_ground_is_reached(self):
        frames = run(player(y=18.7, vy=8, grounded=False), [intent(jump=True)] + [intent()] * 15)
        self.assertTrue(any(p['grounded'] for p in frames[:8]))
        self.assertTrue(any(p['vy'] < -10 for p in frames[3:9]))

    @unittest.skipUnless(shutil.which('godot'), 'Godot unavailable: Python movement checks still run')
    def test_godot_and_authority_match_complete_trajectories(self):
        floor = [((x, 21), 'stone') for x in range(WIDTH)]
        cases = [
            ('accelerate_stop', player(), [intent(axis=1)] * 60 + [intent()] * 40, floor),
            ('held_jump', player(), [intent(axis=1, jump=True)] + [intent(axis=1)] * 100, floor),
            ('tap_jump', player(), [intent(jump=True)] + [intent(held=False)] * 100, floor),
            ('wall', player(), [intent(axis=1)] * 120, floor + [((15, y), 'stone') for y in range(10, 21)]),
            ('ceiling', player(), [intent(jump=True)] + [intent()] * 100, floor + [((x, 16), 'stone') for x in range(9, 14)]),
            ('terminal_fall', player(y=1, vy=20, grounded=False), [intent()] * 120, floor),
            ('left_boundary', player(x=.5), [intent(axis=-1)] * 80, floor),
            ('coyote', player(x=15.5, grounded=False, coyote=.08), [intent(axis=1, jump=True)] + [intent(axis=1)] * 60,
             [((x, 21), 'stone') for x in range(15)]),
            ('buffered_jump', player(y=18.7, vy=8, grounded=False), [intent(jump=True)] + [intent()] * 100, floor),
        ]
        config = {'delta': DELTA, 'items': ITEMS, 'movement': MOVE, 'cases': [
            {'name': name, 'initial': initial, 'inputs': inputs,
             'tiles': [[x, y, item] for (x, y), item in tiles]}
            for name, initial, inputs, tiles in cases]}
        with tempfile.TemporaryDirectory() as temp:
            source, destination = Path(temp)/'input.json', Path(temp)/'output.json'
            source.write_text(json.dumps(config))
            result = subprocess.run(['bash', 'scripts/godot.sh', '--headless', '--script',
                                     'res://tests/movement_runner.gd', '--', str(source), str(destination)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(destination.is_file(), result.stdout + result.stderr)
            self.assertNotIn('SCRIPT ERROR', result.stderr)
            predictions = json.loads(destination.read_text())
        for name, initial, inputs, tiles in cases:
            authoritative = run(initial, inputs, flat_world(tiles))
            self.assertEqual(len(predictions[name]), len(authoritative))
            for index, (predicted, expected) in enumerate(zip(predictions[name], authoritative)):
                with self.subTest(trajectory=name, frame=index):
                    for field in FIELDS:
                        if field == 'grounded':
                            self.assertEqual(predicted[field], expected[field])
                        else:
                            self.assertAlmostEqual(predicted[field], expected[field], delta=.0003,
                                                   msg=f'{name} frame {index} field {field}')

    @unittest.skipUnless(shutil.which('godot'), 'Godot unavailable: Python movement checks still run')
    def test_actual_client_prediction_and_reconciliation(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'prediction.json'
            result = subprocess.run(['bash', 'scripts/godot.sh', '--headless', '--script',
                                     'res://tests/prediction_runner.gd', '--', str(destination)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(destination.is_file(), result.stdout + result.stderr)
            self.assertNotIn('SCRIPT ERROR', result.stderr)
            checks = json.loads(destination.read_text())['checks']
        self.assertGreaterEqual(len(checks), 16)
        for check in checks:
            with self.subTest(check=check['description']):
                self.assertTrue(check['passed'])


if __name__ == '__main__':
    unittest.main()
