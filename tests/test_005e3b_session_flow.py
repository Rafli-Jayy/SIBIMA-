"""PATCH-005E3-B: regression tests with a fake transactional database.

This does not test real PostgreSQL migration/locking; execute migration --check and
full pytest suite on the user's computer before manual confirmation.
"""
import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / 'app/repositories/academic_repo.py'
SERVICE = ROOT / 'app/services/academic_service.py'
UI = ROOT / 'app/ui/menu_tutor_academic.py'
MIGRATION = ROOT / 'tools/apply_migration_005e3b.py'


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self.rows = []
        self.index = 0

    def execute(self, query, params=()):
        q = ' '.join(query.lower().split())
        self.state['sql'].append((q, params))
        s = self.state
        self.rows = []
        self.index = 0
        if 'select cs.id, cs.tanggal, cs.status::text' in q and 'for update of cs' in q:
            self.rows = ([{'id': 9, 'tanggal': s['today'], 'status_pertemuan': s['status'], 'program_id': 11}]
                         if s['owned'] else [])
        elif 'select distinct e.student_id' in q:
            self.rows = [{'student_id': n} for n in s['eligible']]
        elif 'select student_id from attendances where' in q:
            self.rows = [{'student_id': n} for n in s['recorded']]
        elif "update class_sessions set status = 'selesai'" in q:
            if s['status'] in ('perlu_laporan', 'terlaksana'):
                s['status'] = 'selesai'
                self.rows = [{'id': 9}]
        elif 'select cs.status::text as status_pertemuan' in q:
            self.rows = [{'status_pertemuan': s['status']}] if s['owned'] else []
        elif 'select exists (select 1 from attendances' in q:
            self.rows = [{'ada': bool(s['recorded'])}]
        elif "update class_sessions set status = 'batal'" in q:
            if s['status'] in ('perlu_laporan', 'terlaksana'):
                s['status'] = 'batal'
                s['reason'] = params[0]
                self.rows = [{'id': 9}]
        elif 'select id, hari::text as hari from schedules' in q:
            self.rows = [{'id': 7, 'hari': s['day_label']}] if s['owned'] else []
        elif 'select current_date as tanggal' in q:
            self.rows = [{'tanggal': s['today']}]
        elif 'select id, pertemuan_ke from class_sessions' in q:
            self.rows = [{'id': 9, 'pertemuan_ke': 2}] if s['existing'] else []
        elif 'select coalesce(max(pertemuan_ke)' in q:
            self.rows = [{'berikutnya': 2}]
        elif 'insert into class_sessions' in q:
            self.rows = [{'id': 9}]
        elif 'insert into activity_logs' in q:
            pass
        else:
            raise AssertionError('Unmocked SQL: ' + q[:110])

    def fetchone(self):
        value = self.rows[self.index] if self.index < len(self.rows) else None
        self.index += 1
        return value

    def fetchall(self):
        values = self.rows[self.index:]
        self.index = len(self.rows)
        return values

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConnection:
    def __init__(self, state):
        self.state = state
    def cursor(self, **kwargs):
        return FakeCursor(self.state)
    def commit(self):
        self.state['commits'] += 1
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return False


def _functions(path, names, **env):
    module = ast.parse(path.read_text(encoding='utf-8'))
    funcs = [node for node in module.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {n.name for n in funcs} == set(names)
    sandbox = dict(env)
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(path), 'exec'), sandbox)
    return sandbox


def ctx(status='perlu_laporan', eligible=(41, 42), recorded=(), owned=True,
        day_label='minggu', today=date(2026, 11, 1), existing=False):
    state = dict(status=status, eligible=tuple(eligible), recorded=tuple(recorded),
                 owned=owned, day_label=day_label, today=today, existing=existing,
                 sql=[], commits=0, reason=None)
    pool = SimpleNamespace(connection=lambda: FakeConnection(state))
    ns = _functions(REPO, ('_peserta_sesi', 'selesaikan_pertemuan', 'batalkan_pertemuan',
                           'buka_pertemuan'), pool=pool, dict_row=object())
    return SimpleNamespace(state=state, funcs=ns)


