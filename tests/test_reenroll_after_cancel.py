"""PATCH-005C: pendaftaran ulang membuat enrollment baru tanpa merusak riwayat.

Fake pool / SQL contract: tidak menyentuh PostgreSQL pengguna.
"""
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.repositories import enrollment_repo
from app.repositories.class_access_sql import ENROLLMENT_TERAKHIR_TERSEDIA_SQL

ROOT = Path(__file__).resolve().parent.parent


class Cursor:
    def __init__(self, *, old_status=None, price=Decimal('120000'), open_program=True,
                 quota=10, occupied=0, student=True):
        self.old_status = old_status
        self.price = price
        self.open_program = open_program
        self.quota = quota
        self.occupied = occupied
        self.student = student
        self.queries = []
        self.row = None
        self.inserted = False
        self.new_status = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        q = ' '.join(sql.lower().split())
        self.queries.append((q, params))
        if 'from students s join users u' in q:
            self.row = ({'user_id': 17, 'nama_lengkap': 'Siswa Test',
                         'email': 'tester@example.org', 'nis': 'S-999'} if self.student else None)
        elif 'from programs where id = %s for update' in q:
            self.row = {'id': 5, 'nama': 'IPA', 'kode': 'IPA', 'kuota': self.quota,
                        'status': 'buka' if self.open_program else 'tutup',
                        'harga_bulanan': self.price}
        elif q.startswith('select id, status from enrollments'):
            # Simulasi DB: query baru mengabaikan riwayat lama yang ditutup.
            assert "status in ('menunggu_pembayaran', 'menunggu', 'aktif')" in q
            self.row = ({'id': 7, 'status': self.old_status}
                        if self.old_status in {'menunggu_pembayaran', 'menunggu', 'aktif'} else None)
        elif q.startswith('select count(*) as jumlah'):
            self.row = {'jumlah': self.occupied}
        elif q.startswith('insert into enrollments'):
            self.inserted = True
            self.new_status = params[-1]
            self.row = {'id': 99, 'status': self.new_status}
        else:
            raise AssertionError(f'Query unexpected: {q[:160]}')

    def fetchone(self):
        return self.row


class Conn:
    def __init__(self, cur):
        self.cur = cur
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self, **_):
        return self.cur

    def commit(self):
        self.commits += 1


def run(monkeypatch, **kwargs):
    cur = Cursor(**kwargs)
    conn = Conn(cur)
    invoice = Mock(return_value={'id': 110, 'no_invoice': 'INV-NEW',
                                 'jumlah': kwargs.get('price', Decimal('120000'))})
    monkeypatch.setattr(enrollment_repo, 'pool', Mock(connection=lambda: conn))
    monkeypatch.setattr(enrollment_repo, 'buat_invoice_awal', invoice)
    result = enrollment_repo.buat_enrollment(17, 5)
    return result, cur, conn, invoice


@pytest.mark.parametrize('old_status', ['batal', 'ditolak', 'selesai', None])
def test_closed_history_can_create_new_paid_enrollment(monkeypatch, old_status):
    res, cur, conn, invoice = run(monkeypatch, old_status=old_status)
    assert res['berhasil'] is True
    assert res['enrollment_id'] == 99
    assert res['status'] == 'menunggu_pembayaran'
    assert res['invoice']['no_invoice'] == 'INV-NEW'
    assert cur.inserted and invoice.call_count == 1 and conn.commits == 1
    assert any('status in (' in sql for sql, _ in cur.queries)


@pytest.mark.parametrize('old_status', ['menunggu_pembayaran', 'menunggu', 'aktif'])
def test_open_enrollment_blocks_second_registration(monkeypatch, old_status):
    res, cur, conn, invoice = run(monkeypatch, old_status=old_status)
    assert res['berhasil'] is False
    assert res['alasan'] == 'sudah_terdaftar' and res['status'] == old_status
    assert not cur.inserted and invoice.call_count == 0 and conn.commits == 0


def test_free_program_reenroll_no_invoice(monkeypatch):
    res, cur, conn, invoice = run(monkeypatch, old_status='batal', price=Decimal('0'))
    assert res['berhasil'] and res['status'] == 'menunggu'
    assert res['invoice'] is None
    assert invoice.call_count == 0 and conn.commits == 1


@pytest.mark.parametrize('options,reason', [
    ({'student': False}, 'siswa_tidak_ditemukan'),
    ({'open_program': False}, 'program_tutup'),
    ({'occupied': 10}, 'kuota_penuh'),
])
def test_reenroll_respects_existing_guards(monkeypatch, options, reason):
    res, cur, conn, invoice = run(monkeypatch, old_status='batal', **options)
    assert res['berhasil'] is False and res['alasan'] == reason
    assert not cur.inserted and invoice.call_count == 0 and conn.commits == 0


