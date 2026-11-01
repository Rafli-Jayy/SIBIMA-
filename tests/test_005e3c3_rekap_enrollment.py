"""C3 regression: runtime SQLite untuk query siswa + pemeriksaan SQL antar role.

SQLite dipakai sebagai data tiruan untuk sebagian query yang kompatibel; ini
BUKAN bukti bahwa migrasi PostgreSQL atau service lokal telah diuji langsung.
"""
import ast
import importlib.util
import re
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'app/repositories'
ACADEMIC = (SRC / 'academic_repo.py').read_text(encoding='utf-8')
STUDENT = (SRC / 'student_repo.py').read_text(encoding='utf-8')
ADMIN = (SRC / 'report_repo.py').read_text(encoding='utf-8')
VIEW = (ROOT / 'sql/migrations/20261101_patch_005e3c3_rekap_kehadiran.sql').read_text(encoding='utf-8')
SCHEMA = (ROOT / 'sql/schema.sql').read_text(encoding='utf-8')


def body(source, func, following=None):
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == func)
    return ast.get_source_segment(source, node)


def test_view_menambah_identitas_enrollment_tanpa_menghapus_view():
    assert 'CREATE OR REPLACE VIEW v_rekap_kehadiran AS' in VIEW
    assert 'e.id AS enrollment_id' in VIEW
    assert 'e.status::text AS status_enrollment' in VIEW
    assert 'e.created_at::date AS tanggal_pendaftaran' in VIEW
    assert "cs.status = 'selesai'" in VIEW
    assert 'a.enrollment_id = e.id' in VIEW
    assert "e.status IN ('aktif', 'selesai', 'batal')" in VIEW
    assert not re.search(r'\b(DROP|DELETE|TRUNCATE|UPDATE)\b', VIEW, flags=re.I)
    assert 'CREATE VIEW v_rekap_kehadiran AS' in SCHEMA
    assert 'e.id AS enrollment_id' in SCHEMA


@pytest.mark.parametrize('query', [
    body(ACADEMIC, 'daftar_siswa_kelas'),
    body(ACADEMIC, 'detail_siswa_kelas'),
    body(ACADEMIC, 'rekap_absensi_tutor'),
])
def test_rekap_tutor_terikat_enrollment_dan_sesi_selesai(query):
    assert 'enrollment_id' in query
    assert "cs.status = 'selesai'" in query
    assert 'a.student_id = e.student_id' in query or 'at.student_id = e.student_id' in query
    assert 'NULLIF(' in query


@pytest.mark.parametrize('query', [
    body(STUDENT, 'daftar_pertemuan_siswa'),
    body(STUDENT, 'rekap_absensi'),
    body(STUDENT, 'daftar_absensi'),
])
def test_pembacaan_siswa_terikat_pendaftaran_dan_akses_h3(query):
    assert 'enrollment_id' in query
    assert 'NOT {AKSES_TERKUNCI_SQL}' in query
    assert '{ENROLLMENT_TERAKHIR_TERSEDIA_SQL}' in query


def test_roster_tutor_pilih_satu_pendaftaran_siswa_per_sesi():
    sql = body(ACADEMIC, 'daftar_absensi_sesi')
    assert 'LIMIT 1' in sql
    assert 'a.enrollment_id = e.id' in sql
    assert 'a.session_id IS NOT NULL' in sql
    assert 'a.enrollment_id = selected.enrollment_id' in sql
    assert 'legacy.enrollment_id IS NULL' in sql
    assert 'riwayat_lama_belum_terhubung' in sql


def test_laporan_admin_berisi_identitas_dan_arsip_null():
    assert 'r.enrollment_id, r.status_enrollment, r.tanggal_pendaftaran' in ADMIN
    assert 'WHERE a.enrollment_id IS NULL' in body(ADMIN, 'absensi_belum_terhubung')
    definitions = (ROOT / 'app/services/report_service.py').read_text(encoding='utf-8')
    assert '"absensi_arsip"' in definitions
    assert 'report_repo.absensi_belum_terhubung' in definitions
    assert '("enrollment_id", "ID pendaftaran")' in definitions
    assert '"Rekap Kehadiran per Pendaftaran"' in definitions


