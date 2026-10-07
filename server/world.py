"""Seeded terrain and bounded collision, shared by the simulation and requests."""
import math
import random
import re
from .definitions import WIDTH, HEIGHT, MOVE, solid
from .inventory import require


def normalize(name):
    require(isinstance(name, str), 'Enter a world name.')
    name = name.strip().upper()
    require(re.fullmatch(r'[A-Z][A-Z0-9_]{2,19}', name), 'Use 3–20 letters, numbers, or underscores.')
    return name


def generate(seed, biome):
    rng = random.Random(seed)
    cells = {}
    heights = []
    surface = {'forest': 'grass', 'desert': 'sand', 'snow': 'snow'}[biome]
    for x in range(WIDTH):
        h = 21 + round(math.sin(x * .13 + seed % 8) * 2 + math.sin(x * .31) * 1.5)
        if x < 27:
            h = 21
        heights.append(h)
        for y in range(h, HEIGHT):
            item = surface if y == h else ('dirt' if y < h + 4 else 'stone')
            cave = y > h + 5 and y < HEIGHT - 2 and math.sin(x*.31 + y*.27) + math.cos(x*.19 - y*.33) > 1.25
            if cave:
                continue
            if item == 'stone':
                roll = rng.random()
                if roll < .045:
                    item = 'coal_ore'
                elif roll < .08:
                    item = 'iron_ore'
                elif roll < .09 and y > 38:
                    item = 'crystal'
            cells[(x, y)] = item
    if biome != 'desert':
        for x in [5, 29, 39, 53, 65, 79, 95, 113, 131]:
            h = heights[x]
            tree_h = rng.randint(4, 6)
            for y in range(h - tree_h, h):
                cells[(x, y)] = 'wood'
            for dx in range(-3, 4):
                for dy in range(-3, 2):
                    if abs(dx) + abs(dy) <= 4 and dx != 0:
                        cells[(x + dx, h - tree_h + dy)] = 'leaves'
    # A small original, unclaimed trail shelter. Background trees remain traversable.
    for x in range(14, 22):
        cells[(x, 21)] = 'brick'
        cells[(x, 16)] = 'planks'
    for y in range(17, 21):
        cells[(14, y)] = 'planks'
    for y in range(17, 20):
        cells[(21, y)] = 'planks'
    cells[(15, 20)] = 'bench'
    cells[(16, 20)] = 'chest'
    cells[(20, 19)] = 'torch'
    return cells


class World:
    def __init__(self, meta, deltas=(), crops=(), containers=(), drops=()):
        self.meta = meta
        self.name = meta['name']
        self.cells = generate(meta['seed'], meta['biome'])
        for x, y, item in deltas:
            if item:
                self.cells[(x, y)] = item
            else:
                self.cells.pop((x, y), None)
        self.crops = {(x, y): planted for x, y, planted in crops}
        self.containers = {(x, y): inv for x, y, inv in containers}
        self.drops = {d['id']: d for d in drops}
        self.pending = []

    def tile(self, x, y):
        return self.cells.get((x, y))

    def collides(self, x, y):
        if x < MOVE['width']/2 or x > WIDTH - MOVE['width']/2 or y < 0 or y + MOVE['height'] > HEIGHT:
            return True
        for tx in range(math.floor(x - MOVE['width']/2), math.floor(x + MOVE['width']/2 - .0001) + 1):
            for ty in range(math.floor(y), math.floor(y + MOVE['height'] - .0001) + 1):
                if solid(self.tile(tx, ty)):
                    return True
        return False

    def spawn(self):
        preferred = self.meta.get('spawn', [11.5, 19.4])
        # Search supported, empty positions; never blindly teleport into a tile.
        for radius in range(WIDTH):
            for x in [preferred[0] + radius, preferred[0] - radius]:
                if not 1 <= x < WIDTH - 1:
                    continue
                for ty in range(2, HEIGHT - 2):
                    y = ty - MOVE['height'] - .001
                    if not self.collides(x, y) and self.collides(x, y + .03):
                        return x, y
        raise ValueError('World has no safe spawn.')

    def snapshot(self):
        return {'meta': self.meta, 'width': WIDTH, 'height': HEIGHT,
                'tiles': [[x, y, item] for (x, y), item in self.cells.items()],
                'crops': [[x, y, t] for (x, y), t in self.crops.items()],
                'drops': list(self.drops.values())}

    def allowed(self, account, permission='build'):
        return (self.meta['owner'] is None or account == self.meta['owner']
                or account in self.meta['builders'] or (permission == 'build' and self.meta['guest_build']))