def test_enrollment_scoped_access_keeps_cancelled_latest_hidden():
    expr = ENROLLMENT_TERAKHIR_TERSEDIA_SQL.lower()
    assert "e.status in ('aktif', 'selesai')" in ' '.join(expr.split())
    assert 'max(e_terakhir.id)' in expr
    assert 'e_terakhir.student_id = e.student_id' in expr
    assert 'e_terakhir.program_id = e.program_id' in expr


def test_all_academic_queries_use_latest_enrollment():
    from app.repositories import student_repo
    import inspect
    for func in [student_repo.daftar_program_akademik, student_repo.rekap_absensi,
                 student_repo.daftar_absensi, student_repo.ringkasan_nilai,
                 student_repo.daftar_nilai, student_repo.daftar_catatan_materi]:
        text = inspect.getsource(func)
        assert '{ENROLLMENT_TERAKHIR_TERSEDIA_SQL}' in text, func.__name__
        assert '{AKSES_TERKUNCI_SQL}' in text, func.__name__


def test_attendance_uses_current_enrollment_start():
    from app.repositories import student_repo
    import inspect
    for func in [student_repo.rekap_absensi, student_repo.daftar_absensi,
                 student_repo.daftar_catatan_materi]:
        assert 'cs.tanggal >= e.created_at::date' in inspect.getsource(func)


def test_schema_uses_partial_unique_not_permanent_unique():
    schema = (ROOT / 'sql/schema.sql').read_text(encoding='utf-8').lower()
    create = schema[schema.index('create table enrollments'):schema.index('create table invoices')]
    assert 'constraint uq_enrollment unique' not in create
    assert 'create unique index uq_enrollment_berjalan' in create
    assert "where status in ('menunggu_pembayaran', 'menunggu', 'aktif')" in create


def test_migration_preserves_history():
    migration = (ROOT / 'sql/migrations/20261101_patch_005c_daftar_ulang.sql').read_text().lower()
    assert 'create unique index if not exists uq_enrollment_berjalan' in migration
    assert 'alter table enrollments drop constraint if exists uq_enrollment' in migration
    assert migration.index('create unique index') < migration.index('alter table enrollments drop constraint')
    assert 'delete from enrollments' not in migration and 'truncate' not in migration


def test_admin_cancellation_retains_old_enrollment():
    import inspect
    sql = inspect.getsource(enrollment_repo.batalkan_admin).lower()
    assert "set status = 'batal'" in sql
    assert 'delete from enrollments' not in sql
    assert 'insert into payment_refunds' in sql


def test_old_registration_id_is_not_reused(monkeypatch):
    res, cur, _, invoice = run(monkeypatch, old_status='batal')
    assert res['enrollment_id'] == 99
    assert cur.inserted
    assert invoice.call_args.kwargs['enrollment_id'] == 99


def test_kelas_saya_hides_cancelled_and_rejected():
    import inspect
    from pathlib import Path
    source = (ROOT / 'app/ui/menu_siswa_academic.py').read_text(encoding='utf-8')
    section = source[source.index('def menu_kelas_saya'):source.index('def menu_jadwal_saya')]
    assert 'r.get("status") in {"menunggu_pembayaran", "menunggu", "aktif"}' in section
    assert '"KELAS SAYA", rows' in section


def test_migration_file_has_exact_two_safe_commands():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'sibima_005c_migration', ROOT / 'tools/apply_migration_005c.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cmds = module._migration_statements()
    assert len(cmds) == 2
    assert cmds[0].startswith('CREATE UNIQUE INDEX IF NOT EXISTS')
    assert cmds[1].startswith('ALTER TABLE enrollments DROP CONSTRAINT IF EXISTS')


def test_migration_check_never_changes_database(monkeypatch, capsys):
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location(
        'sibima_005c_migration_check', ROOT / 'tools/apply_migration_005c.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class DbCursor:
        def __init__(self):
            self.executed = []
            self.row = None
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, statement):
            q = ' '.join(statement.lower().split())
            self.executed.append(q)
            if 'select current_database()' in q: self.row = ('sibima_test_db',)
            elif 'duplicate_groups' in q: self.row = (0,)
            elif 'from pg_constraint' in q: self.row = (True,)
            elif 'from pg_indexes' in q: self.row = None
            else: raise AssertionError('Unexpected SQL: '+q)
        def fetchone(self): return self.row

    class DbConnection:
        def __init__(self): self.cur = DbCursor()
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def cursor(self): return self.cur

    db = DbConnection()
    import psycopg
    monkeypatch.setattr(psycopg, 'connect', lambda **kwargs: db)
    from app import config
    monkeypatch.setattr(config, 'DB_CONFIG', {'dbname':'sibima_test_db','user':'stub', 'password':'fake'})
    assert module.main(['--check']) == 0
    assert len(db.cur.executed) == 4
    assert 'Tidak ada data yang diubah.' in capsys.readouterr().out
