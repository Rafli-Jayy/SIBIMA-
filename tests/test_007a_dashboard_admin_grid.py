"""PATCH-007A: test grid Admin, routing lama, dan SQL read-only."""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from rich.console import Console

from app.ui import admin_dashboard_grid as ui


def test_semua_menu_lama_tetap_terjangkau():
    kode = [k for _, entries in ui.KELOMPOK_MENU for _, k in entries]
    assert len(kode) == len(set(kode)) == 11
    assert set(kode) == {
        "konfirmasi", "akun", "siswa", "tutor", "program", "pendaftaran",
        "jadwal", "pembayaran", "laporan", "pengumuman", "log",
    }


def _render(stats, rows, width=120, name="Admin"):
    output = Console(width=width, force_terminal=False, color_system=None, record=True)
    output.print(ui.render_dashboard_admin(name, stats, rows, width=width))
    return output.export_text()


@pytest.mark.parametrize("width", [52, 80, 130])
def test_grid_sesuai_lebar_dan_data_asli(width):
    stats = {
        "siswa_aktif": 8, "tutor_aktif": 3, "program_buka": 4,
        "enrollment_aktif": 12, "konfirmasi_akun": 2,
        "konfirmasi_pendaftaran": 1, "tagihan_belum_lunas": 5,
        "tagihan_terlambat": 3, "sesi_perlu_laporan": 1,
    }
    result = _render(stats, [], width)
    assert "Siswa Aktif" in result
    assert "Invoice" in result
    assert "8" in result
    assert "12" in result
    assert "Tidak ada jadwal rutin aktif" in result


def test_gagal_database_bukan_nol():
    t = _render(None, None)
    assert "tidak tersedia" in t.lower()
    assert "—" in t
    assert "Jadwal tidak dapat dimuat" in t


def test_nama_user_tidak_diparse_rich_markup():
    t = _render({"siswa_aktif": 0}, [], name="[red]X[/red]")
    assert "[red]X[/red]" in t


def test_jadwal_ada_dan_waktu_terlihat():
    from datetime import time
    t = _render({}, [{"program": "Matematika", "tutor": "Budi",
                      "ruang": "A", "jam_mulai": time(16),
                      "jam_selesai": time(17, 30)}], width=140)
    assert "Matematika" in t
    assert "16:00" in t
    assert "Budi" in t


def test_kembali_dari_submenu_tidak_menumpuk(monkeypatch):
    calls = iter([0, "kembali"])
    def fake_select(*args, **kwargs):
        return SimpleNamespace(ask=lambda: next(calls))
    import questionary
    monkeypatch.setattr(questionary, "select", fake_select)
    assert ui.pilih_modul_admin(None) == "dashboard"


def test_memilih_modul_admin_tetap_sama(monkeypatch):
    calls = iter([2, "jadwal"])
    def fake_select(*args, **kwargs):
        return SimpleNamespace(ask=lambda: next(calls))
    import questionary
    monkeypatch.setattr(questionary, "select", fake_select)
    assert ui.pilih_modul_admin(None) == "jadwal"


def test_keluar_dashboard_mengembalikan_logout(monkeypatch):
    import questionary
    monkeypatch.setattr(questionary, "select", lambda *a, **k:
                        SimpleNamespace(ask=lambda: None))
    assert ui.pilih_modul_admin(None) == "logout"


def test_query_ringkasan_dan_jadwal_readonly():
    source = Path(__file__).parents[1] / "app/repositories/admin_dashboard_repo.py"
    text = source.read_text(encoding="utf-8")
    assert "AT TIME ZONE 'Asia/Jakarta'" in text
    assert "status::text = 'perlu_laporan'" in text
    for forbidden in ("INSERT INTO", "UPDATE USERS", "DELETE FROM", "DROP TABLE"):
        assert forbidden not in text.upper()
    assert "s.aktif = TRUE" in text


def test_dashboard_menangani_error_stats_dan_schedule(monkeypatch):
    from app.repositories import admin_dashboard_repo
    def err():
        raise RuntimeError("DB unavailable")
    monkeypatch.setattr(admin_dashboard_repo, "ringkasan_admin", err)
    monkeypatch.setattr(admin_dashboard_repo, "jadwal_hari_ini_admin", err)
    output = Console(width=120, force_terminal=False, color_system=None, record=True)
    monkeypatch.setattr(ui, "console", output)
    ui.tampilkan_dashboard_admin("Admin")
    assert "tidak tersedia" in output.export_text().lower()


def test_repo_memakai_select_dan_mengembalikan_data_tiruan(monkeypatch):
    from app.repositories import admin_dashboard_repo as repo
    class Cur:
        def __init__(self): self.sqls = []
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql):
            assert sql.strip().startswith("SELECT")
            assert "INSERT" not in sql.upper()
            self.sqls.append(sql)
        def fetchone(self): return {"siswa_aktif": 8, "program_buka": 4}
        def fetchall(self): return [{"program": "Matematika SMA", "tutor": "A"}]
    cur = Cur()
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def cursor(self, **kwargs): return cur
    monkeypatch.setattr(repo.pool, "connection", lambda **kw: Conn())
    stats = repo.ringkasan_admin()
    rows = repo.jadwal_hari_ini_admin()
    assert stats["siswa_aktif"] == 8
    assert rows[0]["program"] == "Matematika SMA"
    assert len(cur.sqls) == 2
    assert "LIMIT 5" in cur.sqls[1]
