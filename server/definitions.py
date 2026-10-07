"""One stable-ID registry consumed by both Godot and the authority."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFINITIONS = json.loads((ROOT / 'shared/definitions.json').read_text())
ITEMS = {item['id']: item for item in DEFINITIONS['items']}
RECIPES = {recipe['id']: recipe for recipe in DEFINITIONS['recipes']}
MOVE = DEFINITIONS['movement']
INVENTORY_SIZE = 30
WIDTH, HEIGHT = 144, 56


def solid(item):
    return ITEMS.get(item, {}).get('solid', False)
