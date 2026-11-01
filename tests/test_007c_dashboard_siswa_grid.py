"""PATCH-007C: dashboard Siswa grid, SQL aman, navigasi lama utuh."""
from datetime import time
from decimal import Decimal
from pathlib import Path

import pytest
from rich.console import Console

from app.ui import student_dashboard_grid as ui

STATS = {'kelas_aktif': 2, 'pertemuan_hadir': 5, 'rata_nilai_tercatat': Decimal('84.50'),
         'tagihan_belum_lunas': 1, 'jumlah_tagihan': Decimal('150000'), 'tagihan_terlambat': 0}
ENROLL = [
    {'nama_program': 'Matematika SMA', 'jenjang': 'SMA', 'status': 'aktif'},
    {'nama_program': 'Bahasa Inggris', 'jenjang': 'SMA', 'status': 'aktif'},
    {'nama_program': 'Fisika', 'jenjang': 'SMA', 'status': 'menunggu_pembayaran'},
]
JADWAL = [
    {'nama_program': 'Matematika SMA', 'nama_ruang': 'Ruang A', 'nama_tutor': 'Tutor A',
     'hari':'senin', 'jam_mulai':time(16), 'jam_selesai':time(17,30), 'hari_ini':True},
    {'nama_program': 'Bahasa Inggris', 'nama_ruang': 'Ruang B', 'nama_tutor': 'Tutor B',
     'hari':'kamis', 'jam_mulai':time(13), 'jam_selesai':time(14,30), 'hari_ini':False},
]


def render(stats=STATS, jadwal=JADWAL, enrollments=ENROLL, width=118,
           name='Siswa Contoh'):
    con = Console(width=width, color_system=None, force_terminal=False, record=True)
    con.print(ui.render_dashboard_siswa({'id':42,'username':'siswa', 'nama_lengkap':name},
                                        enrollments, stats, jadwal, width=width))
    return con.export_text()


@pytest.mark.parametrize('width', [53, 80, 120])
def test_grid_adaptif_tiga_ukuran(width):
    txt = render(width=width)
    for label in ('Pusat Aktivitas Belajar', 'Kelas Aktif', 'Hadir',
                  'Rata-rata Nilai', 'Tagihan', 'KELAS & PENDAFTARAN',
                  'JADWAL MINGGUAN', 'AKSES CEPAT'):
        assert label in txt, (label, width, txt)
    assert 'Matematika SMA' in txt


def test_jadwal_hari_ini_bukan_semua_hari():
    txt = render(width=130)
    today_part = txt.split('JADWAL HARI INI')[1].split('JADWAL MINGGUAN')[0]
    assert '16:00' in today_part
    assert '13:00' not in today_part
    assert 'Ruang A' in today_part


def test_nilai_kosong_bukan_nol():
    zero = dict(STATS, rata_nilai_tercatat=None)
    assert 'Belum ada' in render(stats=zero)
    assert '0.00' not in render(stats=zero).split('KELAS & PENDAFTARAN')[0]


def test_database_gagal_bukan_angka_nol():
    txt = render(stats=None, jadwal=None)
    assert 'Statistik tidak tersedia' in txt
    assert 'Jadwal tidak dapat dimuat' in txt
    assert '—' in txt


def test_kelas_belum_ada_dan_menu_katalog():
    txt = render(stats=dict(STATS, kelas_aktif=0, tagihan_belum_lunas=0),
                 jadwal=[], enrollments=[])
    assert 'Belum ada pendaftaran' in txt
    assert 'Belum ada jadwal' in txt
    assert 'Katalog Program' in txt


def test_tagihan_dan_antrean_tidak_ditampilkan_ganda():
    txt = render()
    assert '1 pendaftaran menunggu pembayaran pertama' in txt
    assert '1 invoice belum lunas' in txt
    assert 'Rp 150.000' in txt
    assert txt.count('1 invoice belum lunas') == 1


def test_markup_nama_diperlakukan_sebagai_teks():
    assert '[red]Tes X[/red]' in render(name='[red]Tes X[/red]')


