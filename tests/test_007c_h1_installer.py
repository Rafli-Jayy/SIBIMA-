"""Installer adaptif harus mempertahankan dashboard asli dan menolak partial state."""
import ast
import importlib.util
from pathlib import Path
import pytest

HERE = Path(__file__).resolve()
PACKAGE = HERE.parents[2] if HERE.parents[2].name == 'SIBIMA_PATCH_007C_H1_DASHBOARD_SISWA_ADAPTIF' else HERE.parents[1] / 'SIBIMA_PATCH_007C_H1_DASHBOARD_SISWA_ADAPTIF'
if not PACKAGE.exists():
    pytest.skip('Berkas installer belum tersedia di root proyek', allow_module_level=True)

spec = importlib.util.spec_from_file_location('installer_007c_h1', PACKAGE / 'install_007c_h1.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

BASE = ("from app.utils.formatters import rupiah\n\n"
        "def _dashboard(pengguna, enrollments):\n"
        "    bersihkan_layar()\n"
        "    console.print('Dashboard lama')\n\n"
        "def jalankan():\n"
        "    _dashboard(pengguna, enrollments)\n")


def test_berbeda_isi_fungsi_tetap_aman():
    src = BASE.replace("console.print('Dashboard lama')", "console.print('Dashboard kustom')")
    result, mode = mod.patch_student(src)
    assert mode == 'siap dipasang'
    assert "console.print('Dashboard kustom')" in result
    assert result.count('def _dashboard(') == 1
    assert 'def _dashboard_legacy_007c(' in result
    assert 'tampilkan_dashboard_siswa(pengguna, enrollments)' in result
    ast.parse(result)


def test_pasangan_dashboard_lama_tersimpan_dan_idempoten():
    result, _ = mod.patch_student(BASE)
    again, status = mod.patch_student(result)
    assert again == result
    assert status == 'sudah terpasang'


def test_perubahan_parameter_ditolak():
    with pytest.raises(RuntimeError):
        mod.patch_student(BASE.replace('def _dashboard(pengguna, enrollments):',
                                       'def _dashboard(user, enrollments):'))


def test_tidak_ada_dashboard_ditolak():
    with pytest.raises(RuntimeError):
        mod.patch_student(BASE.replace('def _dashboard(', 'def _dashboard_custom('))


def test_partial_import_ditolak():
    with pytest.raises(RuntimeError):
        mod.patch_student(mod.IMPORT + BASE)


def test_kompatibel_dengan_source_versi_007c_lama():
    oldpkg = PACKAGE.parent / 'SIBIMA_PATCH_007C_DASHBOARD_SISWA_GRID'
    old = oldpkg/'old_dashboard_section.txt'
    if not old.exists():
        pytest.skip('Source patch 007C lama tidak tersedia')
    src = 'from app.utils.formatters import rupiah\n' + old.read_text(encoding='utf-8') + '\n' + 'def jalankan():\n    _dashboard(pengguna, enrollments)\n'
    result, _ = mod.patch_student(src)
    assert 'def _dashboard_legacy_007c' in result
    assert 'def jalankan():' in result


def test_crlf_masih_bisa_diproses():
    src = BASE.replace('\n', '\r\n')
    result, _ = mod.patch_student(src.replace('\r\n', '\n'))
    assert 'tampilkan_dashboard_siswa' in result


def test_tidak_menggunakan_sql_atau_akses_database():
    source = (PACKAGE/'install_007c_h1.py').read_text(encoding='utf-8')
    for forbidden in ('psycopg.connect(', 'DROP TABLE', 'DELETE FROM', 'UPDATE enrollments'):
        assert forbidden not in source
