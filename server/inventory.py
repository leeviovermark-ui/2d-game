"""Pure inventory operations. Callers commit copies only after full validation."""
from copy import deepcopy
from .definitions import ITEMS, INVENTORY_SIZE


class Rejected(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Rejected(message)


def integer(value, low, high):
    require(type(value) is int and low <= value <= high, 'Invalid quantity or slot.')
    return value


def empty(size=INVENTORY_SIZE):
    return [None] * size


def quantity(inv, item):
    return sum(s['n'] for s in inv if s and s['id'] == item)


def add(inv, item, count):
    require(item in ITEMS, 'Unknown item.')
    integer(count, 1, 9999)
    remaining = count
    for s in inv:
        if s and s['id'] == item:
            n = min(ITEMS[item]['stack'] - s['n'], remaining)
            s['n'] += n
            remaining -= n
    for i, s in enumerate(inv):
        if s is None and remaining:
            n = min(ITEMS[item]['stack'], remaining)
            inv[i] = {'id': item, 'n': n}
            remaining -= n
    return remaining


def remove(inv, item, count):
    integer(count, 1, 9999)
    require(quantity(inv, item) >= count, 'Not enough materials.')
    for i, s in enumerate(inv):
        if s and s['id'] == item:
            n = min(s['n'], count)
            count -= n
            s['n'] -= n
            if s['n'] == 0:
                inv[i] = None
            if count == 0:
                return


def transfer(source, target, slot, count, target_slot=None):
    integer(slot, 0, len(source) - 1)
    require(source[slot] is not None, 'Empty slot.')
    integer(count, 1, source[slot]['n'])
    a, b = deepcopy(source), deepcopy(target)
    item = a[slot]['id']
    if target_slot is None:
        require(add(b, item, count) == 0, 'Inventory is full.')
    else:
        integer(target_slot, 0, len(b) - 1)
        dest = b[target_slot]
        require(dest is None or dest['id'] == item, 'Choose an empty or matching slot.')
        require((dest['n'] if dest else 0) + count <= ITEMS[item]['stack'], 'Stack is full.')
        b[target_slot] = {'id': item, 'n': (dest['n'] if dest else 0) + count}
    a[slot]['n'] -= count
    if not a[slot]['n']:
        a[slot] = None
    return a, b


def starter():
    inv = empty()
    for item, n in [('wood_pick', 1), ('dirt', 24), ('planks', 16), ('seed', 8), ('wood', 8),
                    ('bench', 1), ('chest', 1), ('core', 1), ('fiber', 4)]:
        add(inv, item, n)
    return inv
