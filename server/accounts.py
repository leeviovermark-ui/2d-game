"""Password settings and offline recovery without an email service.

Only password hashing runs on worker threads. SQL validation/finalization remains
on the authority's event loop; every security change rechecks its original state
after hashing and commits credentials, session revocation and audit together.
"""
import asyncio
import base64
import hashlib
import hmac
import re
import secrets
import time
from .inventory import require

RECOVERY_LIFETIME = 365 * 86400


def new_recovery_code():
    value = base64.b32encode(secrets.token_bytes(20)).decode('ascii')
    return '-'.join(value[index:index+4] for index in range(0, len(value), 4))


def recovery_digest(code):
    require(isinstance(code, str) and len(code) <= 128, 'Recovery code is invalid or expired.')
    normalized = code.upper().replace('-', '').replace(' ', '')
    require(re.fullmatch(r'[A-Z2-7]{32}', normalized), 'Recovery code is invalid or expired.')
    return hashlib.sha256(('worldforge-recovery:'+normalized).encode()).hexdigest()


class Accounts:
    def __init__(self, store):
        self.store = store

    def _credentials(self, ident):
        row = self.store.db.execute('''SELECT a.salt,a.password,COALESCE(s.revision,0),s.recovery_hash,
            COALESCE(s.recovery_expires,0) FROM accounts a LEFT JOIN accounts_security s ON s.account=a.id
            WHERE a.id=?''', (ident,)).fetchone()
        require(row is not None, 'Account not found.')
        return row

    def _authenticated(self, ident, token):
        require(isinstance(ident, str) and self.store.resume(token) == ident, 'Sign in again to edit your account.')

    def _unchanged(self, ident, expected):
        require(self._credentials(ident) == expected, 'Account security changed. Try again.')
        self.store.assert_not_banned(ident)

    def _set_recovery(self, ident, code, expires):
        self.store.db.execute('''INSERT INTO accounts_security(account,recovery_hash,recovery_expires,revision)
            VALUES(?,?,?,1) ON CONFLICT(account) DO UPDATE SET recovery_hash=excluded.recovery_hash,
            recovery_expires=excluded.recovery_expires,revision=accounts_security.revision+1''',
            (ident, recovery_digest(code), expires))
        self.store._registration_recovery.pop(ident, None)

    def info(self, ident, token):
        self._authenticated(ident, token)
        row = self._credentials(ident)
        return {'type': 'account_result', 'action': 'info', 'text': 'Account security',
                'recovery_configured': bool(row[3]) and row[4] > time.time(), 'recovery_expires': row[4],
                'saved_sessions': self.store.db.execute('SELECT count(*) FROM sessions WHERE account=? AND expires>?',
                                                       (ident, time.time())).fetchone()[0]}

    def logout(self, ident, token):
        self._authenticated(ident, token)
        with self.store.transaction():
            self.store.revoke_session(ident, token)
            self.store.audit('account_logout', [ident], {})
        return {'type': 'account_result', 'action': 'logout', 'text': 'Signed out. This saved session was revoked.'}

    async def handle(self, ident, data, current_token=None, authorization_guard=None):
        require(isinstance(data, dict), 'Malformed account request.')
        if authorization_guard is not None:
            authorization_guard()
        action = data.get('type')
        if action == 'recovery_reset':
            require(ident is None, 'Sign out before recovering an account.')
            return await self._recover(data)
        self._authenticated(ident, current_token)
        if action == 'account_info':
            return self.info(ident, current_token)
        if action == 'account_logout':
            return self.logout(ident, current_token)
        if action == 'account_password':
            return await self._change_password(ident, data, current_token, authorization_guard)
        if action == 'account_recovery_rotate':
            return await self._rotate_recovery(ident, data, current_token, authorization_guard)
        if action == 'account_sessions_clear':
            return await self._clear_sessions(ident, data, current_token, authorization_guard)
        require(False, 'Unknown account action.')

    async def _change_password(self, ident, data, token, guard=None):
        old = self.store.validate_password(data.get('current_password'))
        new = self.store.validate_password(data.get('new_password'))
        require(old != new, 'Choose a different new password.')
        expected = self._credentials(ident)
        salt = secrets.token_hex(16)

        def hashes():
            return self.store._password_digest(old, expected[0]), self.store._password_digest(new, salt)

        old_digest, digest = await asyncio.to_thread(hashes)
        require(hmac.compare_digest(old_digest, expected[1]), 'Current password is incorrect.')
        with self.store.transaction():
            if guard is not None:
                guard()
            self._authenticated(ident, token)
            self._unchanged(ident, expected)
            self.store.db.execute('UPDATE accounts SET salt=?,password=? WHERE id=?', (salt, digest, ident))
            self.store.db.execute('''INSERT INTO accounts_security(account,revision) VALUES(?,1)
                ON CONFLICT(account) DO UPDATE SET revision=accounts_security.revision+1''', (ident,))
            self.store.db.execute('DELETE FROM sessions WHERE account=? AND token!=?', (ident, self.store.session_hash(token)))
            self.store.audit('account_password_changed', [ident], {'other_sessions_revoked': True})
        return {'type': 'account_result', 'action': 'password_change',
                'text': 'Password updated. Other saved sessions were revoked.'}

    async def _verify_password(self, ident, data, token):
        password = self.store.validate_password(data.get('password'))
        expected = self._credentials(ident)
        digest = await asyncio.to_thread(self.store._password_digest, password, expected[0])
        require(hmac.compare_digest(digest, expected[1]), 'Current password is incorrect.')
        return expected

    async def _rotate_recovery(self, ident, data, token, guard=None):
        expected = await self._verify_password(ident, data, token)
        code, expires = new_recovery_code(), time.time()+RECOVERY_LIFETIME
        with self.store.transaction():
            if guard is not None:
                guard()
            self._authenticated(ident, token)
            self._unchanged(ident, expected)
            self._set_recovery(ident, code, expires)
            self.store.audit('account_recovery_rotated', [ident], {})
        return {'type': 'account_result', 'action': 'recovery_rotate',
                'text': 'Save this new recovery code privately. The previous code no longer works.',
                'recovery_code': code, 'recovery_expires': expires}

    async def _clear_sessions(self, ident, data, token, guard=None):
        expected = await self._verify_password(ident, data, token)
        with self.store.transaction():
            if guard is not None:
                guard()
            self._authenticated(ident, token)
            self._unchanged(ident, expected)
            self.store.db.execute('DELETE FROM sessions WHERE account=? AND token!=?', (ident, self.store.session_hash(token)))
            self.store.audit('account_sessions_revoked', [ident], {})
        return {'type': 'account_result', 'action': 'sessions_clear',
                'text': 'Other saved sessions were revoked. This device stays signed in.'}

    async def _recover(self, data):
        name = self.store.validate_name(data.get('name'))
        password = self.store.validate_password(data.get('new_password'))
        code_digest = recovery_digest(data.get('recovery_code'))
        account = self.store.db.execute('SELECT id FROM accounts WHERE username=? COLLATE NOCASE', (name,)).fetchone()
        ident = account[0] if account else None
        expected = self._credentials(ident) if ident else None
        salt = secrets.token_hex(16)
        # Unknown names and wrong codes still perform the same password work.
        digest = await asyncio.to_thread(self.store._password_digest, password, salt)
        require(expected is not None and expected[3] is not None
                and hmac.compare_digest(code_digest, expected[3]) and expected[4] > time.time(),
                'Recovery code is invalid or expired.')
        code, expires = new_recovery_code(), time.time()+RECOVERY_LIFETIME
        with self.store.transaction():
            self._unchanged(ident, expected)
            require(expected[4] > time.time(), 'Recovery code is invalid or expired.')
            self.store.db.execute('UPDATE accounts SET salt=?,password=? WHERE id=?', (salt, digest, ident))
            self._set_recovery(ident, code, expires)
            self.store.db.execute('DELETE FROM sessions WHERE account=?', (ident,))
            self.store.audit('account_recovered', [ident], {'all_sessions_revoked': True})
        return {'type': 'account_result', 'action': 'recovery_reset', 'account_id': ident,
                'text': 'Password reset. All saved sessions were revoked. Save the new code, then sign in.',
                'recovery_code': code, 'recovery_expires': expires}
