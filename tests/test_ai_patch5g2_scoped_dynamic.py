"""Regression and access-control tests for scoped dynamic analytics Patch 5G.2."""
from contextlib import contextmanager
from decimal import Decimal
import re
import sys
import types

import pytest

from app import session
from app.repositories.ai_dynamic_repo import compile_query, execute_dynamic
from app.repositories.ai_read_repo import AIReadRepository
from app.services.ai_dynamic_plan import (
    ROLE_DYNAMIC_NAMES, role_dynamic_schema, validate_role_dynamic_plan,
)
from app.services.ai_tool_controller import AIToolController
from app.services.hybrid_evidence import HybridEvidence


def plan(domain, metric, groups=(), filters=None):
    return {"domain": domain, "metrik": metric, "kelompok": list(groups), "filter": filters or {}}


@pytest.fixture(autouse=True)
def cleanup_session():
    old = session.get_user()
    session.logout()
    yield
    session.set_user(old)


@pytest.mark.parametrize("role, permitted", [
    ("tutor", {"pendaftaran", "jadwal", "kehadiran"}),
    ("siswa", {"pendaftaran", "tagihan", "pembayaran", "nilai", "kehadiran"}),
])
def test_role_schemas_only_expose_permitted_domains(role, permitted):
    schema = role_dynamic_schema(role)
    assert schema["name"] == ROLE_DYNAMIC_NAMES[role]
    assert set(schema["parameters"]["properties"]["domain"]["enum"]) == permitted
    assert "password" not in str(schema).lower()


@pytest.mark.parametrize("role, domain, metric, group", [
    ("tutor", "pendaftaran", "siswa_unik", "program"),
    ("tutor", "jadwal", "jumlah_jadwal_aktif", "program"),
    ("tutor", "kehadiran", "persentase_hadir", "bulan"),
    ("siswa", "pendaftaran", "jumlah_pendaftaran", "status"),
    ("siswa", "tagihan", "nominal_belum_lunas", "program"),
    ("siswa", "pembayaran", "nominal_pembayaran_lunas", "bulan"),
    ("siswa", "nilai", "rata_rata_nilai", "jenis"),
    ("siswa", "kehadiran", "jumlah_hadir", "program"),
])
def test_compiled_queries_are_scoped_and_parameterized(role, domain, metric, group):
    safe = validate_role_dynamic_plan(plan(domain, metric, [group]), role)
    total, pars, groups_count, grouped, group_pars = compile_query(safe, role=role, user_id=171)
    assert "WHERE" in total and "GROUP BY" in grouped
    assert total.count("%s") == len(pars) and grouped.count("%s") == len(group_pars)
    assert 171 in pars and 171 in group_pars
    assert "171" not in total and "171" not in grouped
    assert "LIMIT 20" in grouped and "LIMIT 20" not in total
    assert "COUNT(*)" in groups_count
    assert not re.search(r"\b(?:INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|COPY|TRUNCATE)\b", total, re.I)
    if role == "tutor":
        assert "tutor_id=%s" in total or "own_s.tutor_id=%s" in total
        if domain == "pendaftaran":
            assert "e.status='aktif'" in total and "own_u.status='aktif'" in total
        if domain == "kehadiran":
            assert "own_e.status='aktif'" in total
    else:
        assert "e.student_id=%s" in total
        if domain in {"nilai", "kehadiran"}:
            assert "e_terakhir.student_id" in total and "i_akses.enrollment_id" in total
            assert "e.status IN ('aktif', 'selesai')" in total


@pytest.mark.parametrize("role,bad", [
    ("tutor", plan("tagihan", "jumlah_tagihan")),
    ("tutor", plan("nilai", "rata_rata_nilai")),
    ("tutor", plan("pendaftaran", "jumlah_pendaftaran", filters={"status":"selesai"})),
    ("tutor", plan("pendaftaran", "siswa_unik", ["bulan"])),
    ("tutor", plan("jadwal", "tutor_unik")),
    ("siswa", plan("jadwal", "jumlah_jadwal_aktif")),
    ("siswa", plan("pendaftaran", "siswa_unik")),
    ("siswa", plan("tagihan", "jumlah_tagihan", ["tutor"])),
    ("siswa", plan("nilai", "jumlah_nilai", filters={"raw_sql":"DELETE FROM users"})),
    ("siswa", dict(plan("nilai", "jumlah_nilai"), user_id=999)),
    ("siswa", plan("tagihan", "jumlah_tagihan", filters={"program_id":"1 OR TRUE"})),
    ("tutor", plan("kehadiran", "persentase_hadir", filters={"tanggal_dari":"2026-02-30"})),
])
def test_role_bypass_and_bad_plans_are_denied(role, bad):
    with pytest.raises((PermissionError, ValueError)):
        validate_role_dynamic_plan(bad, role)


