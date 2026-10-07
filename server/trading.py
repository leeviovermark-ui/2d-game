"""Two-player offer revisions, locks, and atomic exchange, inside Game transactions."""
from copy import deepcopy
import math
import secrets
from .definitions import ITEMS
from .inventory import require, integer, quantity, remove, add


class Trading:
    def __init__(self, game):
        self.game = game

    def nearby(self, a, b):
        return a['world'] == b['world'] and math.hypot(a['x']-b['x'], a['y']-b['y']) < 7

    def trade_request(self, p, d):
        other = self.game.players.get(d.get('player'))
        require(other is not None and other != p and self.nearby(p, other), 'Find an explorer within seven tiles.')
        require(not p['trade'] and not other['trade'], 'An explorer is already trading.')
        require(self.game.clock()-p.get('last_invite', 0) >= 2, 'Please wait before inviting again.')
        p['last_invite'] = self.game.clock()
        self.game.invites[other['id']] = (p['id'], self.game.clock()+20)
        self.game.emit(other['id'], 'trade_invite', player=p['id'], name=p['name'])
        self.game.emit(p['id'], 'notice', text='Trade request sent to '+other['name']+'.')

    def trade_accept(self, p, d):
        invite = self.game.invites.get(p['id'])
        require(invite and invite[0] == d.get('player') and invite[1] > self.game.clock(), 'Trade invitation expired.')
        other = self.game.players.get(invite[0])
        require(other is not None and self.nearby(p, other) and not p['trade'] and not other['trade'], 'Trade unavailable.')
        ident = secrets.token_hex(12)
        trade = {'id': ident, 'players': [other['id'], p['id']], 'names': [other['name'], p['name']],
                 'offers': {p['id']: {}, other['id']: {}}, 'locked': [], 'confirmed': [], 'revision': 0}
        self.game.trades[ident] = trade
        p['trade'] = other['trade'] = ident
        p['mining'] = other['mining'] = None
        del self.game.invites[p['id']]
        self.send_trade(trade)

    def get_trade(self, p):
        trade = self.game.trades.get(p['trade'])
        require(trade is not None, 'No active trade.')
        return trade

    def send_trade(self, trade):
        for ident in trade['players']:
            self.game.emit(ident, 'trade', trade=deepcopy(trade))

    def trade_offer(self, p, d):
        trade = self.get_trade(p)
        offer = d.get('offer')
        require(isinstance(offer, dict) and len(offer) <= 12, 'Offer at most twelve item types.')
        for item, n in offer.items():
            require(item in ITEMS, 'Unknown item in trade.')
            integer(n, 1, 999)
            require(quantity(p['inventory'], item) >= n, 'You do not own that offer.')
        trade['offers'][p['id']] = offer.copy()
        trade['locked'], trade['confirmed'] = [], []
        trade['revision'] += 1
        self.send_trade(trade)

    def trade_lock(self, p, d):
        trade = self.get_trade(p)
        require(d.get('revision') == trade['revision'], 'Offer changed. Review it again.')
        if p['id'] not in trade['locked']:
            trade['locked'].append(p['id'])
        self.send_trade(trade)

    def trade_confirm(self, p, d):
        trade = self.get_trade(p)
        require(d.get('revision') == trade['revision'] and len(trade['locked']) == 2, 'Both explorers must lock the current offers.')
        if p['id'] not in trade['confirmed']:
            trade['confirmed'].append(p['id'])
        if len(trade['confirmed']) < 2:
            self.send_trade(trade)
            return
        a, b = [self.game.players.get(i) for i in trade['players']]
        require(a is not None and b is not None and self.nearby(a, b), 'Trade partner disconnected or moved away.')
        ia, ib = deepcopy(a['inventory']), deepcopy(b['inventory'])
        for item, n in trade['offers'][a['id']].items():
            remove(ia, item, n)
        for item, n in trade['offers'][b['id']].items():
            remove(ib, item, n)
        for item, n in trade['offers'][b['id']].items():
            require(add(ia, item, n) == 0, 'An explorer has no room for this trade.')
        for item, n in trade['offers'][a['id']].items():
            require(add(ib, item, n) == 0, 'An explorer has no room for this trade.')
        a['inventory'], b['inventory'] = ia, ib
        self.game.inventory(a)
        self.game.inventory(b)
        self.game.store.audit('trade', trade['players'], trade['offers'])
        self.cancel_trade(p, 'Trade completed. Your exchange has been saved.')

    def cancel_trade(self, p, reason='Trade cancelled. No items were exchanged.'):
        trade = self.game.trades.pop(p['trade'], None)
        if trade:
            for ident in trade['players']:
                if ident in self.game.players:
                    self.game.players[ident]['trade'] = None
                self.game.emit(ident, 'trade_closed', text=reason)

