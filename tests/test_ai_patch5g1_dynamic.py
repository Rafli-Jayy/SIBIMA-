"""Offline regression for V1 dynamic analytics with strict allowlists."""
from contextlib import contextmanager
from decimal import Decimal
import re
import sys
import types

import pytest

from app import session
from app.repositories.ai_dynamic_repo import compile_query, execute_dynamic
from app.repositories.ai_read_repo import AIReadRepository
from app.services.ai_dynamic_plan import DOMAINS, NAME, validate_dynamic_plan
from app.services.ai_tool_controller import AIToolController
from app.services.hybrid_evidence import HybridEvidence


@pytest.fixture(autouse=True)
def restore_session():
    prev = session.get_user()
    session.logout()
    yield
    session.set_user(prev)


def plan(domain, metric, groups=(), filters=None, **extra):
    return {"domain": domain, "metrik": metric, "kelompok": list(groups), "filter": filters or {}, **extra}


@pytest.mark.parametrize("domain,metric,groups", [
    ("pendaftaran", "siswa_unik", ["program", "status"]),
    ("pendaftaran", "jumlah_pendaftaran", ["bulan", "program"]),
    ("tagihan", "nominal_belum_lunas", ["bulan", "program"]),
    ("tagihan", "jumlah_tagihan", ["status"]),
    ("pembayaran", "nominal_pembayaran_lunas", ["program", "bulan"]),
    ("pembayaran", "jumlah_pembayaran", ["status"]),
    ("jadwal", "tutor_unik", ["program"]),
    ("jadwal", "jumlah_jadwal_aktif", ["tutor", "program"]),
    ("nilai", "rata_rata_nilai", ["program", "jenis"]),
    ("nilai", "jumlah_nilai", ["bulan"]),
    ("kehadiran", "persentase_hadir", ["program", "bulan"]),
    ("kehadiran", "jumlah_catatan_absensi", []),
])
def test_valid_plan_sql_structure(domain, metric, groups):
    validated = validate_dynamic_plan(plan(domain, metric, groups), "admin")
    total, params, count, grouped, other_params = compile_query(validated)
    assert total.startswith("SELECT ") and " FROM " in total
    assert total.count("%s") == len(params)
    assert count.count("%s") == len(other_params)
    assert grouped.count("%s") == len(other_params)
    assert ("GROUP BY" in grouped) == bool(groups)
    if groups:
        assert "LIMIT 20" in grouped
        assert "banyak_kelompok" in count
    for sql in (total, count, grouped):
        assert not re.search(r"\b(?:INSERT|UPDATE|DELETE|DROP|ALTER|COPY|CREATE|TRUNCATE)\b", sql, re.I)


@pytest.mark.parametrize("bad_plan", [
    {"domain": "users", "metrik": "password_hash"},
    {"domain": "pendaftaran", "metrik": "jumlah_tagihan"},
    {"domain": "pendaftaran", "metrik": "jumlah_pendaftaran", "kelompok": ["email"]},
    plan("pendaftaran", "siswa_unik", ["program", "program"]),
    plan("pendaftaran", "siswa_unik", ["program", "status", "bulan"]),
    plan("pendaftaran", "siswa_unik", ["program"], {"status": "aktif' OR TRUE --"}),
    plan("tagihan", "nominal_belum_lunas", ["program"], {"status": "lunas"}),
    plan("pembayaran", "nominal_pembayaran_lunas", [], {"status": "direfund"}),
    plan("jadwal", "tutor_unik", [], {"tanggal_dari": "2026-01-01"}),
    plan("kehadiran", "persentase_hadir", [], {"status": "H"}),
    plan("nilai", "rata_rata_nilai", ["tutor"]),
    plan("nilai", "rata_rata_nilai", [], {"program_id": True}),
    plan("nilai", "rata_rata_nilai", [], {"program_id": -5}),
    plan("nilai", "rata_rata_nilai", [], {"tanggal_dari": "2026-02-30"}),
    plan("tagihan", "jumlah_tagihan", [], {"tanggal_dari": "2026-11-09"}),
    plan("nilai", "rata_rata_nilai", [], {"tanggal_dari": "2026-12-01", "tanggal_sampai": "2026-10-01"}),
    plan("nilai", "rata_rata_nilai", [], {"tanggal_dari": "2026-11-09 OR TRUE"}),
    plan("pendaftaran", "jumlah_pendaftaran", [], {"raw_sql": "SELECT * FROM users"}),
    dict(plan("nilai", "rata_rata_nilai"), sql="SELECT 1"),
    dict(plan("nilai", "rata_rata_nilai"), urut="RANDOM()"),
    dict(plan("nilai", "rata_rata_nilai"), kelompok="program"),
])
def test_invalid_plan_rejected(bad_plan):
    with pytest.raises((ValueError, PermissionError)):
        validate_dynamic_plan(bad_plan, "admin")