@pytest.mark.parametrize('status', ['perlu_laporan', 'terlaksana'])
def test_absensi_lengkap_baru_boleh_selesai(status):
    c = ctx(status=status, eligible=(41, 42), recorded=(41, 42))
    result = c.funcs['selesaikan_pertemuan'](7, 9)
    assert result == {'sudah_selesai': False, 'jumlah_peserta': 2}
    assert c.state['status'] == 'selesai'
    assert c.state['commits'] == 1
    assert any('for update of cs' in q for q, _ in c.state['sql'])


@pytest.mark.parametrize('eligible,recorded,fragment', [
    ((41, 42), (41,), '1 dari 2'),
    ((41, 42, 43), (), '3 dari 3'),
    ((), (), 'Belum ada peserta'),
    ((41,), (41, 99), 'di luar daftar'),
])
def test_validasi_selesai_gagal_tanpa_mengubah_status(eligible, recorded, fragment):
    c = ctx(eligible=eligible, recorded=recorded)
    with pytest.raises(ValueError, match=fragment):
        c.funcs['selesaikan_pertemuan'](7, 9)
    assert c.state['status'] == 'perlu_laporan'
    assert c.state['commits'] == 0


@pytest.mark.parametrize('status', ['batal', 'selesai'])
def test_sesi_tertutup_tidak_bisa_selesai_ulang(status):
    c = ctx(status=status, eligible=(41,), recorded=(41,))
    if status == 'batal':
        with pytest.raises(ValueError, match='dibatalkan'):
            c.funcs['selesaikan_pertemuan'](7, 9)
    else:
        assert c.funcs['selesaikan_pertemuan'](7, 9) == {'sudah_selesai': True}
    assert c.state['commits'] == 0


def test_tutor_lain_tidak_boleh_selesaikan():
    c = ctx(owned=False, eligible=(41,), recorded=(41,))
    with pytest.raises(ValueError, match='bukan milikmu'):
        c.funcs['selesaikan_pertemuan'](8, 9)


@pytest.mark.parametrize('status', ['perlu_laporan', 'terlaksana'])
def test_pembatalan_tutor_beralasan(status):
    c = ctx(status=status, recorded=())
    assert c.funcs['batalkan_pertemuan'](7, 9, 'Tutor berhalangan') is True
    assert c.state['status'] == 'batal'
    assert c.state['reason'] == 'Tutor berhalangan'
    assert c.state['commits'] == 1


@pytest.mark.parametrize('status', ['batal', 'selesai'])
def test_tak_boleh_batal_ulang(status):
    c = ctx(status=status)
    with pytest.raises(ValueError, match='tidak dapat dibatalkan ulang'):
        c.funcs['batalkan_pertemuan'](7, 9, 'Tidak berlangsung')


def test_batal_ditolak_jika_absensi_sudah_tercatat():
    c = ctx(recorded=(41,))
    with pytest.raises(ValueError, match='Sudah ada absensi'):
        c.funcs['batalkan_pertemuan'](7, 9, 'Tidak berlangsung')
    assert c.state['status'] == 'perlu_laporan'


def test_tutor_lain_tidak_boleh_membatalkan():
    c = ctx(owned=False)
    with pytest.raises(ValueError, match='bukan milikmu'):
        c.funcs['batalkan_pertemuan'](8, 9, 'Tidak berlangsung')


def test_pertemuan_hari_jadwal_dibuat_sekali():
    c = ctx()
    first = c.funcs['buka_pertemuan'](7, 7)
    assert first['dibuat'] is True and first['session_id'] == 9
    assert c.state['commits'] == 1
    assert any('insert into class_sessions' in q for q, _ in c.state['sql'])