def test_cli_menyatakan_konteks_enrollment_dan_sesi_selesai():
    siswa = (ROOT / 'app/ui/menu_siswa_academic.py').read_text(encoding='utf-8')
    tutor = (ROOT / 'app/ui/menu_tutor_academic.py').read_text(encoding='utf-8')
    assert 'Rekap hanya menghitung sesi selesai' in siswa
    assert "r.get('enrollment_id')" in siswa
    assert '"Sesi selesai"' in tutor
    assert '("enrollment_id", "Pendaftaran")' in tutor


def test_keselamatan_migrasi_tanpa_backfill():
    sql = VIEW.lower()
    assert 'update attendances' not in sql
    assert 'delete from attendances' not in sql
    assert 'drop view' not in sql
    migrator = (ROOT / 'tools/apply_migration_005e3c3.py').read_text(encoding='utf-8')
    assert '--check' in migrator and '--apply' in migrator
    assert 'with conn.transaction()' in migrator
    assert "state['database'] != expected" in migrator
    assert 'confirm != expected' in migrator


class SqliteCursor:
    def __init__(self, conn):
        self.cursor = conn.cursor()
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        self.cursor.close()
    def execute(self, query, params=()):
        # Terjemahan sintaks tipe PostgreSQL saja, tanpa mengubah logika join.
        q = re.sub(r'([\w]+\.[\w]+)::date', r'date(\1)', query)
        q = re.sub(r'::(?:integer|int|text)\b', '', q)
        q = q.replace('CURRENT_DATE - 3', "date('now', '-3 days')")
        q = q.replace('%s', '?')
        self.cursor.execute(q, params)
    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]


class SqliteConnection:
    def __init__(self, sqlite):
        self.sqlite = sqlite
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        pass
    def cursor(self, **_):
        return SqliteCursor(self.sqlite)


