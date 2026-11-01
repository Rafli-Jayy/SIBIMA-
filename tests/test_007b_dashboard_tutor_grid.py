"""PATCH-007B: tampilan grid Tutor, data read-only, dan menu lama tetap utuh."""
from datetime import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

from app.ui import tutor_dashboard_grid as ui


STATS = {
    'program_diampu': 2, 'jadwal_aktif': 5,
    'siswa_aktif': 8, 'sesi_perlu_laporan': 1,
}
ROWS = [
    {'schedule_id': 9, 'hari': 'senin', 'jam_mulai': time(16),
     'jam_selesai': time(17, 30), 'nama_program': 'Matematika SMA',
     'nama_ruang': 'Ruang A', 'jumlah_siswa': 4,
     'hari_ini': True, 'status_sesi_hari_ini': 'perlu_laporan'},
    {'schedule_id': 10, 'hari': 'kamis', 'jam_mulai': time(13),
     'jam_selesai': time(14, 30), 'nama_program': 'Fisika SMA',
     'nama_ruang': 'Ruang B', 'jumlah_siswa': 4,
     'hari_ini': False, 'status_sesi_hari_ini': None},
]


def render(stats=STATS, rows=ROWS, *, width=120, name='Tutor A'):
    console = Console(width=width, color_system=None, force_terminal=False, record=True)
    console.print(ui.render_dashboard_tutor({'id': 5, 'nama_lengkap': name, 'username': 'pengajar'},
                                            stats, rows, width=width))
    return console.export_text()


@pytest.mark.parametrize('width', [52, 80, 128])
def test_layout_grid_semua_lebar_terminal(width):
    txt = render(width=width)
    assert 'Pusat Aktivitas Pengajar' in txt
    assert 'Program Diampu' in txt
    assert 'Perlu Laporan' in txt
    assert '8' in txt
    assert 'Matematika SMA' in txt
    assert 'JADWAL MINGGUAN' in txt


def test_dashboard_jadwal_real_dan_status_sesi():
    txt = render(width=135)
    assert '16:00' in txt
    assert 'Ruang A' in txt
    assert 'Perlu laporan' in txt
    assert 'Terjadwal ≠ sudah mengajar' in txt


def test_status_sesi_bukan_bukti_jadwal_selesai():
    assert ui._status({'status_sesi_hari_ini': None}) == 'Terjadwal'
    assert ui._status({'status_sesi_hari_ini': 'perlu_laporan'}) == 'Perlu laporan'
    assert ui._status({'status_sesi_hari_ini': 'selesai'}) == 'Selesai'
    assert ui._status({'status_sesi_hari_ini': 'batal'}) == 'Batal'
    assert ui._status({'status_sesi_hari_ini': 'terlaksana'}) == 'Sesi historis'


def test_jadwal_kosong_tidak_membuat_jadwal_palsu():
    t = render({'program_diampu': 0, 'jadwal_aktif': 0, 'siswa_aktif': 0,
                'sesi_perlu_laporan': 0}, [], width=120)
    assert 'Tidak ada jadwal mengajar aktif hari ini' in t
    assert 'Belum ada jadwal aktif untuk akun Tutor ini' in t
    assert '0' in t


def test_database_gagal_tidak_menganggap_nol():
    t = render(None, None)
    assert 'tidak dapat dimuat' in t.lower()
    assert 'Statistik tidak tersedia' in t
    assert '—' in t


def test_nama_pengguna_tidak_dieksekusi_sebagai_markup():
    assert '[red]Tutor X[/red]' in render(name='[red]Tutor X[/red]')


def test_jadwal_bukan_hari_ini_tidak_muncul_di_panel_hari_ini():
    t = render(STATS, [ROWS[1]])
    assert 'Tidak ada jadwal mengajar aktif hari ini' in t
    assert 'Fisika SMA' in t  # tetap muncul di daftar mingguan


def test_query_stats_readonly_dan_count_distinct():
    text = (Path(__file__).parents[1] / 'app/repositories/tutor_dashboard_repo.py').read_text(encoding='utf-8')
    assert 'COUNT(DISTINCT e.student_id)' in text
    assert "cs.status::text = 'perlu_laporan'" in text
    assert "AT TIME ZONE 'Asia/Jakarta'" in text
    assert 's.tutor_id = %s' in text
    for forbidden in ('INSERT INTO', 'DELETE FROM', 'DROP TABLE', 'UPDATE SCHEDULES'):
        assert forbidden not in text.upper()


def test_semua_menu_tutor_lama_tetap_tersedia():
    text = (Path(__file__).parents[1] / 'app/ui/menu_tutor.py').read_text(encoding='utf-8')
    for code in ('jadwal', 'kelas', 'absensi', 'nilai', 'materi', 'profil', 'notifikasi', 'logout'):
        assert ('"' + code + '"') in text or ("'" + code + "'") in text
    assert 'tampilkan_dashboard_tutor(pengguna)' in text
    assert 'bersihkan_layar()' in text


def test_error_repo_tidak_memutus_dashboard(monkeypatch):
    from app.repositories import tutor_dashboard_repo
    def fail(_):
        raise RuntimeError('DB gagal')
    monkeypatch.setattr(tutor_dashboard_repo, 'ringkasan_tutor', fail)
    monkeypatch.setattr(tutor_dashboard_repo, 'jadwal_mingguan_tutor', fail)
    stream = Console(width=112, force_terminal=False, color_system=None, record=True)
    monkeypatch.setattr(ui, 'console', stream)
    ui.tampilkan_dashboard_tutor({'id': 5, 'username': 'tutor'})
    assert 'Statistik tidak tersedia' in stream.export_text()


def test_repo_hanya_membaca_dan_memakai_id_login(monkeypatch):
    from app.repositories import tutor_dashboard_repo as repo
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params):
            assert sql.lstrip().startswith('SELECT')
            calls.append((sql, params))
        def fetchone(self): return {'jadwal_aktif': 5}
        def fetchall(self): return [{'nama_program': 'Matematika SMA'}]
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self, **kwargs): return Cursor()
    monkeypatch.setattr(repo.pool, 'connection', lambda **k: Conn())
    assert repo.ringkasan_tutor(42)['jadwal_aktif'] == 5
    assert repo.jadwal_mingguan_tutor(42)[0]['nama_program'] == 'Matematika SMA'
    assert calls[0][1] == (42, 42, 42, 42)
    assert calls[1][1] == (42,)
