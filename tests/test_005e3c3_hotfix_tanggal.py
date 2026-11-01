"""Regresi PATCH-005E3-C3-H1: tanggal sesi tidak mendahului enrollment.

Tidak melakukan koneksi ke database asli. Memakai SQLite tiruan yang disediakan
oleh test regresi C3 untuk mengeksekusi query student_repo.rekap_absensi.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDENT = (ROOT / 'app/repositories/student_repo.py').read_text(encoding='utf-8')


def _load_c3_tests():
    path = ROOT / 'tests/test_005e3c3_rekap_enrollment.py'
    spec = importlib.util.spec_from_file_location('sibima_c3_runtime_h1', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rekap_membatasi_tanggal_dan_enrollment():
    start = STUDENT.index('def rekap_absensi(')
    end = STUDENT.index('def daftar_absensi(', start)
    query = STUDENT[start:end]
    assert 'a.enrollment_id = e.id' in query
    assert "cs.status = 'selesai'" in query
    assert 'cs.tanggal >= e.created_at::date' in query


def test_absensi_sesi_sebelum_daftar_tidak_dihitung_meski_salah_terkait():
    c3 = _load_c3_tests()
    db = c3.setup_db()
    try:
        # Simulasi data buruk: sesi lama (Februari) dihubungkan ke enrollment
        # baru (Oktober). Ini tidak boleh terhitung dalam rekap periode baru.
        db.execute('UPDATE attendances SET enrollment_id = 27 WHERE session_id = 1')
        rows = c3.compiled_student('rekap_absensi', db)(41, 11)
        assert len(rows) == 1
        assert rows[0]['enrollment_id'] == 27
        assert rows[0]['total_pertemuan'] == 1
        assert (rows[0]['hadir'], rows[0]['izin'], rows[0]['sakit'], rows[0]['alpa']) == (1, 0, 0, 0)
    finally:
        db.close()
