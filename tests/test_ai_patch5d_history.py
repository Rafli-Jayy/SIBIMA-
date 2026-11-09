"""Patch 5D offline security, history SQL and cursor regression tests."""
from contextlib import contextmanager
from datetime import datetime, timezone
import re
import sys
import types

import pytest

from app import session
from app.services.ai_history_plan import (HISTORY_TOOLS, _decode_cursor, make_cursor,
                                           tool_schema, validate_history_args)
from app.services.ai_tool_controller import AIToolController
from app.repositories.ai_history_repo import execute_history
from app.repositories.ai_read_repo import AIReadRepository
from app.services.hybrid_evidence import HybridEvidence


@pytest.fixture(autouse=True)
def restore_session():
    old = session.get_user()
    session.logout()
    yield
    session.set_user(old)


class DummyRepo:
    def __init__(self, found=None):
        self.found = found if found is not None else [{"user_id": 12, "role": "siswa"}]
        self.calls = []
    def execute(self, user_id, role, name, args):
        self.calls.append((user_id, role, name, args))
        return {"data": self.found if name == "admin_find_users" else [], "total_hasil": 0}


def controller(role="admin", found=None):
    session.set_user({"id": 99, "role": role, "status": "aktif"})
    repo = DummyRepo(found)
    return AIToolController(role, repo=repo, rag_tool=False), repo


def test_tools_only_admin_and_schema():
    assert len(HISTORY_TOOLS) == 4
    for role in ("admin", "tutor", "siswa"):
        c, _ = controller(role)
        declared = {x["name"] for x in c.declarations()}
        assert (set(HISTORY_TOOLS) <= declared) == (role == "admin")
        for name in HISTORY_TOOLS:
            assert tool_schema(name)["type"] == "function"
    c, repo = controller("siswa")
    with pytest.raises(PermissionError): c.execute("admin_system_history", {})
    assert repo.calls == []


@pytest.mark.parametrize("name,args", [
    ("admin_user_activity", {"user_id": 0}),
    ("admin_user_activity", {"user_id": True}),
    ("admin_user_activity", {}),
    ("admin_system_history", {"user_id": 12}),
    ("admin_system_history", {"raw_sql": "DROP TABLE users"}),
    ("admin_system_history", {"limit": 21}),
    ("admin_system_history", {"limit": 0}),
    ("admin_system_history", {"limit": True}),
    ("admin_system_history", {"tanggal_dari": "2026-02-30"}),
    ("admin_system_history", {"tanggal_dari": "2026-11-10", "tanggal_sampai": "2026-11-01"}),
    ("admin_system_history", {"aksi": "X\nY"}),
    ("admin_system_history", {"cursor": "not-a-cursor"}),
    ("admin_user_timeline", {"user_id": 1, "cursor": make_cursor(datetime(2026, 11, 9, tzinfo=timezone.utc), 4)}),
    ("admin_history_analytics", {"kelompok": "SQL"}),
    ("admin_history_analytics", {"cursor": "hack"}),
])
def test_reject_invalid_arguments(name, args):
    with pytest.raises(ValueError): validate_history_args(name, args)


def test_date_range_limit_default_and_cursor_roundtrip():
    args = validate_history_args("admin_system_history", {"tanggal_dari": "2026-11-01", "tanggal_sampai": "2026-11-09"})
    assert args["limit"] == 10
    assert validate_history_args("admin_history_analytics", {}) == {"kelompok": "aksi"}
    stamp = datetime(2026, 11, 9, 21, 1, 3, 456789, tzinfo=timezone.utc)
    x = make_cursor(stamp, 212)
    assert _decode_cursor(x, timeline=False) == (stamp, 212)
    t = make_cursor(stamp, 21, seq=5)
    assert _decode_cursor(t, timeline=True) == (stamp, 5, 21)
    assert validate_history_args("admin_user_timeline", {"user_id": 12, "cursor": t})["cursor"] == t


def test_user_selection_required_and_reset_on_new_search():
    c, repo = controller()
    with pytest.raises(PermissionError): c.execute("admin_user_activity", {"user_id": 12})
    c.execute("admin_find_users", {"query": "Dira"})
    c.execute("admin_user_activity", {"user_id": 12})
    assert repo.calls[-1][2] == "admin_user_activity"
    with pytest.raises(PermissionError): c.execute("admin_user_timeline", {"user_id": 13})
    repo.found = []
    c.execute("admin_find_users", {"query": "Nara"})
    with pytest.raises(PermissionError): c.execute("admin_user_timeline", {"user_id": 12})


def test_ambiguous_name_cannot_resolve_timeline():
    c, _ = controller(found=[{"user_id":12,"role":"siswa"}, {"user_id":13,"role":"tutor"}])
    c.execute("admin_find_users", {"query": "Rafi"})
    with pytest.raises(PermissionError, match="Beberapa akun"):
        c.execute("admin_user_activity", {"user_id": 12})


def test_session_change_and_disabled_user_denied():
    c, repo = controller()
    session.set_user({"id": 100, "role": "admin", "status": "aktif"})
    with pytest.raises(PermissionError): c.execute("admin_system_history", {})
    assert not repo.calls
    session.set_user({"id": 99, "role": "admin", "status": "ditolak"})
    with pytest.raises(PermissionError): c.execute("admin_system_history", {})


