"""Real SQLite friendship permissions, atomic requests, and shared catalogues."""
from copy import deepcopy
from pathlib import Path
import asyncio
import json
import sqlite3
import tempfile
import unittest
import uuid
from unittest.mock import patch

from server.game import Game
from server.inventory import Rejected
from server.main import Gateway
from server.storage import Store
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve


class SocialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'world.sqlite3'
        self.store = Store(self.path)
        self.now = 100000.
        self.game = Game(self.store, lambda: self.now)
        self.a, self.token = self.store.authenticate('Aster', 'test-password', True)
        self.b, _ = self.store.authenticate('Briar', 'test-password', True)
        self.c, _ = self.store.authenticate('Cedar', 'test-password', True)
        for ident in (self.a, self.b, self.c):
            self.game.join(ident)
        self.game.outbox.clear()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def cmd(self, actor, action, **data):
        self.now += 5
        self.game.command(actor, {'type': 'social_action', 'request': uuid.uuid4().hex, 'action': action, **data})

    def friend(self, a=None, b=None):
        a, b = a or self.a, b or self.b
        self.cmd(a, 'request', target=b)
        self.cmd(b, 'accept', target=a)
        self.game.outbox.clear()

    def messages(self, kind, destination=None):
        return [message for target, message in self.game.outbox if message['type'] == kind and
                (destination is None or target == destination)]

    def restart(self):
        for ident in list(self.game.players):
            self.game.leave(ident)
        self.store.close()
        self.store = Store(self.path)
        self.game = Game(self.store, lambda: self.now)
        for ident in (self.a, self.b, self.c):
            self.game.join(ident)
        self.game.outbox.clear()

    def extra(self, n):
        ident = 'friend-test-'+str(n)
        self.store.db.execute('''INSERT INTO accounts(id,username,salt,password,inventory,world,x,y,selected,created)
            VALUES(?,?,?,?,'[]','NEXUS',11.5,19.4,0,?)''', (ident, 'Extra'+str(n), '00'*16, 'synthetic-test-digest', self.now))
        return ident

    def test_social_open_hides_credentials_and_delivers_only_to_requester(self):
        self.game.command(self.a, {'type': 'social_open'})
        self.assertEqual(len(self.game.outbox), 1)
        destination, message = self.game.outbox[0]
        self.assertEqual(destination, self.a)
        self.assertEqual(message['type'], 'social_state')
        self.assertEqual(message['friends'], [])
        self.assertEqual(message['max_friends'], 100)
        self.assertNotIn('password', repr(message))
        self.assertNotIn(self.token, repr(message))

    def test_request_accept_exact_case_insensitive_identity_and_presence(self):
        self.cmd(self.a, 'request', target='bRiAr')
        a_state = self.game.social.state(self.a)
        b_state = self.game.social.state(self.b)
        self.assertEqual(a_state['outgoing'][0]['id'], self.b)
        self.assertEqual(b_state['incoming'][0]['id'], self.a)
        self.assertTrue(a_state['outgoing'][0]['online'])
        self.cmd(self.b, 'accept', target=self.a)
        self.assertTrue(self.game.social.friends(self.a, self.b))
        for ident, friend in ((self.a, self.b), (self.b, self.a)):
            state = self.game.social.state(ident)
            self.assertEqual(state['friends'][0]['id'], friend)
            self.assertEqual(state['friends'][0]['world'], 'NEXUS')
            self.assertFalse(state['incoming'] or state['outgoing'])

    def test_offline_request_and_friendship_survive_restart(self):
        self.game.leave(self.b)
        self.cmd(self.a, 'request', target=self.b)
        self.assertFalse(self.game.social.state(self.a)['outgoing'][0]['online'])
        self.restart()
        self.cmd(self.b, 'accept', target='aster')
        self.restart()
        self.assertTrue(self.game.social.friends(self.a, self.b))
        self.assertEqual(len(self.game.social.state(self.a)['friends']), 1)

    def test_crossed_requests_accept_once_without_duplicate_edge(self):
        self.cmd(self.a, 'request', target=self.b)
        self.cmd(self.b, 'request', target=self.a)
        self.assertTrue(self.game.social.friends(self.a, self.b))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM friendships').fetchone()[0], 1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM friend_requests').fetchone()[0], 0)
        with self.assertRaises(Rejected):
            self.cmd(self.a, 'accept', target=self.b)

    def test_forged_accept_or_third_party_target_cannot_create_friendship(self):
        with self.assertRaises(Rejected):
            self.cmd(self.a, 'accept', target=self.b)
        self.cmd(self.a, 'request', target=self.b)
        with self.assertRaises(Rejected):
            self.cmd(self.c, 'accept', target=self.a)
        self.assertFalse(self.game.social.friends(self.a, self.b))
        self.assertFalse(self.game.social.friends(self.a, self.c))
        self.assertEqual(len(self.game.social.state(self.b)['incoming']), 1)

    def test_self_unknown_partial_and_malformed_targets_rejected(self):
        for target in (self.a, 'Bri', "Briar' OR 1=1 --", [], {}, None, 'x'*65):
            with self.assertRaises(Rejected):
                self.cmd(self.a, 'request', target=target)
        self.assertFalse(self.store.db.execute('SELECT 1 FROM friend_requests').fetchone())

    def test_duplicate_and_replayed_requests_cannot_duplicate_state(self):
        packet = {'type': 'social_action', 'request': uuid.uuid4().hex, 'action': 'request', 'target': self.b}
        self.game.command(self.a, packet)
        with self.assertRaisesRegex(Rejected, 'already processed'):
            self.game.command(self.a, packet)
        with self.assertRaisesRegex(Rejected, 'already pending'):
            self.cmd(self.a, 'request', target=self.b)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM friend_requests').fetchone()[0], 1)

    def test_decline_and_sender_withdraw_remove_pending_request(self):
        self.cmd(self.a, 'request', target=self.b)
        self.cmd(self.b, 'decline', target=self.a)
        self.assertFalse(self.game.social.state(self.a)['outgoing'])
        self.cmd(self.a, 'request', target=self.b)
        self.cmd(self.a, 'decline', target=self.b)
        self.assertFalse(self.game.social.state(self.b)['incoming'])
        with self.assertRaises(Rejected):
            self.cmd(self.b, 'decline', target=self.a)

    def test_friend_limits_apply_to_both_request_and_accept(self):
        self.cmd(self.a, 'request', target=self.b)
        for n in range(100):
            other = self.extra(n)
            self.store.db.execute('INSERT INTO friendships VALUES(?,?,?)', (*self.game.social.pair(self.b, other), self.now))
        with self.assertRaisesRegex(Rejected, '100-friend'):
            self.cmd(self.b, 'accept', target=self.a)
        with self.assertRaisesRegex(Rejected, '100-friend'):
            self.cmd(self.c, 'request', target=self.b)
        self.assertFalse(self.game.social.friends(self.a, self.b))
        self.assertEqual(len(self.game.social.state(self.b)['incoming']), 1)

    def test_pending_request_limits_apply_to_sender_and_recipient(self):
        extras = [self.extra(n) for n in range(100)]
        for other in extras:
            self.store.db.execute('INSERT INTO friend_requests VALUES(?,?,?)', (self.a, other, self.now))
        with self.assertRaisesRegex(Rejected, 'pending'):
            self.cmd(self.a, 'request', target=self.b)
        self.store.db.execute('DELETE FROM friend_requests')
        for other in extras:
            self.store.db.execute('INSERT INTO friend_requests VALUES(?,?,?)', (other, self.b, self.now))
        with self.assertRaisesRegex(Rejected, 'pending'):
            self.cmd(self.c, 'request', target=self.b)

    def test_remove_revokes_messages_invites_and_join_permission(self):
        self.friend()
        self.cmd(self.a, 'remove', target=self.b)
        self.assertFalse(self.game.social.friends(self.b, self.a))
        for action in ('message', 'invite', 'join'):
            with self.assertRaisesRegex(Rejected, 'accepted friends'):
                self.cmd(self.b, action, target=self.a, text='Hello')

    def test_private_message_is_delivered_to_two_peers_only_and_sanitized(self):
        self.friend()
        self.cmd(self.a, 'message', target=self.b, text='  Hello\nfriend\t!  ')
        messages = self.messages('private_message')
        self.assertEqual(len(messages), 2)
        received = self.messages('private_message', self.b)[0]
        sent = self.messages('private_message', self.a)[0]
        self.assertEqual(received['text'], 'Hellofriend!')
        self.assertFalse(received['sent'])
        self.assertTrue(sent['sent'])
        self.assertEqual(received['peer_id'], self.a)
        self.assertEqual(sent['peer_id'], self.b)
        self.assertEqual(received['time'], self.now)
        self.assertFalse(self.messages('private_message', self.c))

    def test_private_messages_reject_offline_invalid_empty_and_rate_limited(self):
        self.friend()
        for text in ('', ' '*10, '\x00'*5, 'x'*181, [], {}, None):
            with self.assertRaises(Rejected):
                self.cmd(self.a, 'message', target=self.b, text=text)
        self.cmd(self.a, 'message', target=self.b, text='hello')
        with self.assertRaisesRegex(Rejected, 'slow down'):
            self.game.command(self.a, {'type': 'social_action', 'request': uuid.uuid4().hex, 'action': 'message',
                                       'target': self.b, 'text': 'again'})
        self.game.leave(self.b)
        with self.assertRaisesRegex(Rejected, 'offline'):
            self.cmd(self.a, 'message', target=self.b, text='hello')

    def test_muted_players_cannot_contact_but_can_join_friends(self):
        self.friend()
        self.store.mute_account(self.a, self.c, self.now+600)
        for action, target in (('message', self.b), ('invite', self.b), ('request', self.c)):
            with self.assertRaisesRegex(Rejected, 'muted'):
                self.cmd(self.a, action, target=target, text='hello')
        self.cmd(self.a, 'join', target=self.b)

    def test_durable_blocks_and_session_ignore_prevent_contact_both_directions(self):
        self.friend()
        self.cmd(self.a, 'block', target=self.b)
        self.restart()
        self.assertTrue(self.game.social.state(self.a)['friends'][0]['blocked'])
        self.assertEqual(self.game.social.state(self.a)['blocked'][0]['id'], self.b)
        for actor, target in ((self.a, self.b), (self.b, self.a)):
            for action in ('message', 'invite', 'join'):
                with self.assertRaisesRegex(Rejected, 'blocked'):
                    self.cmd(actor, action, target=target, text='hello')
        self.cmd(self.a, 'unblock', target=self.b)
        self.game.players[self.b]['ignore'].add(self.a)
        with self.assertRaisesRegex(Rejected, 'blocked'):
            self.cmd(self.a, 'message', target=self.b, text='hello')
        self.cmd(self.b, 'unblock', target=self.a)
        self.cmd(self.a, 'message', target=self.b, text='hello')

    def test_blocks_cancel_both_pending_requests_and_survive_restart(self):
        self.cmd(self.a, 'request', target=self.b)
        self.cmd(self.b, 'block', target=self.a)
        self.assertFalse(self.game.social.state(self.a)['outgoing'])
        with self.assertRaisesRegex(Rejected, 'blocked'):
            self.cmd(self.a, 'request', target=self.b)
        self.restart()
        self.assertTrue(self.game.social.blocked(self.a, self.b))

    def test_join_uses_current_friend_world_safe_spawn_and_cancels_trade(self):
        self.friend()
        self.store.create_world('BLOSSOM', 'forest')
        self.game.travel(self.game.players[self.b], {'world': 'BLOSSOM'})
        self.game.command(self.a, {'type': 'trade_request', 'request': uuid.uuid4().hex, 'player': self.c})
        self.game.command(self.c, {'type': 'trade_accept', 'request': uuid.uuid4().hex, 'player': self.a})
        inventory = deepcopy(self.game.players[self.a]['inventory'])
        self.cmd(self.a, 'join', target=self.b, world='INJECTED', x=-999)
        p = self.game.players[self.a]
        self.assertEqual(p['world'], 'BLOSSOM')
        self.assertFalse(self.game.world('BLOSSOM').collides(p['x'], p['y']))
        self.assertFalse(self.game.trades)
        self.assertIsNone(self.game.players[self.c]['trade'])
        self.assertEqual(p['inventory'], inventory)
        self.game.leave(self.b)
        with self.assertRaisesRegex(Rejected, 'offline'):
            self.cmd(self.a, 'join', target=self.b)

    def test_world_invite_targets_only_online_friend_and_has_server_expiry(self):
        self.friend()
        self.cmd(self.a, 'invite', target=self.b, world='FAKE', expires=99999999)
        invite = self.messages('world_invite', self.b)[0]
        self.assertEqual(invite['id'], self.a)
        self.assertEqual(invite['name'], 'Aster')
        self.assertEqual(invite['world'], 'NEXUS')
        self.assertEqual(invite['expires'], self.now+120)
        self.assertFalse(self.messages('world_invite', self.c))
        with self.assertRaisesRegex(Rejected, 'wait'):
            self.game.command(self.a, {'type': 'social_action', 'request': uuid.uuid4().hex, 'action': 'invite', 'target': self.b})

    def test_favorites_are_personalized_persistent_and_idempotent(self):
        self.store.create_world('BLOSSOM', 'forest')
        self.cmd(self.a, 'favorite', world='blossom', favorite=True)
        self.cmd(self.a, 'favorite', world='BLOSSOM', favorite=True)
        self.restart()
        worlds_a = {w['name']: w for w in self.game.social.catalogue(self.game.players[self.a])}
        worlds_b = {w['name']: w for w in self.game.social.catalogue(self.game.players[self.b])}
        self.assertTrue(worlds_a['BLOSSOM']['favorite'])
        self.assertFalse(worlds_b['BLOSSOM']['favorite'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM world_favorites').fetchone()[0], 1)
        self.cmd(self.a, 'favorite', world='BLOSSOM', favorite=False)
        self.assertFalse(self.store.db.execute('SELECT 1 FROM world_favorites').fetchone())

    def test_favorites_survive_world_metadata_updates(self):
        self.cmd(self.a, 'favorite', world='NEXUS', favorite=True)
        meta = self.store.load_world('NEXUS').meta
        meta['guest_build'] = False
        self.store.save_meta(meta)
        nexus = next(w for w in self.game.social.catalogue(self.game.players[self.a]) if w['name'] == 'NEXUS')
        self.assertTrue(nexus['favorite'])
        self.assertFalse(nexus['guest_build'])

    def test_catalogue_search_biome_sort_online_and_featured(self):
        for name, biome, created in (('BLOSSOM', 'forest', 10), ('DUNES', 'desert', 20), ('FROST', 'snow', 30)):
            w = self.store.create_world(name, biome)
            w.meta.update(created=created, owner_name='Aster' if name == 'DUNES' else '')
            self.store.save_meta(w.meta)
        p = self.game.players[self.a]
        catalog = self.game.social.catalogue(p)
        self.assertEqual(catalog[0]['name'], 'NEXUS')
        self.assertTrue(catalog[0]['featured'])
        self.assertEqual(catalog[0]['online'], 3)
        self.assertEqual([w['name'] for w in self.game.social.catalogue(p, {'search': 'aStEr'})], ['DUNES'])
        self.assertEqual([w['name'] for w in self.game.social.catalogue(p, {'biome': 'snow'})], ['FROST'])
        self.assertEqual([w['name'] for w in self.game.social.catalogue(p, {'search': 'f', 'sort': 'newest'})], ['FROST'])
        names = [w['name'] for w in self.game.social.catalogue(p, {'sort': 'name'})]
        self.assertEqual(names, sorted(names))
        self.game.travel(self.game.players[self.b], {'world': 'FROST'})
        catalog = self.game.social.catalogue(p, {'sort': 'online'})
        self.assertEqual(catalog[0]['name'], 'NEXUS')
        self.assertEqual(catalog[1]['name'], 'FROST')
        self.assertEqual(catalog[1]['online'], 1)

    def test_catalogue_rejects_invalid_filters_and_favorites(self):
        for data in ({'search': []}, {'search': 'x'*33}, {'biome': {}}, {'sort': 'unsafe'}):
            with self.assertRaises(Rejected):
                self.game.command(self.a, {'type': 'directory', **data})
        for favorite in ('true', 1, None):
            with self.assertRaises(Rejected):
                self.cmd(self.a, 'favorite', world='NEXUS', favorite=favorite)
        with self.assertRaises(Rejected):
            self.cmd(self.a, 'favorite', world='MISSING', favorite=True)

    def test_create_world_updates_every_online_catalogue(self):
        self.game.command(self.a, {'type': 'create_world', 'request': uuid.uuid4().hex, 'world': 'BLOSSOM', 'biome': 'forest'})
        for ident in (self.a, self.b, self.c):
            directories = self.messages('directory', ident)
            self.assertTrue(directories, 'Every online explorer receives the new world catalogue.')
            entry = next(w for w in directories[-1]['worlds'] if w['name'] == 'BLOSSOM')
            self.assertEqual(entry['online'], 1)
            self.assertFalse(entry['favorite'])

    def test_presence_refreshes_friends_without_disclosing_to_unrelated_players(self):
        self.friend()
        self.game.leave(self.a)
        self.game.outbox.clear()
        self.game.social.presence_changed(self.a)
        self.assertFalse(self.messages('social_state', self.c))
        friends = self.messages('social_state', self.b)[0]['friends']
        self.assertFalse(friends[0]['online'])
        self.assertEqual(friends[0]['world'], '')

    def test_failed_accept_rolls_back_friendship_pending_request_and_events(self):
        self.cmd(self.a, 'request', target=self.b)
        before = len(self.game.outbox)
        with patch.object(self.store, 'audit', side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(sqlite3.OperationalError):
                self.cmd(self.b, 'accept', target=self.a)
        self.assertFalse(self.game.social.friends(self.a, self.b))
        self.assertEqual(len(self.game.social.state(self.b)['incoming']), 1)
        self.assertEqual(len(self.game.outbox), before)

    def test_request_rate_limit_rejects_without_consuming_pending_slots(self):
        self.cmd(self.a, 'request', target=self.b)
        with self.assertRaisesRegex(Rejected, 'wait'):
            self.game.command(self.a, {'type': 'social_action', 'request': uuid.uuid4().hex, 'action': 'request', 'target': self.c})
        self.assertEqual(len(self.game.social.state(self.a)['outgoing']), 1)

    def test_banned_target_cannot_receive_new_requests_or_contact(self):
        self.store.ban_account(self.b, self.c, 'Test moderation', self.now)
        with self.assertRaisesRegex(Rejected, 'banned'):
            self.cmd(self.a, 'request', target=self.b)

    def test_world_chat_honors_durable_blocks(self):
        self.cmd(self.a, 'block', target=self.b)
        self.game.outbox.clear()
        self.game.command(self.b, {'type': 'chat', 'text': 'Hello explorers'})
        self.assertFalse(self.messages('chat', self.a))
        self.assertTrue(self.messages('chat', self.c))

    def test_block_cancels_active_trade_and_invitations_without_item_loss(self):
        self.game.command(self.a, {'type': 'trade_request', 'request': uuid.uuid4().hex, 'player': self.b})
        self.game.command(self.b, {'type': 'trade_accept', 'request': uuid.uuid4().hex, 'player': self.a})
        before_a = deepcopy(self.game.players[self.a]['inventory'])
        before_b = deepcopy(self.game.players[self.b]['inventory'])
        self.cmd(self.a, 'block', target=self.b)
        self.assertFalse(self.game.trades)
        self.assertEqual(self.game.players[self.a]['inventory'], before_a)
        self.assertEqual(self.game.players[self.b]['inventory'], before_b)
        with self.assertRaisesRegex(Rejected, 'blocked'):
            self.game.command(self.b, {'type': 'trade_request', 'request': uuid.uuid4().hex, 'player': self.a})
        self.cmd(self.a, 'unblock', target=self.b)
        self.game.command(self.b, {'type': 'trade_request', 'request': uuid.uuid4().hex, 'player': self.a})
        self.assertIn(self.a, self.game.invites)
        self.cmd(self.a, 'block', target=self.b)
        self.assertNotIn(self.a, self.game.invites)

    def test_muted_player_can_accept_existing_friend_request(self):
        self.cmd(self.a, 'request', target=self.b)
        self.store.mute_account(self.b, self.c, self.now+600)
        self.cmd(self.b, 'accept', target=self.a)
        self.assertTrue(self.game.social.friends(self.a, self.b))

    def test_trade_accept_revalidates_session_blocks_after_invitation(self):
        self.game.command(self.a, {'type': 'trade_request', 'request': uuid.uuid4().hex, 'player': self.b})
        # Revalidate at acceptance even if an older invitation survived a block.
        self.game.players[self.b]['ignore'].add(self.a)
        before_a = deepcopy(self.game.players[self.a]['inventory'])
        before_b = deepcopy(self.game.players[self.b]['inventory'])
        with self.assertRaisesRegex(Rejected, 'blocked'):
            self.game.command(self.b, {'type': 'trade_accept', 'request': uuid.uuid4().hex, 'player': self.a})
        self.assertFalse(self.game.trades)
        self.assertEqual(self.game.players[self.a]['inventory'], before_a)
        self.assertEqual(self.game.players[self.b]['inventory'], before_b)

    def test_session_ignore_cancels_live_trade_without_exchanging_assets(self):
        self.game.command(self.a, {'type': 'trade_request', 'request': uuid.uuid4().hex, 'player': self.b})
        self.game.command(self.b, {'type': 'trade_accept', 'request': uuid.uuid4().hex, 'player': self.a})
        trade = self.game.trades[self.game.players[self.a]['trade']]
        old_id = trade['id']
        self.game.command(self.a, {'type': 'trade_offer', 'request': uuid.uuid4().hex, 'trade_id': old_id, 'offer': {'wood': 2}})
        before_a = deepcopy(self.game.players[self.a]['inventory'])
        before_b = deepcopy(self.game.players[self.b]['inventory'])
        self.game.command(self.b, {'type': 'ignore', 'player': self.a})
        self.assertFalse(self.game.trades)
        self.assertIsNone(self.game.players[self.a]['trade'])
        self.assertIsNone(self.game.players[self.b]['trade'])
        with self.assertRaises(Rejected):
            self.game.command(self.a, {'type': 'trade_lock', 'request': uuid.uuid4().hex, 'trade_id': old_id, 'revision': 1})
        self.assertEqual(self.game.players[self.a]['inventory'], before_a)
        self.assertEqual(self.game.players[self.b]['inventory'], before_b)

    def test_session_ignore_removes_pending_trade_invitation(self):
        self.game.command(self.a, {'type': 'trade_request', 'request': uuid.uuid4().hex, 'player': self.b})
        self.game.command(self.b, {'type': 'ignore', 'player': self.a})
        self.assertNotIn(self.b, self.game.invites)
        with self.assertRaises(Rejected):
            self.game.command(self.b, {'type': 'trade_accept', 'request': uuid.uuid4().hex, 'player': self.a})
        self.assertFalse(self.game.trades)

    def test_session_ignore_rejects_unknown_self_and_oversized_targets(self):
        for target in ('unknown-id', self.a, 'x'*16000, [], None):
            with self.assertRaises(Rejected):
                self.game.command(self.a, {'type': 'ignore', 'player': target})
        self.assertFalse(self.game.players[self.a]['ignore'])

    def test_session_ignore_is_bounded_and_full_list_can_be_unblocked(self):
        targets = [self.extra(n) for n in range(101)]
        for target in targets[:100]:
            self.game.command(self.a, {'type': 'ignore', 'player': target})
        with self.assertRaises(Rejected):
            self.game.command(self.a, {'type': 'ignore', 'player': targets[100]})
        self.assertEqual(len(self.game.players[self.a]['ignore']), 100)
        self.game.command(self.a, {'type': 'ignore', 'player': targets[0]})
        self.game.command(self.a, {'type': 'ignore', 'player': targets[100]})
        self.assertEqual(len(self.game.players[self.a]['ignore']), 100)

    def test_world_chat_rejects_control_only_text_without_broadcast(self):
        for text in ('\x00'*5, '\x1b'*3, '\t \n'):
            with self.assertRaises(Rejected):
                self.game.command(self.a, {'type': 'chat', 'text': text})
        self.assertFalse(self.messages('chat'))

    def test_world_metadata_update_preserves_favorites_and_existing_tiles(self):
        w = self.store.create_world('BLOSSOM', 'forest')
        self.store.tile('BLOSSOM', 12, 20, 'stone')
        self.cmd(self.a, 'favorite', world='BLOSSOM', favorite=True)
        w.meta['owner_name'] = 'Aster'
        self.store.save_meta(w.meta)
        loaded = self.store.load_world('BLOSSOM')
        self.assertEqual(loaded.tile(12, 20), 'stone')
        self.assertTrue(next(w for w in self.game.social.catalogue(self.game.players[self.a]) if w['name'] == 'BLOSSOM')['favorite'])

    def test_favorite_sort_and_live_presence_broadcast_are_personalized(self):
        self.store.create_world('BLOSSOM', 'forest')
        self.cmd(self.a, 'favorite', world='BLOSSOM', favorite=True)
        self.game.outbox.clear()
        self.game.social.broadcast_directory()
        a_catalog = self.messages('directory', self.a)[0]['worlds']
        b_catalog = self.messages('directory', self.b)[0]['worlds']
        self.assertTrue(next(w for w in a_catalog if w['name'] == 'BLOSSOM')['favorite'])
        self.assertFalse(next(w for w in b_catalog if w['name'] == 'BLOSSOM')['favorite'])
        favorites = self.game.social.catalogue(self.game.players[self.a], {'sort': 'favorites'})
        self.assertEqual(favorites[0]['name'], 'BLOSSOM')


class SocialNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'network.sqlite3'
        self.clients = []
        await self.start()

    async def start(self):
        self.store = Store(self.path)
        self.gateway = Gateway(Game(self.store))
        self.server = await serve(self.gateway.connection, '127.0.0.1', 0, max_size=16384)
        self.port = self.server.sockets[0].getsockname()[1]
        self.ticks = asyncio.create_task(self.gateway.run_ticks())

    async def stop(self):
        for ws in self.clients:
            await ws.close()
        self.clients.clear()
        self.server.close()
        await self.server.wait_closed()
        self.ticks.cancel()
        try:
            await self.ticks
        except asyncio.CancelledError:
            pass
        self.store.close()

    async def asyncTearDown(self):
        await self.stop()
        self.temp.cleanup()

    async def receive(self, ws, kind, predicate=lambda message: True):
        async def wait():
            while True:
                message = json.loads(await ws.recv())
                if message['type'] == kind and predicate(message):
                    return message
                if message['type'] == 'error' and kind != 'error':
                    self.fail(message['text'])
        return await asyncio.wait_for(wait(), 4)

    async def auth(self, name=None, token=None):
        ws = await connect('ws://127.0.0.1:'+str(self.port), max_size=2**22)
        self.clients.append(ws)
        packet = {'type': 'auth', 'token': token} if token else {
            'type': 'auth', 'name': name, 'password': 'network-password', 'register': True}
        await ws.send(json.dumps(packet))
        return ws, await self.receive(ws, 'welcome')

    async def action(self, ws, action, **data):
        request = uuid.uuid4().hex
        await ws.send(json.dumps({'type': 'social_action', 'request': request, 'action': action, **data}))
        await self.receive(ws, 'ack', lambda message: message['request'] == request)

    async def test_two_real_clients_friend_messages_world_invites_and_join(self):
        a, wa = await self.auth('SocialA')
        b, wb = await self.auth('SocialB')
        await self.action(a, 'request', target='socialb')
        state = await self.receive(b, 'social_state', lambda message: bool(message['incoming']))
        self.assertEqual(state['incoming'][0]['id'], wa['id'])
        await self.action(b, 'accept', target=wa['id'])
        state = await self.receive(a, 'social_state', lambda message: bool(message['friends']))
        self.assertEqual(state['friends'][0]['id'], wb['id'])
        await self.action(a, 'message', target=wb['id'], text='Meet at my forest!')
        message = await self.receive(b, 'private_message')
        self.assertEqual(message['name'], 'SocialA')
        self.assertEqual(message['text'], 'Meet at my forest!')
        request = uuid.uuid4().hex
        await a.send(json.dumps({'type': 'create_world', 'request': request, 'world': 'SOCIAL_HOME', 'biome': 'forest'}))
        await self.receive(a, 'ack', lambda message: message['request'] == request)
        catalog = await self.receive(b, 'directory', lambda message: any(w['name'] == 'SOCIAL_HOME' for w in message['worlds']))
        self.assertEqual(next(w['online'] for w in catalog['worlds'] if w['name'] == 'SOCIAL_HOME'), 1)
        await self.action(a, 'invite', target=wb['id'])
        invite = await self.receive(b, 'world_invite')
        self.assertEqual(invite['world'], 'SOCIAL_HOME')
        request = uuid.uuid4().hex
        await b.send(json.dumps({'type': 'social_action', 'request': request, 'action': 'join', 'target': wa['id'], 'world': 'FAKE'}))
        world = await self.receive(b, 'world')
        self.assertEqual(world['world']['meta']['name'], 'SOCIAL_HOME')
        await self.receive(b, 'ack', lambda message: message['request'] == request)
        players = await self.receive(a, 'players', lambda message: len(message['players']) == 2)
        self.assertEqual({p['id'] for p in players['players']}, {wa['id'], wb['id']})

    async def test_friends_and_personal_favorites_survive_real_server_restart(self):
        a, wa = await self.auth('PersistentA')
        b, wb = await self.auth('PersistentB')
        await self.action(a, 'request', target=wb['id'])
        await self.action(b, 'accept', target=wa['id'])
        await self.action(a, 'favorite', world='NEXUS', favorite=True)
        await self.stop()
        await self.start()
        a, resumed_a = await self.auth(token=wa['token'])
        b, resumed_b = await self.auth(token=wb['token'])
        await a.send(json.dumps({'type': 'social_open'}))
        state = await self.receive(a, 'social_state', lambda message: bool(message['friends']) and message['friends'][0]['online'])
        self.assertEqual(state['friends'][0]['id'], resumed_b['id'])
        await a.send(json.dumps({'type': 'directory'}))
        a_catalog = await self.receive(a, 'directory')
        await b.send(json.dumps({'type': 'directory'}))
        b_catalog = await self.receive(b, 'directory')
        self.assertTrue(next(w['favorite'] for w in a_catalog['worlds'] if w['name'] == 'NEXUS'))
        self.assertFalse(next(w['favorite'] for w in b_catalog['worlds'] if w['name'] == 'NEXUS'))
        self.assertEqual(resumed_a['id'], wa['id'])

    async def test_nonfriend_and_blocked_client_packets_are_rejected(self):
        a, wa = await self.auth('GuardA')
        b, wb = await self.auth('GuardB')
        await a.send(json.dumps({'type': 'social_action', 'request': uuid.uuid4().hex, 'action': 'message',
                                 'target': wb['id'], 'text': 'Unsolicited'}))
        self.assertIn('accepted friends', (await self.receive(a, 'error'))['text'])
        await self.action(a, 'request', target=wb['id'])
        await self.action(b, 'accept', target=wa['id'])
        await self.action(b, 'block', target=wa['id'])
        await a.send(json.dumps({'type': 'social_action', 'request': uuid.uuid4().hex, 'action': 'message',
                                 'target': wb['id'], 'text': 'Blocked'}))
        self.assertIn('blocked', (await self.receive(a, 'error'))['text'])
