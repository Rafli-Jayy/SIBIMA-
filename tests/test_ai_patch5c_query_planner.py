"""Patch 5C offline scope/security/SQL contract tests, with no live DB."""
from contextlib import contextmanager
from decimal import Decimal
import re
import sys
import types

import pytest

from app import session
from app.services.ai_query_planner import (TOOL_ROLE, validate_plan, tool_schema)
from app.services.ai_tool_controller import (AIToolController, PATCH5C_ROLE_TO_TOOLS)
from app.repositories.ai_analytics_repo import (execute_analytics, _INVOICE_TOTAL,
    _INVOICE_GROUP_LIST, _PROGRAM_LIST, _STUDENT_LIST, _TUTOR_ATTENDANCE_CTE,
    _ATTENDANCE_TOTAL, _ENROLLMENT_COUNT)
from app.repositories.ai_read_repo import AIReadRepository


@pytest.fixture(autouse=True)
def session_reset():
    old = session.get_user()
    session.logout()
    yield
    session.set_user(old)


class RecordingCursor:
    def __init__(self, responses=None, pages=None, current_role="admin"):
        self.queries = []
        self.responses = list(responses or [])
        self.pages = list(pages or [])
        self.current_role = current_role
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None):
        if params is None: params = ()
        self.queries.append((sql, params))
        # Every parameter value must have one associated fixed SQL placeholder.
        assert sql.count("%s") == len(params), (sql.count("%s"), len(params))
        assert not re.search(r"\b(?:INSERT|UPDATE|DELETE|ALTER|DROP|TRUNCATE)\b", sql, re.I)
    def fetchone(self):
        if self.responses: return self.responses.pop(0)
        return {}
    def fetchmany(self, cap):
        assert cap == 20
        return self.pages.pop(0) if self.pages else []


class Db:
    def __init__(self, cur): self.cur = cur
    def __enter__(self): return self
    def __exit__(self, *a): return False
    @contextmanager
    def transaction(self): yield
    def cursor(self, **kwargs): return self.cur


class Pool:
    def __init__(self, cur): self.cur=cur
    def connection(self, timeout):
        assert timeout == 5
        return Db(self.cur)