@pytest.mark.parametrize("role", ["siswa", "tutor", "root", None])
def test_non_admin_plan_rejected(role):
    with pytest.raises(PermissionError):
        validate_dynamic_plan(plan("pendaftaran", "jumlah_pendaftaran"), role)


def test_all_domain_metrics_and_dimensions_come_from_catalog():
    for domain, spec in DOMAINS.items():
        for metric in spec["metrics"]:
            for grouping in [[], *[[x] for x in spec["dimensions"]]]:
                parsed = validate_dynamic_plan(plan(domain, metric, grouping), "admin")
                compile_query(parsed)
    assert len(DOMAINS) == 6


def test_parameters_never_joined_to_sql():
    parsed = validate_dynamic_plan(plan("pendaftaran", "siswa_unik", ["program"], {
        "program_id": 8, "status": "aktif", "tanggal_dari": "2026-11-01", "tanggal_sampai": "2026-11-09"}), "admin")
    total, params, count, grouped, _ = compile_query(parsed)
    for sql in (total, count, grouped):
        assert "2026-11-09" not in sql and "aktif" not in sql
        assert "WHERE" in sql
    assert params == (8, "aktif", "2026-11-01", "2026-11-09")
    # A metric-level fixed status is also a SQL parameter, never raw user input.
    parsed = validate_dynamic_plan(plan("tagihan", "nominal_belum_lunas", [], {"program_id": 6}), "admin")
    _, params, _, _, _ = compile_query(parsed)
    assert params == ("belum_dibayar", 6)


class Cursor:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def __init__(self, one, many=None):
        self.one = list(one)
        self.many = list(many or [])
        self.calls = []
    def execute(self, sql, params=None):
        params = params or ()
        assert sql.count("%s") == len(params), (sql, params)
        assert not re.search(r"\b(?:UPDATE|DELETE|INSERT|DROP|ALTER|CREATE|COPY|TRUNCATE)\b", sql, re.I)
        self.calls.append((sql, params))
    def fetchone(self): return self.one.pop(0) if self.one else {}
    def fetchmany(self, cap):
        assert cap == 20
        return self.many.pop(0) if self.many else []


class Conn:
    def __init__(self, cur): self.cur=cur
    def __enter__(self): return self
    def __exit__(self, *args): return False
    @contextmanager
    def transaction(self): yield
    def cursor(self, **kwargs): return self.cur


class Pool:
    def __init__(self, cur): self.cur=cur
    def connection(self, timeout):
        assert timeout == 5
        return Conn(self.cur)


def fake_psycopg(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", types.ModuleType("psycopg"))
    rows = types.ModuleType("psycopg.rows")
    rows.dict_row = object()
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows)