class FakeCursor:
    def __init__(self, single=(), many=()):
        self.single = list(single)
        self.many = list(many)
        self.queries = []
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None):
        params = params or ()
        assert sql.count("%s") == len(params), (sql.count("%s"), len(params), sql)
        assert not re.search(r"\b(?:INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE)\b", sql, re.I)
        self.queries.append((sql, params))
    def fetchone(self):
        return self.single.pop(0) if self.single else {}
    def fetchmany(self, cap):
        return self.many.pop(0) if self.many else []


class FakeConn:
    def __init__(self, cur): self.cur = cur
    def __enter__(self): return self
    def __exit__(self, *a): return False
    @contextmanager
    def transaction(self): yield
    def cursor(self, **kwargs): return self.cur


class FakePool:
    def __init__(self, cur): self.cur = cur
    def connection(self, timeout):
        assert timeout == 5
        return FakeConn(self.cur)


def fake_psycopg(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", types.ModuleType("psycopg"))
    m = types.ModuleType("psycopg.rows"); m.dict_row=object()
    monkeypatch.setitem(sys.modules, "psycopg.rows", m)


def test_repository_checks_real_role_and_readonly(monkeypatch):
    fake_psycopg(monkeypatch)
    cur = FakeCursor(single=[{"role":"admin", "status":"aktif"}, {"total_hasil": 2}],
                     many=[[{"id":17,"user_id":999,"pelaku_user_id":999,"pelaku":"Nara",
                            "aksi":"LOGIN","detail":"OTP=123456 SECRET=abc",
                            "waktu":datetime(2026,11,9,14,tzinfo=timezone.utc)}]])
    repo = AIReadRepository(pool=FakePool(cur))
    result = repo.execute(99,"admin","admin_system_history",{"limit":10})
    assert result["total_hasil"] == 2
    assert "detail" not in result["data"][0]
    assert "SECRET" not in str(result)
    assert "SET TRANSACTION READ ONLY" in cur.queries[0][0]
    assert "statement_timeout" in cur.queries[1][0]
    assert "FROM users WHERE id=%s" in cur.queries[2][0]
    assert "COUNT(*)" in cur.queries[3][0]
    with pytest.raises(PermissionError): repo.execute(99,"tutor","admin_system_history",{})


def test_real_role_mismatch_denied_before_history_sql(monkeypatch):
    fake_psycopg(monkeypatch)
    cur = FakeCursor(single=[{"role":"siswa","status":"aktif"}])
    repo = AIReadRepository(pool=FakePool(cur))
    with pytest.raises(PermissionError): repo.execute(99,"admin","admin_system_history",{})
    assert not any("activity_logs" in query for query,_ in cur.queries)


def test_history_list_cursor_and_no_raw_detail():
    t = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    rows = [{"id":v,"pelaku":"Tutor","aksi":"LOGIN","detail":"secret password",
             "waktu":t} for v in (14,13,12)]
    cur = FakeCursor(single=[{"total_hasil":27}], many=[rows])
    result = execute_history(cur,"admin","admin_system_history",{"limit":2})
    assert result["total_hasil"] == 27
    assert result["terpotong"] is True
    assert result["jumlah_ditampilkan"] == 2
    assert len(result["data"]) == 2
    assert "detail" not in result["data"][0]
    assert _decode_cursor(result["next_cursor"], timeline=False) == (t,13)
    assert "created_at, l.id" in cur.queries[-1][0]
    assert "Asia/Jakarta" in cur.queries[-1][0]


def test_timeline_verified_sources_and_not_history_status():
    t=datetime(2026,11,8,12,tzinfo=timezone.utc)
    cur = FakeCursor(single=[{"id":12},{"total_hasil":1}],
                     many=[[{"waktu":t,"urut":2,"entity_id":34,"sumber_tabel":"enrollments",
                             "jenis_peristiwa":"pendaftaran_dibuat","status_terkini":"aktif",
                             "program":"Python"}]])
    out = execute_history(cur,"admin","admin_user_timeline",{"user_id":12,"limit":10})
    assert out["data"][0]["jenis_peristiwa"] == "pendaftaran_dibuat"
    assert "status SEKARANG" in out["basis"]
    assert len(cur.queries) == 3
    for sql, params in cur.queries:
        assert "activity_logs.detail" not in sql
    assert cur.queries[1][1][:7] == (12,)*7


def test_analytics_over_twenty_and_actor_grouping_by_id():
    cur = FakeCursor(single=[{"total_hasil":87}, {"banyak_kelompok":24}],
                     many=[[{"kelompok":"Rafi","pelaku_user_id":11,"jumlah":52}]])
    out=execute_history(cur,"admin","admin_history_analytics",{"kelompok":"pelaku"})
    assert out["total_hasil"] == 87
    assert out["total_kelompok"] == 24
    assert out["terpotong"] is True
    assert out["jumlah_ditampilkan"] == 1
    assert "GROUP BY l.user_id" in cur.queries[-1][0]
    assert "LIMIT 20" in cur.queries[-1][0]


def test_refusal_when_history_not_retrieved():
    ev=HybridEvidence(original_query="Tampilkan riwayat sistem hari ini")
    assert ev.refusal("Tampilkan riwayat sistem hari ini") is not None
    ev.record("admin_system_history", {"data": []})
    assert ev.refusal("Tampilkan riwayat sistem hari ini") is None