@pytest.mark.parametrize("role", ["admin", "tutor", "siswa"])
def test_controller_routes_only_own_tool(role):
    class Repo:
        def __init__(self): self.calls = []
        def execute(self, uid, r, name, args):
            self.calls.append((uid, r, name, args))
            return {"data": [{"nilai": 4}], "agregat_global": 4}
    repo=Repo()
    session.set_user({"id": 71, "role": role, "status": "aktif"})
    controller=AIToolController(role,repo=repo,rag_tool=False)
    names={x["name"] for x in controller.declarations()}
    assert names.intersection(set(ROLE_DYNAMIC_NAMES.values())) == {ROLE_DYNAMIC_NAMES[role]}
    own_plan=plan("pendaftaran", "jumlah_pendaftaran")
    assert controller.execute(ROLE_DYNAMIC_NAMES[role], own_plan)["agregat_global"] == 4
    for other in set(ROLE_DYNAMIC_NAMES.values()) - {ROLE_DYNAMIC_NAMES[role]}:
        with pytest.raises(PermissionError):
            controller.execute(other, own_plan)
    assert len(repo.calls) == 1
    session.set_user({"id": 72, "role":role, "status":"aktif"})
    with pytest.raises(PermissionError):
        controller.execute(ROLE_DYNAMIC_NAMES[role], own_plan)


class Cursor:
    def __init__(self, rows): self.rows=list(rows); self.calls=[]
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, params=None):
        params=params or ()
        assert sql.count('%s') == len(params), (sql,params)
        self.calls.append((sql,params))
    def fetchone(self): return self.rows.pop(0) if self.rows else {}
    def fetchmany(self, limit): return []

class Connection:
    def __init__(self, cur): self.cur=cur
    def __enter__(self): return self
    def __exit__(self, *_): return False
    @contextmanager
    def transaction(self): yield
    def cursor(self, **_): return self.cur

class Pool:
    def __init__(self, cursor): self.cursor_=cursor
    def connection(self, timeout):
        assert timeout == 5
        return Connection(self.cursor_)


def fake_psycopg(monkeypatch):
    monkeypatch.setitem(sys.modules, 'psycopg',types.ModuleType('psycopg'))
    rows=types.ModuleType('psycopg.rows'); rows.dict_row=object()
    monkeypatch.setitem(sys.modules,'psycopg.rows',rows)


@pytest.mark.parametrize('role,domain,metric', [
    ('tutor','pendaftaran','siswa_unik'),
    ('siswa','tagihan','nominal_belum_lunas'),
    ('siswa','nilai','rata_rata_nilai'),
])
def test_repository_revalidates_login_role_before_running_scoped_query(monkeypatch,role,domain,metric):
    fake_psycopg(monkeypatch)
    name=ROLE_DYNAMIC_NAMES[role]
    cur=Cursor([{'role':role,'status':'aktif'},{'nilai':Decimal('15.50')}])
    result=AIReadRepository(pool=Pool(cur)).execute(44,role,name,plan(domain,metric))
    assert result['agregat_global']=='15.50'
    assert result['cakupan']
    assert cur.calls[0][0] == 'SET TRANSACTION READ ONLY'
    assert cur.calls[1][0].startswith('SET LOCAL statement_timeout')
    assert cur.calls[2][1] == (44,)
    assert cur.calls[3][1][-1] == 44 or 44 in cur.calls[3][1]
    cur=Cursor([{'role':'admin','status':'aktif'}])
    with pytest.raises(PermissionError):
        AIReadRepository(pool=Pool(cur)).execute(44,role,name,plan(domain,metric))
    assert len(cur.calls)==3


def test_evidence_refuses_without_real_tool_and_accepts_scoped_proof():
    q = 'Berapa total tagihan saya?'
    evidence=HybridEvidence(original_query=q)
    assert evidence.refusal(q)
    evidence.record('student_dynamic_query', {'data':[{'nilai':'125000'}], 'rencana':{'domain':'tagihan'}})
    assert evidence.refusal(q) is None
    q2='Berapa jumlah akun siswa aktif?'
    assert evidence.refusal(q2)


def test_missing_principal_fails_even_if_plan_valid():
    p=validate_role_dynamic_plan(plan('pendaftaran','jumlah_pendaftaran'),'siswa')
    with pytest.raises(PermissionError):
        compile_query(p, role='siswa', user_id=None)
    with pytest.raises(PermissionError):
        compile_query(p, role='siswa', user_id=0)


def test_evidence_requires_correct_dynamic_domain():
    for question, wrong, right in [
        ('Berapa total tagihan saya?', 'nilai', 'tagihan'),
        ('Berapa jumlah pembayaran saya?', 'tagihan', 'pembayaran'),
        ('Berapa rata rata nilai saya?', 'pembayaran', 'nilai'),
        ('Berapa jumlah siswa aktif di kelas saya?', 'jadwal', 'pendaftaran'),
    ]:
        name = 'tutor_dynamic_query' if 'siswa aktif' in question else 'student_dynamic_query'
        ledger = HybridEvidence(original_query=question)
        assert ledger.refusal(question)
        ledger.record(name, {'data': [{'nilai': 5}], 'rencana': {'domain': wrong}})
        assert ledger.refusal(question), (question,wrong)
        ledger.record(name, {'data': [{'nilai': 5}], 'rencana': {'domain': right}})
        assert ledger.refusal(question) is None, (question,right)