def mock_psycopg(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", types.ModuleType("psycopg"))
    m = types.ModuleType("psycopg.rows")
    m.dict_row = object()
    monkeypatch.setitem(sys.modules, "psycopg.rows", m)


def test_all_seven_declared_only_to_correct_role():
    assert len(TOOL_ROLE) == 7
    for role in ("admin", "tutor", "siswa"):
        session.set_user({"id": 42, "role": role, "status": "aktif"})
        c = AIToolController(role, repo=object(), rag_tool=False)
        names = {t["name"] for t in c.declarations()}
        assert set(PATCH5C_ROLE_TO_TOOLS[role]) <= names
        assert not ({n for n,r in TOOL_ROLE.items() if r != role} & names)
        for name in PATCH5C_ROLE_TO_TOOLS[role]:
            assert tool_schema(name)["parameters"]["type"] == "object"


@pytest.mark.parametrize('name,role,args', [
    ("admin_receivables_summary", "siswa", {}),
    ("tutor_program_summary", "admin", {}),
    ("student_progress_summary", "tutor", {}),
])
def test_cross_role_denied(name, role, args):
    with pytest.raises(PermissionError): validate_plan(name, args, role)


@pytest.mark.parametrize('name,args', [
    ("admin_receivables_summary", {"raw_sql":"SELECT * FROM users"}),
    ("admin_receivables_summary", {"user_id":999}),
    ("admin_receivables_summary", {"table":"payments"}),
    ("admin_enrollment_overview", {"program_id": True}),
    ("admin_enrollment_overview", {"program_id": -5}),
    ("admin_receivables_summary", {"kelompok":"; DROP TABLE invoices"}),
    ("admin_receivables_summary", {"keterlambatan":"semua OR TRUE"}),
    ("admin_enrollment_overview", {"status":"lunas"}),
    ("admin_enrollment_overview", {"tanggal_dari":"2026-02-30"}),
    ("admin_enrollment_overview", {"tanggal_dari":"2026-11-30", "tanggal_sampai":"2026-11-01"}),
    ("admin_receivables_summary", {"periode_dari":"2026-11-02"}),
    ("admin_receivables_summary", {"periode_sampai":"2026-1-01"}),
])
def test_invalid_filter_denied(name,args):
    with pytest.raises(ValueError): validate_plan(name, args, TOOL_ROLE[name])


def test_default_arguments_and_metadata():
    assert validate_plan("admin_receivables_summary", {}, "admin") == {"keterlambatan":"semua", "kelompok":"total"}
    assert validate_plan("admin_enrollment_overview", {"status":"menunggu_pembayaran"}, "admin") == {"status":"menunggu_pembayaran"}


def test_admin_receivables_not_summed_from_first_20():
    # fake DB says there are 27 invoices, but only 20 grouped rows shown.
    cur=RecordingCursor(responses=[{"jumlah_invoice": 27,"nominal_bruto_belum_lunas":Decimal('810000.00')},
                                   {"kelompok_total":22}],
                        pages=[[{"program_id":i,"nominal_bruto_belum_lunas":Decimal('30000.00')} for i in range(20)]])
    result=execute_analytics(cur,1,'admin','admin_receivables_summary',{"kelompok":"program"})
    assert result["total_hasil"] == 27
    assert result["data"]["nominal_bruto_belum_lunas"] == "810000.00"
    assert result["terpotong"] is True
    assert result["jumlah_ditampilkan"] == 20
    assert result["total_kelompok"] == 22
    assert all("SUM(" in q[0] for q in (cur.queries[0],cur.queries[2]))


def test_enrollment_counts_are_separate_from_users():
    cur=RecordingCursor(responses=[{"akun_siswa_aktif_global":10,"jumlah_enrollment":14,
                                   "siswa_unik":9,"jumlah_program":3}],
                        pages=[[{"program_id":1,"jumlah_enrollment":8}]])
    result=execute_analytics(cur,1,'admin','admin_enrollment_overview',{})
    assert result["data"]["akun_siswa_aktif_global"] == 10
    assert result["data"]["jumlah_enrollment"] == 14
    assert result["data"]["siswa_unik"] == 9
    assert result["total_hasil"] == 14
    assert result["terpotong"]  # fixture returns one group of three


def test_attendance_no_records_is_not_zero_percent():
    cur=RecordingCursor(responses=[{"jumlah_sesi_selesai":7,"jumlah_catatan":0,"hadir":0,
                                   "izin":0,"sakit":0,"alpa":0,"persentase_hadir_tercatat":None}])
    result=execute_analytics(cur,1,'admin','admin_attendance_summary',{})
    assert result["data"]["persentase_hadir_tercatat"] is None
    assert result["data"]["jumlah_sesi_selesai"] == 7
    assert result["terpotong"] is False
    assert "NULLIF" in cur.queries[0][0]


def test_tutor_scope_uses_principal_from_session_not_model():
    cur=RecordingCursor(responses=[{"jumlah_sesi_selesai":3,"jumlah_catatan":4,"hadir":3,
                                   "izin":1,"sakit":0,"alpa":0,"persentase_hadir_tercatat":Decimal('75.00')}])
    res=execute_analytics(cur,123,'tutor','tutor_attendance_statistics',{'program_id':9})
    assert res['data']['persentase_hadir_tercatat']=='75.00'
    assert cur.queries[0][1][-1] == 123
    assert 's.tutor_id=f.tutor_id' in cur.queries[0][0]


def test_student_access_bound_to_latest_enrollment_and_lock():
    cur=RecordingCursor(responses=[{'jumlah_program':1}], pages=[[{'program_id':11,'jumlah_nilai':2,
                                                              'rata_rata_nilai_aritmetika':Decimal('80.25')} ]])
    res=execute_analytics(cur,84,'siswa','student_progress_summary',{})
    assert res['data']['per_program'][0]['rata_rata_nilai_aritmetika']=='80.25'
    assert 'MAX(e_terakhir.id)' in cur.queries[0][0]
    assert 'i_akses.status = \'belum_dibayar\'' in cur.queries[0][0]
    assert cur.queries[0][1] == (84,None)


def test_repository_stays_readonly_and_checks_principal(monkeypatch):
    mock_psycopg(monkeypatch)
    cur=RecordingCursor(responses=[{'role':'admin','status':'aktif'},
                                   {'jumlah_invoice':27,'nominal_bruto_belum_lunas':Decimal('810000.00')}])
    res=AIReadRepository(Pool(cur)).execute(71,'admin','admin_receivables_summary',{})
    assert res['total_hasil']==27
    assert [q[0] for q in cur.queries[:2]]==['SET TRANSACTION READ ONLY',"SET LOCAL statement_timeout = '5000ms'"]
    assert cur.queries[2][1]==(71,)
    assert 'SUM(' in cur.queries[3][0]


def test_database_inactive_role_fails_without_analytics_query(monkeypatch):
    mock_psycopg(monkeypatch)
    cur=RecordingCursor(responses=[{'role':'admin','status':'ditolak'}])
    with pytest.raises(PermissionError):
        AIReadRepository(Pool(cur)).execute(71,'admin','admin_receivables_summary',{})
    assert len(cur.queries)==3


def test_controller_denies_invalid_plan_before_accessing_repo():
    class FakeRepo:
        calls = []
        def execute(self, *args): self.calls.append(args);return {}
    session.set_user({'id':33,'role':'siswa','status':'aktif'})
    repo=FakeRepo()
    ctrl=AIToolController('siswa',repo=repo,rag_tool=False)
    with pytest.raises(PermissionError): ctrl.execute('admin_enrollment_overview',{})
    with pytest.raises(ValueError): ctrl.execute('student_progress_summary',{'student_id':34})
    with pytest.raises(ValueError): ctrl.execute('student_progress_summary',{'program_id':'13 OR TRUE'})
    assert not repo.calls


def test_sql_fixed_metadata_and_no_user_supplied_identifiers():
    for sql in (_INVOICE_TOTAL, _INVOICE_GROUP_LIST['program'],
                _PROGRAM_LIST, _STUDENT_LIST, _ENROLLMENT_COUNT,
                _TUTOR_ATTENDANCE_CTE+_ATTENDANCE_TOTAL):
        assert 'SELECT' in sql.upper()
        assert 'SET TRANSACTION' not in sql.upper()
        assert all(term not in sql.upper() for term in ('DROP TABLE','INSERT INTO','DELETE FROM','UPDATE USERS'))


@pytest.mark.parametrize('name,role', list(TOOL_ROLE.items()))
def test_all_seven_queries_have_matched_placeholders(name,role):
    cur=RecordingCursor()
    result=execute_analytics(cur,7,role,name,{})
    assert result['sumber'].startswith('PostgreSQL')
    assert result['timezone']=='Asia/Jakarta'
    assert len(cur.queries)>=1


def test_metadata_does_not_mark_full_aggregation_as_truncated():
    cur=RecordingCursor(responses=[{'jumlah_invoice':100,'nominal_bruto_belum_lunas':Decimal('1234.00')}])
    result=execute_analytics(cur,7,'admin','admin_receivables_summary',{})
    assert result['total_hasil']==100
    assert result['jumlah_ditampilkan']==1
    assert result['terpotong'] is False


def test_repo_rejects_cross_role_even_when_called_directly():
    with pytest.raises(PermissionError):
        AIReadRepository(object()).execute(1,'siswa','admin_receivables_summary',{})
