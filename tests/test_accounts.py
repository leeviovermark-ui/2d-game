"""Real account recovery, password changes and saved-session security."""
import asyncio
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from server.accounts import Accounts, recovery_digest
from server.inventory import Rejected
from server.storage import SessionExpired, Store


class AccountSecurity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'accounts.sqlite3'
        self.store = Store(self.path)
        self.accounts = Accounts(self.store)
        self.ident, self.token = await self.store.authenticate_async('Explorer', 'original-password', True)
        self.code = self.store.take_registration_recovery(self.ident)

    async def asyncTearDown(self):
        self.store.close()
        self.temp.cleanup()

    async def change(self, **values):
        return await self.accounts.handle(self.ident, {'type': 'account_password',
            'current_password': 'original-password', 'new_password': 'different-password', **values}, self.token)

    async def recover(self, **values):
        return await self.accounts.handle(None, {'type': 'recovery_reset', 'name': 'explorer',
            'recovery_code': self.code, 'new_password': 'recovered-password', **values})

    def test_registration_recovery_is_one_time_delivery_and_hash_only(self):
        self.assertIsNotNone(self.code)
        self.assertIsNone(self.store.take_registration_recovery(self.ident))
        row = self.store.db.execute('SELECT recovery_hash,recovery_expires FROM accounts_security WHERE account=?',
                                    (self.ident,)).fetchone()
        self.assertEqual(row[0], recovery_digest(self.code))
        self.assertNotIn(self.code, repr(list(self.store.db.iterdump())))
        self.assertNotIn('original-password', repr(list(self.store.db.iterdump())))
        info = self.accounts.info(self.ident, self.token)
        self.assertTrue(info['recovery_configured'])
        self.assertEqual(info['saved_sessions'], 1)
        self.assertNotIn('recovery_code', info)

    async def test_password_change_keeps_current_token_and_revokes_other_devices(self):
        _, older_token = await self.store.authenticate_async('EXPLORER', 'original-password')
        answer = await self.change()
        self.assertEqual(answer['action'], 'password_change')
        self.assertEqual(self.store.resume(self.token), self.ident)
        with self.assertRaises(SessionExpired):
            self.store.resume(older_token)
        with self.assertRaises(Rejected):
            self.store.authenticate('Explorer', 'original-password')
        self.assertEqual(self.store.authenticate('EXPLORER', 'different-password')[0], self.ident)
        self.assertEqual(self.store.db.execute('SELECT recovery_hash FROM accounts_security WHERE account=?',
                                               (self.ident,)).fetchone()[0], recovery_digest(self.code))

    async def test_wrong_current_password_changes_nothing(self):
        original = self.accounts._credentials(self.ident)
        with self.assertRaisesRegex(Rejected, 'incorrect'):
            await self.change(current_password='wrong-password')
        self.assertEqual(self.accounts._credentials(self.ident), original)
        self.assertEqual(self.store.resume(self.token), self.ident)

    async def test_invalid_password_and_name_do_not_reach_hashing(self):
        with patch.object(self.store, '_password_digest') as digest:
            for new in (None, 123, 'short', 'x'*129, '\ud800password'):
                with self.assertRaises(Rejected):
                    await self.change(new_password=new)
            for name in ('a', 'Has spaces', '!!', '', None, 'x'*21):
                with self.assertRaises(Rejected):
                    await self.store.authenticate_async(name, 'valid-password', True)
            with self.assertRaises(Rejected):
                await self.store.authenticate_async('Boolean', 'valid-password', 1)
            digest.assert_not_called()

    async def test_same_password_rejected(self):
        with self.assertRaisesRegex(Rejected, 'different'):
            await self.change(new_password='original-password')

    async def test_unicode_password_is_supported_without_normalization(self):
        await self.change(new_password='Sisu-\u00e4\u00f6\U0001f9ed-password')
        self.assertEqual(self.store.authenticate('Explorer', 'Sisu-\u00e4\u00f6\U0001f9ed-password')[0], self.ident)
        with self.assertRaises(Rejected):
            self.store.authenticate('Explorer', 'Sisu-ao\U0001f9ed-password')

    async def test_recovery_resets_password_revokes_every_token_and_rotates_code(self):
        _, other = await self.store.authenticate_async('Explorer', 'original-password')
        result = await self.recover(recovery_code=self.code.lower().replace('-', ' '))
        self.assertEqual(result['account_id'], self.ident)
        self.assertNotEqual(result['recovery_code'], self.code)
        for token in (self.token, other):
            with self.assertRaises(SessionExpired):
                self.store.resume(token)
        with self.assertRaises(Rejected):
            self.store.authenticate('Explorer', 'original-password')
        self.assertEqual(self.store.authenticate('EXPLORER', 'recovered-password')[0], self.ident)
        with self.assertRaisesRegex(Rejected, 'invalid or expired'):
            await self.recover()
        fresh = await self.recover(recovery_code=result['recovery_code'], new_password='recovered-again')
        self.assertNotEqual(fresh['recovery_code'], result['recovery_code'])

    async def test_wrong_unknown_and_expired_recovery_have_same_rejection(self):
        initial = self.accounts._credentials(self.ident)
        for values in ({'recovery_code': 'AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA'},
                       {'name': 'NoSuchExplorer'}, {'recovery_code': 'not a code'}):
            with self.assertRaisesRegex(Rejected, '^Recovery code is invalid or expired\\.$'):
                await self.recover(**values)
        self.store.db.execute('UPDATE accounts_security SET recovery_expires=1 WHERE account=?', (self.ident,))
        with self.assertRaisesRegex(Rejected, '^Recovery code is invalid or expired\\.$'):
            await self.recover()
        self.assertEqual(self.accounts._credentials(self.ident)[:2], initial[:2])
        self.assertEqual(self.store.resume(self.token), self.ident)

    async def test_two_simultaneous_resets_consume_code_once(self):
        results = await asyncio.gather(self.recover(new_password='first-new-password'),
                                       self.recover(new_password='second-new-password'), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum(isinstance(result, Rejected) for result in results), 1)
        successful = [self.store.authenticate('Explorer', password) for password in
                      ['first-new-password'] if self._accepts(password)]
        if not successful:
            successful = [self.store.authenticate('Explorer', 'second-new-password')]
        self.assertEqual(successful[0][0], self.ident)

    def _accepts(self, password):
        try:
            self.store.authenticate('Explorer', password)
            return True
        except Rejected:
            return False

    async def test_rotating_code_requires_password_and_invalidates_previous_code(self):
        with self.assertRaisesRegex(Rejected, 'incorrect'):
            await self.accounts.handle(self.ident, {'type':'account_recovery_rotate', 'password':'wrong-password'}, self.token)
        result = await self.accounts.handle(self.ident, {'type':'account_recovery_rotate', 'password':'original-password'}, self.token)
        self.assertEqual(result['action'], 'recovery_rotate')
        with self.assertRaises(Rejected):
            await self.recover()
        self.assertEqual(self.store.resume(self.token), self.ident)
        await self.recover(recovery_code=result['recovery_code'])

    async def test_logout_revokes_only_authenticated_device(self):
        _, other = await self.store.authenticate_async('Explorer', 'original-password')
        self.accounts.logout(self.ident, self.token)
        with self.assertRaises(SessionExpired):
            self.store.resume(self.token)
        self.assertEqual(self.store.resume(other), self.ident)

    async def test_cannot_revoke_another_account_session(self):
        stranger, stranger_token = await self.store.authenticate_async('Stranger', 'stranger-password', True)
        with self.assertRaises(Rejected):
            self.accounts.logout(stranger, self.token)
        self.assertEqual(self.store.resume(self.token), self.ident)
        self.assertEqual(self.store.resume(stranger_token), stranger)

    async def test_clear_saved_sessions_keeps_current_device_and_requires_password(self):
        _, other = await self.store.authenticate_async('Explorer', 'original-password')
        with self.assertRaises(Rejected):
            await self.accounts.handle(self.ident, {'type':'account_sessions_clear', 'password':'wrong-password'}, self.token)
        await self.accounts.handle(self.ident, {'type':'account_sessions_clear', 'password':'original-password'}, self.token)
        with self.assertRaises(SessionExpired):
            self.store.resume(other)
        self.assertEqual(self.store.resume(self.token), self.ident)

    def test_saved_session_cap_and_expired_session_classification(self):
        tokens = [self.token]
        for _ in range(10):
            tokens.append(self.store.authenticate('explorer', 'original-password')[1])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM sessions WHERE account=?', (self.ident,)).fetchone()[0], 8)
        self.assertEqual(self.store.resume(tokens[-1]), self.ident)
        with self.assertRaises(SessionExpired) as expired:
            self.store.resume(tokens[0])
        self.assertEqual(expired.exception.code, 'session_expired')
        self.store.db.execute('UPDATE sessions SET expires=1 WHERE token=?', (self.store.session_hash(tokens[-1]),))
        with self.assertRaises(SessionExpired):
            self.store.resume(tokens[-1])

    async def test_ban_prevents_recovery_and_password_change(self):
        self.store.ban_account(self.ident, self.ident, 'test ban')
        with self.assertRaisesRegex(Rejected, 'banned'):
            await self.recover()
        with self.assertRaises(Rejected):
            await self.change()
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM sessions WHERE account=?', (self.ident,)).fetchone()[0], 0)

    async def test_password_change_and_recovery_survive_server_restart(self):
        await self.change()
        self.store.close()
        self.store = Store(self.path)
        self.accounts = Accounts(self.store)
        self.assertEqual(self.store.resume(self.token), self.ident)
        result = await self.recover()
        self.store.close()
        self.store = Store(self.path)
        self.accounts = Accounts(self.store)
        self.assertEqual(self.store.authenticate('Explorer', 'recovered-password')[0], self.ident)
        with self.assertRaises(Rejected):
            await self.recover()
        await self.recover(recovery_code=result['recovery_code'])

    async def test_old_save_migrates_without_losing_password_session_or_inventory(self):
        old_player = self.store.player(self.ident)
        self.store.close()
        db = sqlite3.connect(self.path)
        db.executescript('DROP TABLE accounts_security; DROP TABLE admin_roles; DROP TABLE pending_admins; '
                        'DROP TABLE moderation; UPDATE schema_version SET version=1;')
        db.close()
        self.store = Store(self.path)
        self.accounts = Accounts(self.store)
        self.assertEqual(self.store.resume(self.token), self.ident)
        self.assertEqual(self.store.authenticate('EXPLORER', 'original-password')[0], self.ident)
        self.assertEqual(self.store.player(self.ident)['inventory'], old_player['inventory'])
        self.assertFalse(self.accounts.info(self.ident, self.token)['recovery_configured'])
        result = await self.accounts.handle(self.ident, {'type':'account_recovery_rotate', 'password':'original-password'}, self.token)
        await self.recover(recovery_code=result['recovery_code'])

    async def test_security_save_failure_rolls_back_password_sessions_and_audit(self):
        _, other = await self.store.authenticate_async('Explorer', 'original-password')
        before = self.accounts._credentials(self.ident)
        with patch.object(self.store, 'audit', side_effect=sqlite3.OperationalError('simulated disk error')):
            with self.assertRaises(sqlite3.OperationalError):
                await self.change()
        self.assertEqual(self.accounts._credentials(self.ident), before)
        self.assertEqual(self.store.resume(self.token), self.ident)
        self.assertEqual(self.store.resume(other), self.ident)

    async def test_hash_runs_off_thread_and_revoked_token_cannot_finish_change(self):
        loop = asyncio.get_running_loop()
        started, released = asyncio.Event(), threading.Event()
        threads = []
        original = self.store._password_digest

        def blocked(password, salt):
            threads.append(threading.get_ident())
            loop.call_soon_threadsafe(started.set)
            if not released.wait(2):
                raise RuntimeError('Hash blocked event loop')
            return original(password, salt)

        with patch.object(self.store, '_password_digest', side_effect=blocked):
            task = asyncio.create_task(self.change())
            try:
                await asyncio.wait_for(started.wait(), 1)
                self.assertNotIn(threading.get_ident(), threads)
                self.accounts.logout(self.ident, self.token)
            finally:
                released.set()
            with self.assertRaises(SessionExpired):
                await task
        self.assertEqual(self.store.authenticate('Explorer', 'original-password')[0], self.ident)

    async def test_cancelled_security_hash_does_not_commit(self):
        loop = asyncio.get_running_loop()
        started, released = asyncio.Event(), threading.Event()
        original = self.store._password_digest
        before = self.accounts._credentials(self.ident)

        def blocked(password, salt):
            loop.call_soon_threadsafe(started.set)
            released.wait(2)
            return original(password, salt)

        with patch.object(self.store, '_password_digest', side_effect=blocked):
            task = asyncio.create_task(self.change())
            try:
                await asyncio.wait_for(started.wait(), 1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                released.set()
        self.assertEqual(self.accounts._credentials(self.ident), before)
        self.assertEqual(self.store.resume(self.token), self.ident)


if __name__ == '__main__':
    unittest.main()
