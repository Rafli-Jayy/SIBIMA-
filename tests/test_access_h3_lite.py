"""Regression contracts for Lite H+3 academic gating (no live DB required)."""

from datetime import date, timedelta
import re

import pytest

from app.repositories import student_repo, enrollment_repo
from app.repositories.class_access_sql import AKSES_TERKUNCI_SQL


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, args=None):
        self.queries.append((sql, args))

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self.cur = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self, **_kwargs):
        return self.cur


class FakePool:
    def __init__(self, rows=None):
        self.cursor_obj = FakeCursor(rows if rows is not None else [])

    def connection(self):
        return FakeConnection(self.cursor_obj)


def _capture(monkeypatch, module, fn, *args):
    pool = FakePool()
    monkeypatch.setattr(module, "pool", pool)
    result = getattr(module, fn)(*args)
    assert result == []
    assert len(pool.cursor_obj.queries) == 1
    return pool.cursor_obj.queries[0]


@pytest.mark.parametrize("fn,args", [
    ("daftar_jadwal", (7,)),
    ("daftar_jadwal", (7, "senin", 12)),
    ("rekap_absensi", (7,)),
    ("rekap_absensi", (7, 12)),
    ("daftar_absensi", (7, 12)),
    ("ringkasan_nilai", (7, 12)),
    ("daftar_nilai", (7, 12)),
    ("daftar_catatan_materi", (7, 12)),
])
def test_all_academic_repo_queries_reject_overdue_active_enrollments(monkeypatch, fn, args):
    sql, params = _capture(monkeypatch, student_repo, fn, *args)
    assert "AND NOT " + AKSES_TERKUNCI_SQL in sql
    assert "i_akses.enrollment_id = e.id" in sql
    assert "i_akses.status = 'belum_dibayar'" in sql
    assert "e.status = 'aktif'" in sql
    assert "i_akses.jatuh_tempo < CURRENT_DATE - 3" in sql
    assert params[0] == 7


@pytest.mark.parametrize("mod,method", [
    (student_repo, "daftar_kelas"),
    (student_repo, "daftar_program_akademik"),
    (enrollment_repo, "enrollment_siswa"),
])
def test_status_listing_displays_blocked_flag_without_changing_enrollment(monkeypatch, mod, method):
    sql, params = _capture(monkeypatch, mod, method, 7)
    assert AKSES_TERKUNCI_SQL + " AS akses_terkunci" in sql
    assert "e.student_id = %s" in sql
    assert params == (7,)
    assert "UPDATE enrollments" not in sql


def test_guard_requires_positive_invoice_amount_and_unpaid_status():
    assert "i_akses.jumlah > 0" in AKSES_TERKUNCI_SQL
    assert "i_akses.status = 'belum_dibayar'" in AKSES_TERKUNCI_SQL
    assert "e.status = 'aktif'" in AKSES_TERKUNCI_SQL
    assert "UPDATE" not in AKSES_TERKUNCI_SQL.upper()


@pytest.mark.parametrize("days_after_due,expected_locked", [
    (-1, False), (0, False), (1, False), (2, False), (3, False),
    (4, True), (7, True),
])
def test_h3_calendar_day_boundary(days_after_due, expected_locked):
    """Companion to the SQL `jatuh_tempo < CURRENT_DATE - 3` contract.

    Reference date arithmetic only; live PostgreSQL verification is separate.
    """
    due = date(2026, 11, 10)
    today = due + timedelta(days=days_after_due)
    assert (due < today - timedelta(days=3)) is expected_locked


def test_payment_success_opens_class_on_next_check_via_invoice_status():
    """Asserts the SQL queries unpaid invoices, not a persistent suspension flag."""
    assert re.search(r"i_akses\.status\s*=\s*'belum_dibayar'", AKSES_TERKUNCI_SQL)
    assert "payments" not in AKSES_TERKUNCI_SQL.lower()
    assert "ditangguhkan" not in AKSES_TERKUNCI_SQL


@pytest.mark.parametrize("fn,args", [
    ("daftar_kelas", (0,)),
    ("daftar_program_akademik", (True,)),
    ("daftar_jadwal", (-1,)),
    ("daftar_nilai", (7, 0)),
    ("daftar_catatan_materi", (7, -1)),
])
def test_invalid_identity_is_still_rejected(fn, args):
    with pytest.raises(ValueError):
        getattr(student_repo, fn)(*args)


def test_sql_guard_does_not_block_historical_finished_classes():
    assert "e.status = 'aktif'" in AKSES_TERKUNCI_SQL
    assert "e.status IN ('aktif', 'selesai')" in _get_sql_for_program_listing()


def _get_sql_for_program_listing():
    import inspect
    return inspect.getsource(student_repo.daftar_program_akademik)
