"""C2 regression with a transactional fake; PostgreSQL integration is not claimed."""
import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / 'app/repositories/academic_repo.py'
SCHEMA = ROOT / 'sql/schema.sql'
MIGRATOR = ROOT / 'tools/apply_migration_005e3c2.py'


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.rows = []
        self.pos = 0

    def execute(self, sql, params=()):
        q = ' '.join(sql.lower().split())
        self.db['sql'].append((q, params))
        self.rows, self.pos = [], 0
        db = self.db
        if 'select cs.id, cs.tanggal, cs.status::text' in q and 'for update of cs' in q:
            if db['owned']:
                self.rows = [{'id': 9, 'tanggal': date(2026, 11, 1), 'status_pertemuan': db['status'], 'program_id': 11}]
        elif 'select e.id as enrollment_id from enrollments e' in q:
            self.rows = [{'enrollment_id': n} for n in db['candidates'].get(params[0], ())]
        elif 'select exists ( select 1 from enrollments other' in q:
            self.rows = [{'ambigu': db['same_day'].get(params[0], False)}]
        elif 'select a.enrollment_id from attendances a' in q:
            key = (params[0], params[1])
            if key in db['rows']:
                self.rows = [{'enrollment_id': db['rows'][key]}]
        elif 'insert into attendances' in q:
            sid, student, eid, *_ = params
            key = (sid, student)
            if key in db['rows'] and db['rows'][key] != eid:
                self.rows = []
            else:
                db['staged'][key] = eid
                self.rows = [{'enrollment_id': eid}]
        elif 'insert into activity_logs' in q:
            pass
        else:
            raise AssertionError('Unhandled SQL: ' + q[:180])

    def fetchone(self):
        result = self.rows[self.pos] if self.pos < len(self.rows) else None
        self.pos += 1
        return result

    def fetchall(self):
        out = self.rows[self.pos:]
        self.pos = len(self.rows)
        return out

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, db):
        self.db = db
    def cursor(self, **kwargs):
        return FakeCursor(self.db)
    def commit(self):
        self.db['rows'].update(self.db['staged'])
        self.db['staged'].clear()
        self.db['commits'] += 1
    def __enter__(self):
        return self
    def __exit__(self, typ, exc, tb):
        if typ is not None:
            self.db['staged'].clear()
        return False


def funcs(**overrides):
    db = {'rows': {}, 'staged': {}, 'sql': [], 'candidates': {41:(101,), 42:(102,)},
          'same_day': {}, 'owned':True, 'status':'perlu_laporan', 'commits':0}
    db.update(overrides)
    source = ast.parse(REPO.read_text(encoding='utf-8'))
    names = {'_enrollment_sah_untuk_absensi', 'simpan_absensi'}
    nodes = [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes} == names
    ns={'pool':SimpleNamespace(connection=lambda: FakeConn(db)),'dict_row':object()}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(REPO),'exec'),ns)
    return SimpleNamespace(db=db, save=ns['simpan_absensi'])


def records(*student_ids):
    return [{'student_id': x, 'status':'H', 'keterangan':''} for x in student_ids]


def test_new_attendance_binds_enrollment():
    c=funcs()
    assert c.save(7, 9, records(41))==1
    assert c.db['rows']=={(9,41):101}
    assert c.db['commits']==1


def test_updates_only_same_enrollment():
    c=funcs(rows={(9,41):101})
    assert c.save(7,9,records(41))==1
    assert c.db['rows'][(9,41)]==101
    sql=' '.join(q for q,_ in c.db['sql'])
    assert 'where attendances.enrollment_id = excluded.enrollment_id' in sql


def test_preserve_legacy_null_not_reassigned():
    c=funcs(rows={(9,41):None})
    with pytest.raises(ValueError,match='belum memiliki enrollment_id'):
        c.save(7,9,records(41))
    assert c.db['rows'][(9,41)] is None and c.db['commits']==0


def test_different_enrollment_never_overwritten():
    c=funcs(rows={(9,41):98})
    with pytest.raises(ValueError,match='pendaftaran berbeda'):
        c.save(7,9,records(41))
    assert c.db['rows'][(9,41)]==98


@pytest.mark.parametrize('candidates', [(), (101,110)])
def test_no_exact_one_enrollment_rejected(candidates):
    c=funcs(candidates={41:candidates})
    with pytest.raises(ValueError,match='tepat satu enrollment'):
        c.save(7,9,records(41))
    assert not c.db['rows']


def test_same_day_reenrollment_blocked():
    c=funcs(same_day={41:True})
    with pytest.raises(ValueError,match='hari sesi yang sama'):
        c.save(7,9,records(41))
    assert not c.db['rows']


@pytest.mark.parametrize('status',['batal','selesai'])
def test_closed_session_rejected(status):
    c=funcs(status=status)
    with pytest.raises(ValueError,match='dibatalkan atau selesai'):
        c.save(7,9,records(41))
    assert not c.db['rows']


def test_wrong_tutor_rejected():
    c=funcs(owned=False)
    with pytest.raises(ValueError,match='bukan milikmu'):
        c.save(7,9,records(41))


def test_duplicate_student_rejected_and_batch_rolls_back():
    c=funcs()
    with pytest.raises(ValueError,match='lebih dari sekali'):
        c.save(7,9,records(41,41))
    assert c.db['rows']=={} and c.db['commits']==0


def test_second_student_legacy_rolls_back_first_new():
    c=funcs(rows={(9,42):None})
    with pytest.raises(ValueError,match='belum memiliki enrollment_id'):
        c.save(7,9,records(41,42))
    assert c.db['rows']=={(9,42):None} and c.db['staged']=={}


def test_blank_batch_rejected():
    c=funcs()
    with pytest.raises(ValueError,match='Tidak ada data'):
        c.save(7,9,[])


def test_schema_has_nullable_fk_and_preserves_pk():
    s=SCHEMA.read_text(encoding='utf-8')
    assert 'enrollment_id INT' in s and 'fk_attendances_enrollment' in s
    assert 'REFERENCES enrollments(id)' in s
    assert 'PRIMARY KEY (session_id, student_id)' in s
    assert 'idx_attend_enrollment' in s


def test_migrator_requires_explicit_database_confirmation():
    s=MIGRATOR.read_text(encoding='utf-8')
    assert '--check' in s and '--apply' in s
    assert 'input(f"Untuk menerapkan migrasi, ketik nama database' in s
    assert 'ALTER TABLE attendances ADD COLUMN enrollment_id' in s
    assert 'UPDATE attendances' not in s
    assert 'with conn.transaction()' in s


def test_api_does_not_trust_client_enrollment_id():
    c=funcs()
    supplied=[{'student_id':41,'enrollment_id':999,'status':'H'}]
    c.save(7,9,supplied)
    assert c.db['rows'][(9,41)]==101


def test_legacy_record_still_visible_in_database_after_new_batch():
    c=funcs(rows={(9,42):None})
    c.save(7,9,records(41))
    assert c.db['rows']=={(9,42):None,(9,41):101}


def test_query_scoped_to_program_session_and_tutor():
    c=funcs()
    c.save(7,9,records(41))
    q='\n'.join(a for a,_ in c.db['sql'])
    assert 'where cs.id = %s and s.tutor_id = %s' in q
    assert "e.program_id = %s and e.status = 'aktif'" in q
    assert 'e.created_at::date' in q and 'for update of e' in q