def test_sesi_hari_ini_sudah_ada_digunakan_lagi():
    c = ctx(existing=True)
    result = c.funcs['buka_pertemuan'](7, 7)
    assert result['dibuat'] is False
    assert not any('insert into class_sessions' in q for q, _ in c.state['sql'])


def test_jadwal_hari_lain_tidak_boleh_buat_sesi():
    c = ctx(day_label='senin')
    with pytest.raises(ValueError, match='bukan hari jadwal'):
        c.funcs['buka_pertemuan'](7, 7)
    assert not any('insert into class_sessions' in q for q, _ in c.state['sql'])


def test_jadwal_yang_bukan_milik_tutor_ditolak():
    c = ctx(owned=False)
    with pytest.raises(ValueError, match='bukan milikmu'):
        c.funcs['buka_pertemuan'](8, 7)


def test_roster_query_menggunakan_tanggal_aktivasi_dan_kehadiran_lama():
    source = REPO.read_text(encoding='utf-8')
    assert source.count('COALESCE(e.processed_at::date, e.created_at::date) <= %s::date') >= 3
    assert 'SELECT DISTINCT st.user_id AS student_id' in source
    assert 'a.session_id IS NOT NULL' in source
    assert "in (\"batal\", \"selesai\")" in source
    assert "cs.status NOT IN ('batal', 'selesai')" in source


def test_schema_mempertahankan_nilai_legacy():
    schema = (ROOT / 'sql/schema.sql').read_text(encoding='utf-8')
    assert "'terlaksana', 'batal', 'perlu_laporan', 'selesai'" in schema
    assert "DEFAULT 'perlu_laporan'" in schema
    assert 'selesai_at' in schema and 'alasan_batal' in schema


def test_migrasi_perlu_konfirmasi_database_dan_tidak_update_legacy():
    content = MIGRATION.read_text(encoding='utf-8')
    assert "input(f'Ketik nama database" in content
    assert 'autocommit=True' in content and content.count('with conn.transaction():') >= 2
    assert "ALTER TYPE session_status ADD VALUE IF NOT EXISTS" in content
    assert 'UPDATE class_sessions SET status' not in content


def test_tampilan_memiliki_nama_kelas_dan_aksi_jelas():
    source = UI.read_text(encoding='utf-8')
    assert 'Kelola pertemuan hari ini (sesuai jadwal)' in source
    assert 'Isi / Koreksi Absensi Siswa' in source
    assert 'Konfirmasi pertemuan selesai' in source
    assert 'Laporkan pertemuan dibatalkan' in source
    assert 'nama_program' in source and 'nama_ruang' in source


@pytest.mark.parametrize('status,label', [
    ('perlu_laporan','Perlu absensi'), ('selesai','Selesai'),
    ('batal','Dibatalkan'),('terlaksana','Catatan lama')
])
def test_label_status_di_ui_tutor(status,label):
    ns = _functions(UI, ('_label_pertemuan',))
    assert label in ns['_label_pertemuan'](status)


def test_proyeksi_tidak_menyebut_draf_selesai():
    source = (ROOT/'app/ui/proyeksi_pertemuan.py').read_text(encoding='utf-8')
    assert 'Perlu absensi / laporan Tutor' in source
    assert 'Selesai (dikonfirmasi Tutor)' in source


def test_filter_materi_siswa_menampilkan_historis_dan_selesai():
    source = (ROOT/'app/repositories/student_repo.py').read_text(encoding='utf-8')
    assert "cs.status IN ('terlaksana', 'selesai')" in source


def test_laporan_siswa_tidak_menyamakan_draf_dengan_selesai():
    source = (ROOT/'app/ui/menu_siswa_academic.py').read_text(encoding='utf-8')
    assert "'perlu_laporan': 'Menunggu laporan Tutor'" in source
    assert "'selesai': 'Selesai'" in source