def test_ringkasan_hanya_sql_select_dan_enrollment_id():
    repo = Path(__file__).parents[1]/'app/repositories/student_dashboard_repo.py'
    source = repo.read_text(encoding='utf-8')
    assert 'a.enrollment_id' in source
    assert "cs.status::text = 'selesai'" in source
    assert "e.status = 'aktif'" in source
    assert "AT TIME ZONE 'Asia/Jakarta'" in source
    assert 'e.student_id = %s' in source
    assert 'AND EXISTS (' in source
    for bad in ('INSERT INTO', 'UPDATE ENROLLMENTS', 'DELETE FROM', 'DROP TABLE'):
        assert bad not in source.upper()


def test_semua_menu_siswa_lama_tetap_ada():
    text = (Path(__file__).parents[1]/'app/ui/menu_siswa.py').read_text(encoding='utf-8')
    assert 'tampilkan_dashboard_siswa(pengguna, enrollments)' in text
    for key in ('katalog', 'pendaftaran', 'jadwal', 'absensi', 'nilai',
                'pembayaran', 'materi', 'notifikasi', 'ai', 'profil', 'logout'):
        assert f'value="{key}"' in text


def test_gagal_membaca_repo_tetap_menampilkan_dashboard(monkeypatch):
    from app.repositories import student_dashboard_repo
    def fail(_): raise RuntimeError('simulasi DB gagal')
    monkeypatch.setattr(student_dashboard_repo, 'ringkasan_siswa', fail)
    monkeypatch.setattr(student_dashboard_repo, 'jadwal_mingguan_siswa', fail)
    con = Console(width=118, color_system=None, record=True)
    monkeypatch.setattr(ui, 'console', con)
    ui.tampilkan_dashboard_siswa({'id': 42, 'username':'siswa'}, ENROLL)
    assert 'Statistik tidak tersedia' in con.export_text()


def test_repo_memakai_id_login_readonly(monkeypatch):
    from app.repositories import student_dashboard_repo as repo
    calls=[]
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, params):
            calls.append((sql,params))
            assert sql.lstrip().startswith('SELECT')
        def fetchone(self): return STATS
        def fetchall(self): return JADWAL
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def cursor(self, **kwargs): return Cursor()
    monkeypatch.setattr(repo.pool,'connection',lambda **kw:Conn())
    assert repo.ringkasan_siswa(42)['kelas_aktif'] == 2
    assert len(repo.jadwal_mingguan_siswa(42)) == 2
    assert calls[0][1] == (42,)*6
    assert calls[1][1] == (42,)
    with pytest.raises(ValueError): repo.ringkasan_siswa('42')


def test_installer_tidak_merusak_file_lain_dan_idempoten(tmp_path):
    import importlib.util
    pkg = Path(__file__).parents[1]/'SIBIMA_PATCH_007C_DASHBOARD_SISWA_GRID'
    # Saat diuji di root yang sudah dipatch, resource installer berada di luar.
    if not pkg.exists():
        pkg = Path(__file__).resolve().parents[2]/'SIBIMA_PATCH_007C_DASHBOARD_SISWA_GRID'
    if not pkg.exists():
        pytest.skip('Payload installer tidak ada dalam lokasi test ini.')
    spec=importlib.util.spec_from_file_location('seed_installer_007c',pkg/'install_007c.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    src=(pkg/'old_dashboard_section.txt').read_text(encoding='utf-8')
    new=(pkg/'new_dashboard_section.txt').read_text(encoding='utf-8')
    base='from app.utils.formatters import rupiah\n'+src+'\n\ndef menu_katalog(pengguna):\n    pass\n'
    updated=mod.patch_student(base,src,new)
    assert updated.count('tampilkan_dashboard_siswa(pengguna, enrollments)') == 1
    assert mod.patch_student(updated,src,new)==updated
    with pytest.raises(RuntimeError): mod.patch_student(base.replace('def _dashboard(', 'def custom_dashboard('),src,new)