def setup_db():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE students(user_id INTEGER);
        CREATE TABLE programs(id INTEGER PRIMARY KEY, nama TEXT);
        CREATE TABLE enrollments(id INTEGER PRIMARY KEY, student_id INTEGER, program_id INTEGER,
            status TEXT, created_at TEXT);
        CREATE TABLE schedules(id INTEGER PRIMARY KEY, program_id INTEGER);
        CREATE TABLE class_sessions(id INTEGER PRIMARY KEY, schedule_id INTEGER, tanggal TEXT,
            pertemuan_ke INTEGER, topik TEXT, status TEXT);
        CREATE TABLE attendances(session_id INTEGER, student_id INTEGER, enrollment_id INTEGER,
            status TEXT, keterangan TEXT);
        CREATE TABLE invoices(enrollment_id INTEGER, status TEXT, jumlah INTEGER, jatuh_tempo TEXT);
        INSERT INTO students VALUES (41);
        INSERT INTO programs VALUES (11, 'Matematika');
        INSERT INTO enrollments VALUES (10, 41, 11, 'batal', '2026-01-01');
        INSERT INTO enrollments VALUES (27, 41, 11, 'aktif', '2026-10-01');
        INSERT INTO schedules VALUES (55, 11);
        INSERT INTO class_sessions VALUES (1,55,'2026-02-01',1,'Lama','selesai');
        INSERT INTO class_sessions VALUES (2,55,'2026-10-10',2,'Dalam proses','perlu_laporan');
        INSERT INTO class_sessions VALUES (3,55,'2026-10-17',3,'Aktif','selesai');
        INSERT INTO class_sessions VALUES (4,55,'2026-10-24',4,'Batal','batal');
        INSERT INTO class_sessions VALUES (5,55,'2026-10-03',5,'Warisan','terlaksana');
        INSERT INTO class_sessions VALUES (6,55,'2026-10-31',6,'Belum diabsen','selesai');
        INSERT INTO attendances VALUES (1,41,10,'H','riwayat lama');
        INSERT INTO attendances VALUES (2,41,27,'I','belum diselesaikan');
        INSERT INTO attendances VALUES (3,41,27,'H','aktif');
        INSERT INTO attendances VALUES (4,41,27,'A','invalid batal');
        INSERT INTO attendances VALUES (5,41,NULL,'A','legacy ambigu');
    ''')
    return db


def compiled_student(name, db):
    src = ast.parse(STUDENT)
    node = next(n for n in src.body if isinstance(n, ast.FunctionDef) and n.name == name)
    cl = (SRC / 'class_access_sql.py').read_text(encoding='utf-8')
    globals_ns = {'pool': SimpleNamespace(connection=lambda: SqliteConnection(db)),
                  'dict_row': object(),
                  '_valid_id': lambda v, k: v if type(v) is int and v > 0 else (_ for _ in ()).throw(ValueError(k))}
    exec(compile(cl, str(SRC / 'class_access_sql.py'), 'exec'), globals_ns)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SRC/'student_repo.py'), 'exec'), globals_ns)
    return globals_ns[name]


def test_sql_aktual_rekap_hanya_pendaftaran_baru_dan_sesi_selesai():
    db = setup_db()
    rows = compiled_student('rekap_absensi', db)(41, 11)
    assert len(rows) == 1
    row = rows[0]
    assert row['enrollment_id'] == 27
    assert row['total_pertemuan'] == 1
    assert (row['hadir'],row['izin'],row['sakit'],row['alpa']) == (1,0,0,0)
    assert row['persen_hadir'] == 100.0
    db.close()


def test_sql_aktual_riwayat_siswa_tak_mencampur_arsip_null_dan_batal():
    db = setup_db()
    rows = compiled_student('daftar_absensi', db)(41, 11)
    assert [(r['tanggal'],r['status_pertemuan']) for r in rows] == [
        ('2026-10-17','selesai'), ('2026-10-10','perlu_laporan')]
    assert {r['enrollment_id'] for r in rows} == {27}
    db.close()


def test_sql_aktual_pertemuan_tidak_mengambil_absensi_lama():
    db = setup_db()
    # Database minimal untuk query ini membutuhkan rooms & users; bentuk relasi lengkap disiapkan.
    db.executescript('''
        CREATE TABLE rooms(id INTEGER PRIMARY KEY, nama TEXT);
        CREATE TABLE users(id INTEGER PRIMARY KEY, nama_lengkap TEXT);
        ALTER TABLE schedules ADD COLUMN room_id INTEGER;
        ALTER TABLE schedules ADD COLUMN tutor_id INTEGER;
        ALTER TABLE schedules ADD COLUMN hari TEXT;
        ALTER TABLE schedules ADD COLUMN jam_mulai TEXT;
        ALTER TABLE schedules ADD COLUMN jam_selesai TEXT;
        UPDATE schedules SET room_id=9, tutor_id=7, hari='sabtu',jam_mulai='15:00',jam_selesai='16:00';
        INSERT INTO rooms VALUES (9, 'Ruang A');
        INSERT INTO users VALUES (7, 'Tutor A');
        ALTER TABLE class_sessions ADD COLUMN ringkasan TEXT;
    ''')
    rows = compiled_student('daftar_pertemuan_siswa',db)(41,11)
    by_id = {r['session_id']:r for r in rows}
    assert 1 not in by_id  # sebelum pendaftaran baru
    assert by_id[3]['status_absensi'] == 'H'
    assert by_id[5]['status_absensi'] is None  # legacy NULL tidak dipakai
    db.close()


def test_hak_akses_siswa_tetap_digunakan():
    db = setup_db()
    with pytest.raises(ValueError):
        compiled_student('rekap_absensi', db)(0)
    with pytest.raises(ValueError):
        compiled_student('daftar_absensi', db)(41, limit=0)
    db.close()


def test_view_migration_columns_backward_compatible():
    spec = importlib.util.spec_from_file_location('migrator_c3', ROOT/'tools/apply_migration_005e3c3.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.LEGACY_COLUMNS == ('student_id','program_id','total_pertemuan','hadir',
                                     'izin','sakit','alpa','persen_hadir')
    assert module.ADDED_COLUMNS == ('enrollment_id','status_enrollment','tanggal_pendaftaran')


def test_pendaftaran_terakhir_batal_tidak_membuka_riwayat_lama():
    db = setup_db()
    db.execute("UPDATE enrollments SET status = 'batal' WHERE id = 27")
    assert compiled_student('rekap_absensi', db)(41,11) == []
    assert compiled_student('daftar_absensi', db)(41,11) == []
    db.close()


def test_pendaftaran_tanpa_absensi_tetap_bernilai_nol_bukan_alpa():
    db = setup_db()
    db.execute('DELETE FROM attendances WHERE enrollment_id = 27')
    rows = compiled_student('rekap_absensi', db)(41,11)
    assert len(rows) == 1
    assert rows[0]['total_pertemuan'] == 0
    assert rows[0]['alpa'] == 0
    assert rows[0]['persen_hadir'] is None
    db.close()


def test_h3_kelas_terkunci_tidak_membuka_rekap_akademik():
    db = setup_db()
    db.execute("INSERT INTO invoices VALUES (27,'belum_dibayar',200000,'2025-01-01')")
    assert compiled_student('rekap_absensi', db)(41,11) == []
    assert compiled_student('daftar_absensi', db)(41,11) == []
    db.close()


class InspectCursor:
    def __init__(self, *, columns=None, attendance_col=True, view_sql=None):
        self.columns = columns or (
            'student_id','program_id','total_pertemuan','hadir','izin','sakit','alpa','persen_hadir')
        self.attendance_col = attendance_col
        self.view_sql = view_sql or 'SELECT a.student_id FROM attendances a JOIN class_sessions cs ON cs.id = a.session_id GROUP BY a.student_id'
        self.queries=[]
        self.one=None
        self.many=[]
    def execute(self, sql, params=()):
        q = ' '.join(sql.lower().split())
        self.queries.append(q)
        self.one=None
        self.many=[]
        if 'select current_database(), current_user' in q:
            self.one=('bimbel_db','bimbel_user')
        elif "table_name = 'attendances'" in q:
            self.one=('enrollment_id',) if self.attendance_col else None
        elif "table_name = 'v_rekap_kehadiran'" in q:
            self.many=[(v,) for v in self.columns]
        elif 'pg_get_userbyid' in q:
            self.one=('bimbel_user',self.view_sql)
        elif 'count(*) from attendances where enrollment_id is null' in q:
            self.one=(1,)
        else:
            raise AssertionError('SQL tak diharapkan: ' + q[:140])
    def fetchone(self):
        return self.one
    def fetchall(self):
        return self.many


def load_migrator():
    spec=importlib.util.spec_from_file_location('migrator_c3',ROOT/'tools/apply_migration_005e3c3.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_migrasi_membaca_tanpa_mengubah_database():
    mod=load_migrator()
    cur=InspectCursor()
    state=mod._inspection(cur)
    assert state['database']=='bimbel_db'
    assert state['installed'] is False
    assert state['historical']==1
    assert all(not x.startswith(('update ','alter ','drop ','create ','delete ')) for x in cur.queries)


def test_check_migrasi_menolak_jika_c2_belum_terpasang():
    mod=load_migrator()
    with pytest.raises(ValueError,match='005E3-C2'):
        mod._inspection(InspectCursor(attendance_col=False))


def test_check_migrasi_menolak_view_modifikasi_tak_dikenal():
    mod=load_migrator()
    with pytest.raises(ValueError,match='baseline'):
        mod._inspection(InspectCursor(columns=('student_id','program_id','unexpected')))


def test_check_migrasi_mengenali_view_sudah_terpasang():
    mod=load_migrator()
    cols=mod.LEGACY_COLUMNS+mod.ADDED_COLUMNS
    state=mod._inspection(InspectCursor(columns=cols,view_sql="SELECT e.id AS enrollment_id, e.status::text AS status_enrollment FROM attendances a JOIN class_sessions cs ON cs.id = a.session_id WHERE a.enrollment_id = e.id AND cs.status = 'selesai'"))
    assert state['installed'] is True
