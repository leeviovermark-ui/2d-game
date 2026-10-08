"""Fixed-step movement shared by the authority and the client prediction model."""
import math
from .definitions import MOVE

FIELDS = ('x', 'y', 'vx', 'vy', 'grounded', 'coyote', 'jump_buffer', 'energy', 'launch_timer')


def snapshot(player):
    return {key: player.get(key, False if key == 'grounded' else (100. if key == 'energy' else 0.)) for key in FIELDS}


def step(p, w, intent, dt):
    axis = intent['axis']
    energy = min(100., max(0., p.get('energy', 100.)))
    sprint = bool(intent.get('sprint', False) and axis and energy + 1e-8 >= MOVE['sprint_drain'] * dt)
    p['energy'] = max(0., energy - MOVE['sprint_drain'] * dt) if sprint else min(100., energy + MOVE['energy_recovery'] * dt)
    speed = MOVE['sprint_speed'] if sprint else MOVE['speed']
    p['coyote'] = MOVE['coyote'] if p['grounded'] else max(0., p.get('coyote', 0.) - dt)
    p['jump_buffer'] = MOVE['jump_buffer'] if intent.get('jump') else max(0., p.get('jump_buffer', 0.) - dt)
    accel = MOVE['acceleration'] * (1 if p['grounded'] else MOVE['air_control'])
    amount = (accel if axis else MOVE['friction']) * dt
    p['vx'] += max(-amount, min(amount, axis * speed - p['vx']))
    if p['jump_buffer'] > 0 and p['coyote'] > 0:
        p['vy'] = -MOVE['jump']
        p['jump_buffer'] = p['coyote'] = 0.
        p['grounded'] = False
    p['launch_timer'] = max(0., p.get('launch_timer', 0.)-dt)
    if not intent.get('jump_held', True) and p['vy'] < -MOVE['jump_cut'] and not p['launch_timer']:
        p['vy'] = -MOVE['jump_cut']
    p['vy'] = min(20., p['vy'] + MOVE['gravity'] * dt)
    steps = max(1, math.ceil(max(abs(p['vx']), abs(p['vy'])) * dt / .15))
    for _ in range(steps):
        for coord, velocity in (('x', 'vx'), ('y', 'vy')):
            distance = p[velocity] * dt / steps
            if not distance:
                continue
            old = p[coord]
            def blocked(fraction):
                return w.collides(old + distance * fraction, p['y']) if coord == 'x' else w.collides(p['x'], old + distance * fraction)
            if not blocked(1.):
                p[coord] = old + distance
            else:
                low, high = 0., 1.
                for _ in range(12):
                    middle = (low + high) / 2
                    if blocked(middle):
                        high = middle
                    else:
                        low = middle
                p[coord] = old + distance * low
                p[velocity] = 0.
    p['grounded'] = p['vy'] >= 0 and w.collides(p['x'], p['y'] + .02)

    if p['grounded'] and w.tile(math.floor(p['x']), math.floor(p['y']+MOVE['height']-.25)) == 'spring':
        p['vy'], p['grounded'], p['launch_timer'] = -17., False, .6