def test_total_uses_full_population_and_group_is_limited():
    cur = Cursor([{"nilai": Decimal("2000000.00")}, {"banyak_kelompok": 32}],
                 [[{"program_id": 5, "program": "Python", "nilai": Decimal("180000.00")}]] )
    result = execute_dynamic(cur, "admin", plan("tagihan", "nominal_belum_lunas", ["program"]))
    assert result["agregat_global"] == "2000000.00"
    assert result["data"] == [{"program_id": 5, "program": "Python", "nilai": "180000.00"}]
    assert result["total_kelompok"] == 32
    assert result["jumlah_ditampilkan"] == 1
    assert result["terpotong"] is True
    assert len(cur.calls) == 3
    assert "LIMIT 20" not in cur.calls[0][0]
    assert "COUNT(*)" in cur.calls[1][0]


def test_null_attendance_percentage_not_zero():
    result = execute_dynamic(Cursor([{"nilai": None}]), "admin", plan("kehadiran", "persentase_hadir"))
    assert result["agregat_global"] is None
    assert "NULLIF" in compile_query(validate_dynamic_plan(plan("kehadiran", "persentase_hadir"), "admin"))[0]


def test_controller_role_scope_and_session_change():
    class Repo:
        def __init__(self): self.calls=[]
        def execute(self, uid, role, name, args):
            self.calls.append((uid,role,name,args));return {"data":[],"agregat_global":3}
    repo=Repo()
    for role in ("admin", "tutor", "siswa"):
        session.set_user({"id": 17, "role": role, "status": "aktif"})
        control=AIToolController(role, repo=repo, rag_tool=False)
        names={x["name"] for x in control.declarations()}
        assert (NAME in names) == (role == "admin")
        if role != "admin":
            with pytest.raises(PermissionError):
                control.execute(NAME, plan("pendaftaran", "jumlah_pendaftaran"))
    assert not repo.calls
    session.set_user({"id": 17, "role": "admin", "status": "aktif"})
    control=AIToolController("admin", repo=repo, rag_tool=False)
    out=control.execute(NAME, plan("pendaftaran", "siswa_unik", ["program"]))
    assert out["agregat_global"] == 3
    assert repo.calls[-1][0:3] == (17, "admin", NAME)
    session.set_user({"id": 18, "role": "admin", "status": "aktif"})
    with pytest.raises(PermissionError):
        control.execute(NAME, plan("pendaftaran", "siswa_unik"))
    assert len(repo.calls) == 1


def test_repository_db_role_revalidation_before_data_query(monkeypatch):
    fake_psycopg(monkeypatch)
    params=plan("pendaftaran", "jumlah_pendaftaran")
    cur=Cursor([{"role":"admin", "status":"aktif"}, {"nilai":27}])
    value=AIReadRepository(pool=Pool(cur)).execute(17, "admin", NAME, params)
    assert value["agregat_global"] == 27
    assert cur.calls[0][0] == "SET TRANSACTION READ ONLY"
    assert "statement_timeout" in cur.calls[1][0]
    assert "FROM users WHERE id=%s" in cur.calls[2][0]
    assert len(cur.calls) == 4
    cur=Cursor([{"role":"siswa", "status":"aktif"}])
    with pytest.raises(PermissionError):
        AIReadRepository(pool=Pool(cur)).execute(17, "admin", NAME, params)
    assert len(cur.calls) == 3
    with pytest.raises(PermissionError):
        AIReadRepository(pool=Pool(cur)).execute(17, "siswa", NAME, params)


def test_evidence_accepts_grounded_dynamic_results_and_no_fake_proof():
    query="Berapa jumlah siswa aktif di program Python?"
    evidence=HybridEvidence(original_query=query)
    assert evidence.refusal(query) is not None
    evidence.record(NAME, {"data":[{"program":"Python", "nilai":12}]})
    assert evidence.refusal(query) is None
    # Account status is NOT enrollment status; dynamic enrollment data does
    # not prove how many account rows have users.status='aktif'.
    assert evidence.refusal("Berapa jumlah akun siswa aktif?") is not None
