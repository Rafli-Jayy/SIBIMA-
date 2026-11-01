"""Regression tests PATCH-004D: forgot password with one-time OTP.

All DB operations are simulated. Live PostgreSQL/SMTP tests are separate.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services import auth_service, otp_service, email_service
from app.repositories import otp_repo


EMAIL = 'siswa@example.com'
USER = {
    'id': 9,
    'email': EMAIL,
    'email_verified': True,
    'status': 'aktif',
    'password_hash': 'old_hash',
}


def test_request_disguises_known_unknown_accounts(monkeypatch):
    sent = []
    monkeypatch.setattr(auth_service.user_repo, 'cari_by_email', lambda mail: USER if mail == EMAIL else None)
    monkeypatch.setattr(auth_service.otp_service, 'kirim_otp', lambda *a: sent.append(a) or (True, 'sent'))
    ok1, msg1 = auth_service.minta_otp_reset_password(EMAIL)
    ok2, msg2 = auth_service.minta_otp_reset_password('unknown@example.com')
    assert ok1 and ok2 and msg1 == msg2
    assert sent == [(9, 'reset_password')]


@pytest.mark.parametrize('status,verified', [
    ('nonaktif', True), ('ditolak', True), ('belum_verifikasi', False), ('aktif', False),
])
def test_request_cannot_send_to_unqualified_account(monkeypatch, status, verified):
    monkeypatch.setattr(auth_service.user_repo, 'cari_by_email', lambda *_: {**USER, 'status': status, 'email_verified': verified})
    calls = []
    monkeypatch.setattr(auth_service.otp_service, 'kirim_otp', lambda *a: calls.append(a))
    assert auth_service.minta_otp_reset_password(EMAIL)[0]
    assert calls == []


def test_request_invalid_email(monkeypatch):
    monkeypatch.setattr(auth_service.user_repo, 'cari_by_email', lambda *_: pytest.fail('no lookup on invalid email'))
    assert not auth_service.minta_otp_reset_password('not-an-email')[0]


def test_request_hides_rate_limit_and_delivery_failure(monkeypatch):
    monkeypatch.setattr(auth_service.user_repo, 'cari_by_email', lambda *_: USER)
    monkeypatch.setattr(auth_service.otp_service, 'kirim_otp', lambda *_: (False, 'rate limited'))
    status1 = auth_service.minta_otp_reset_password(EMAIL)
    def fail(*_): raise RuntimeError('no smtp')
    monkeypatch.setattr(auth_service.otp_service, 'kirim_otp', fail)
    status2 = auth_service.minta_otp_reset_password(EMAIL)
    assert status1 == status2 and status1[0]


@pytest.mark.parametrize('code', ['12', 'abcdef', '۱۲۳۴۵۶', '1234567', None, '12 456'])
def test_reset_rejects_invalid_otp_format(monkeypatch, code):
    monkeypatch.setattr(auth_service.user_repo, 'cari_by_email', lambda *_: pytest.fail('invalid otp must not touch DB'))
    assert not auth_service.reset_password(EMAIL, code, 'PasswordBaru123')[0]


@pytest.mark.parametrize('password', ['12345678', 'abcdefgh', '123abc', 'x' * 80])
def test_reset_rejects_weak_password(monkeypatch, password):
    monkeypatch.setattr(auth_service.user_repo, 'cari_by_email', lambda *_: pytest.fail('weak password must not touch DB'))
    assert not auth_service.reset_password(EMAIL, '123456', password)[0]


def test_reset_requires_eligible_account(monkeypatch):
    monkeypatch.setattr(auth_service.user_repo, 'cari_by_email', lambda *_: None)
    assert not auth_service.reset_password(EMAIL, '123456', 'PasswordBaru123')[0]


def test_reset_rejects_reused_old_password(monkeypatch):
    monkeypatch.setattr(auth_service.user_repo, 'cari_by_email', lambda *_: USER)
    monkeypatch.setattr(auth_service.security, 'verifikasi_password', lambda *_: True)
    monkeypatch.setattr(auth_service.security, 'hash_password', lambda *_: pytest.fail('same password must not be hashed'))
    assert not auth_service.reset_password(EMAIL, '123456', 'PasswordBaru123')[0]


def test_reset_forwards_hashed_password_and_otp_to_atomic_repo(monkeypatch):
    monkeypatch.setattr(auth_service.user_repo, 'cari_by_email', lambda *_: USER)
    monkeypatch.setattr(auth_service.security, 'verifikasi_password', lambda *_: False)
    monkeypatch.setattr(auth_service.security, 'hash_password', lambda _: 'new_bcrypt_hash')
    got = []
    monkeypatch.setattr(otp_repo, 'reset_password_dengan_otp', lambda **kw: got.append(kw) or (True, 'done'))
    assert auth_service.reset_password(EMAIL, '123456', 'PasswordBaru123') == (True, 'done')
    assert len(got) == 1
    assert got[0]['user_id'] == USER['id']
    assert got[0]['kode'] == '123456'
    assert got[0]['password_hash'] == 'new_bcrypt_hash'
    assert got[0]['batas_percobaan'] == auth_service.otp_service.OTP_MAX_ATTEMPTS


def test_generic_otp_verify_cannot_be_used_as_reset_authorization(monkeypatch):
    monkeypatch.setattr(otp_service.user_repo, 'cari_by_id', lambda *_: pytest.fail('must not fetch user'))
    ok, msg = otp_service.verifikasi_otp(9, '123456', 'reset_password')
    assert not ok and 'atomik' in msg


def test_email_template_has_separate_reset_context():
    reset_html = email_service._buat_html_email('123456', tujuan='reset_password')
    reg_html = email_service._buat_html_email('123456', tujuan='register')
    assert 'Atur ulang password kamu' in reset_html
    assert 'mengatur ulang password' in reset_html
    assert 'memverifikasi alamat email' in reg_html
    assert '123456' in reset_html
    assert 'Jangan bagikan kode' in reset_html


def test_cli_has_reset_menu_implementation():
    root = Path(__file__).resolve().parents[1]
    content = (root / 'app/ui/menu_auth.py').read_text(encoding='utf-8')
    assert 'def menu_lupa_password():' in content
    assert 'auth_service.minta_otp_reset_password(email)' in content
    assert 'auth_service.reset_password(email, kode.strip(), baru)' in content
    assert 'elif pilihan == "Lupa Password":' in content


class MemoryCursor:
    def __init__(self, user, otp):
        self.user = dict(user) if user is not None else None
        self.otp = dict(otp) if otp is not None else None
        self.query_log = []
        self._last = None
        self.fail_after_user_update = False

    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, params=None):
        self.query_log.append((sql, params))
        norm = ' '.join(sql.lower().split())
        if norm.startswith('select id, email_verified'):
            self._last = self.user
        elif norm.startswith('select id, code_hash'):
            self._last = self.otp if self.otp and not self.otp.get('used') else None
        elif norm.startswith('update otp_codes set attempts'):
            self.otp['attempts'] += 1
            self.otp['used'] = self.otp['attempts'] >= params[0]
        elif norm.startswith('update otp_codes set used_at'):
            self.otp['used'] = True
        elif norm.startswith('update users set password_hash'):
            self.user['password_hash'] = params[0]
            if self.fail_after_user_update:
                raise RuntimeError('db failure after user update')
        else:
            raise AssertionError('unexpected SQL: ' + norm[:100])
    def fetchone(self): return self._last


class MemoryConn:
    def __init__(self, cursor):
        self.cur = cursor
        self.commits = 0
        self.rolled_back = False
    def __enter__(self): return self
    def __exit__(self, typ, *_):
        if typ is not None:
            self.rolled_back = True
        return False
    def cursor(self, **_): return self.cur
    def commit(self): self.commits += 1


class MemoryPool:
    def __init__(self, conn): self.conn = conn
    def connection(self): return self.conn


def make_repo(monkeypatch, otp=None, user=None):
    if user is None: user = USER
    if otp is None:
        otp = {
            'id': 78, 'code_hash': 'hashed_code', 'attempts': 0,
            'expires_at': datetime.now(timezone.utc) + timedelta(minutes=5),
        }
    cur = MemoryCursor(user, otp)
    conn = MemoryConn(cur)
    monkeypatch.setattr(otp_repo, 'pool', MemoryPool(conn))
    monkeypatch.setattr(otp_repo.security, 'verifikasi_otp', lambda code, hashed: code == '123456' and hashed == 'hashed_code')
    return cur, conn


def test_atomic_success_updates_password_and_consumes_code(monkeypatch):
    cur, conn = make_repo(monkeypatch)
    ok, msg = otp_repo.reset_password_dengan_otp(9, '123456', 'new_hash', 3)
    assert ok and 'berhasil' in msg
    assert cur.user['password_hash'] == 'new_hash'
    assert cur.otp['used'] is True
    assert conn.commits == 1
    query = ' '.join(sql for sql, _ in cur.query_log)
    assert query.count('FOR UPDATE') == 2
    assert 'locked_until = NULL' in query
    assert "purpose = 'reset_password'" in query


def test_wrong_otp_has_limited_attempts_and_does_not_change_password(monkeypatch):
    cur, conn = make_repo(monkeypatch)
    for _ in range(2):
        ok, _msg = otp_repo.reset_password_dengan_otp(9, '000000', 'new_hash', 3)
        assert not ok
        assert cur.user['password_hash'] == 'old_hash'
    assert cur.otp['attempts'] == 2
    assert not cur.otp['used']
    ok, msg = otp_repo.reset_password_dengan_otp(9, '000000', 'new_hash', 3)
    assert not ok and 'Batas' in msg
    assert cur.otp['used']
    assert conn.commits == 3
    assert not otp_repo.reset_password_dengan_otp(9, '123456', 'new_hash', 3)[0]


def test_expired_code_is_consumed(monkeypatch):
    expired = {
        'id': 78, 'code_hash': 'hashed_code', 'attempts': 0,
        'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    cur, conn = make_repo(monkeypatch, otp=expired)
    assert 'kedaluwarsa' in otp_repo.reset_password_dengan_otp(9, '123456', 'new_hash', 3)[1]
    assert cur.user['password_hash'] == 'old_hash'
    assert cur.otp['used'] and conn.commits == 1


def test_consumed_otp_cannot_reset_twice(monkeypatch):
    cur, _ = make_repo(monkeypatch)
    assert otp_repo.reset_password_dengan_otp(9, '123456', 'new_hash', 3)[0]
    assert not otp_repo.reset_password_dengan_otp(9, '123456', 'another_hash', 3)[0]
    assert cur.user['password_hash'] == 'new_hash'


def test_atomic_transaction_rollback_contract(monkeypatch):
    cur, conn = make_repo(monkeypatch)
    cur.fail_after_user_update = True
    with pytest.raises(RuntimeError):
        otp_repo.reset_password_dengan_otp(9, '123456', 'new_hash', 3)
    assert conn.commits == 0
    assert conn.rolled_back
    assert not cur.otp.get('used', False)


def test_nonverified_user_denied_again_in_database_transaction(monkeypatch):
    cur, conn = make_repo(monkeypatch, user={**USER, 'email_verified': False})
    assert not otp_repo.reset_password_dengan_otp(9, '123456', 'new_hash', 3)[0]
    assert cur.user['password_hash'] == 'old_hash'
    assert conn.commits == 0


def test_otp_limit_must_be_positive(monkeypatch):
    cur, conn = make_repo(monkeypatch)
    with pytest.raises(ValueError):
        otp_repo.reset_password_dengan_otp(9, '123456', 'new_hash', 0)
    assert cur.query_log == []


def test_kirim_otp_email_respects_reset_purpose(monkeypatch):
    monkeypatch.setattr(otp_service.user_repo, 'cari_by_id', lambda *_: USER)
    monkeypatch.setattr(otp_service.otp_repo, 'hitung_kirim_terakhir', lambda *_: 0)
    monkeypatch.setattr(otp_service.otp_repo, 'simpan_otp', lambda **_: 99)
    monkeypatch.setattr(otp_service.security, 'buat_otp', lambda: '123456')
    monkeypatch.setattr(otp_service.security, 'hash_otp', lambda _: 'otp_hash')
    monkeypatch.setattr(otp_service, 'OTP_MODE', 'email')
    captures = []
    monkeypatch.setattr(otp_service.email_service, 'kirim_otp_email', lambda *a, **kw: captures.append((a, kw)) or True)
    ok, _ = otp_service.kirim_otp(9, 'reset_password')
    assert ok
    assert captures == [((EMAIL, '123456'), {'tujuan': 'reset_password'})]


def test_email_failure_invalidates_otp(monkeypatch):
    monkeypatch.setattr(otp_service.user_repo, 'cari_by_id', lambda *_: USER)
    monkeypatch.setattr(otp_service.otp_repo, 'hitung_kirim_terakhir', lambda *_: 0)
    monkeypatch.setattr(otp_service.otp_repo, 'simpan_otp', lambda **_: 99)
    monkeypatch.setattr(otp_service.security, 'buat_otp', lambda: '123456')
    monkeypatch.setattr(otp_service.security, 'hash_otp', lambda _: 'otp_hash')
    monkeypatch.setattr(otp_service, 'OTP_MODE', 'email')
    monkeypatch.setattr(otp_service.email_service, 'kirim_otp_email', lambda *a, **kw: False)
    used = []
    monkeypatch.setattr(otp_service.otp_repo, 'tandai_terpakai', lambda i: used.append(i))
    assert not otp_service.kirim_otp(9, 'reset_password')[0]
    assert used == [99]


def test_request_respects_otp_send_rate_limit(monkeypatch):
    monkeypatch.setattr(otp_service.user_repo, 'cari_by_id', lambda *_: USER)
    monkeypatch.setattr(otp_service.otp_repo, 'hitung_kirim_terakhir', lambda *_: 3)
    monkeypatch.setattr(otp_service.otp_repo, 'simpan_otp', lambda **kw: pytest.fail('must not insert'))
    assert not otp_service.kirim_otp(9, 'reset_password')[0]
