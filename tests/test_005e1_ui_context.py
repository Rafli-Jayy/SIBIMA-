"""PATCH-005E1: jadwal rutin, informasi kosong, dan SQL akademik read-only.

Tes ini tidak memakai database pengguna; validasi end-to-end tetap perlu di PC.
"""
from datetime import date, time
from pathlib import Path

import pytest

from app.ui.jadwal_context import (
    label_hari, label_jam, jam_jadwal, kondisi_jadwal_siswa,
    jadwal_rutin_terdekat,
)

ROOT = Path(__file__).resolve().parent.parent


def _kelas(status="aktif", locked=False):
    return {"status": status, "akses_terkunci": locked, "program_id": 7}


def _jadwal(hari="selasa"):
    return {"hari": hari, "jam_mulai": time(16, 0), "jam_selesai": time(17, 30),
            "program_id": 7, "nama_program": "Matematika SMA"}


@pytest.mark.parametrize("kelas,jadwal,hari,expected", [
    ([], [], "senin", "belum_ada_kelas"),
    ([_kelas("menunggu")], [], "senin", "belum_ada_kelas"),
    ([_kelas("menunggu_pembayaran")], [], "senin", "belum_ada_kelas"),
    ([_kelas(locked=True)], [], "senin", "terkunci_tagihan"),
    ([_kelas()], [], "senin", "belum_dijadwalkan"),
    ([_kelas()], [_jadwal("selasa")], "senin", "tidak_ada_hari_ini"),
    ([_kelas()], [_jadwal("selasa")], "selasa", "ada_jadwal"),
    ([_kelas()], [_jadwal("selasa")], None, "ada_jadwal"),
    ([_kelas(locked=True), _kelas()], [_jadwal()], "selasa", "ada_jadwal"),
    ([_kelas("batal")], [], "senin", "belum_ada_kelas"),
])
def test_kondisi_tidak_mencampur_tiga_keadaan_kosong(kelas, jadwal, hari, expected):
    assert kondisi_jadwal_siswa(kelas, jadwal, hari) == expected


def test_format_waktu_objek_database():
    assert label_jam(time(8, 5)) == "08:05"
    assert jam_jadwal(_jadwal()) == "16:00–17:30"
    assert label_hari("selasa") == "Selasa"


def test_format_waktu_string_dan_null():
    assert label_jam("09:45:00") == "09:45"
    assert label_jam(None) == "—"
    assert label_hari(None) == "—"


def test_jadwal_terdekat_menghitung_hari_tanpa_membuat_sesi():
    # Senin 2026-11-02 -> Selasa 2026-11-03
    result = jadwal_rutin_terdekat([_jadwal()], date(2026, 11, 2))
    assert result[0] == date(2026, 11, 3)
    assert result[1]["nama_program"] == "Matematika SMA"


def test_jadwal_terdekat_tetap_menggunakan_jadwal_rutin():
    # Sesuai desain: jika hari ini sama, ini hanya perkiraan pola rutin
    result = jadwal_rutin_terdekat([_jadwal()], date(2026, 11, 3))
    assert result[0] == date(2026, 11, 3)


def test_jadwal_terdekat_memilih_urutan_jam():
    first = _jadwal("selasa")
    second = _jadwal("selasa")
    first["jam_mulai"] = time(17, 0)
    second["jam_mulai"] = time(7, 0)
    result = jadwal_rutin_terdekat([first, second], date(2026, 11, 2))
    assert result[1] is second


def test_jadwal_tidak_ada_atau_hari_tidak_valid():
    assert jadwal_rutin_terdekat([]) is None
    assert jadwal_rutin_terdekat([_jadwal("tidak_valid")]) is None


def test_daftar_sesi_siswa_dibatasi_enrollment_dan_h3():
    source = (ROOT / "app/repositories/student_repo.py").read_text(encoding="utf-8")
    section = source.split("def daftar_pertemuan_siswa(", 1)[1].split("def rekap_absensi(", 1)[0]
    assert "e.student_id = %s" in section
    assert "e.program_id = %s" in section
    assert "e.status = 'aktif'" in section
    assert "ENROLLMENT_TERAKHIR_TERSEDIA_SQL" in section
    assert "AKSES_TERKUNCI_SQL" in section
    assert "cs.tanggal >= e.created_at::date" in section
    assert "LEFT JOIN attendances" in section
    assert "INSERT" not in section.upper() and "UPDATE" not in section.upper()


def test_daftar_sesi_tutor_dibatasi_jadwal_dan_pemilik():
    source = (ROOT / "app/repositories/academic_repo.py").read_text(encoding="utf-8")
    section = source.split("def daftar_pertemuan_jadwal_tutor(", 1)[1].split("def buka_pertemuan(", 1)[0]
    assert "s.id = %s AND s.tutor_id = %s" in section
    assert "INSERT" not in section.upper() and "UPDATE" not in section.upper()


def test_menu_siswa_tidak_anggap_sesi_otomatis_selesai():
    source = (ROOT / "app/ui/menu_siswa_academic.py").read_text(encoding="utf-8")
    assert "Catatan sesi tersedia" in source
    assert "Belum dicatat tutor" in source
    assert "Dibatalkan" in source
    assert "Jadwal rutin bukan bukti" in source


def test_menu_admin_menjelaskan_peserta_program():
    source = (ROOT / "app/ui/menu_admin.py").read_text(encoding="utf-8")
    assert "Peserta dihitung per program, bukan per jadwal" in source
    assert "Sesi tercatat tidak menjamin absensi lengkap" in source



def test_dashboard_siswa_tidak_menduplikasi_panel_pembayaran():
    from io import StringIO
    from rich.console import Console
    from app.ui.student_dashboard_grid import render_dashboard_siswa

    pengguna = {
        "id": 1,
        "username": "siswa_uji",
        "nama_lengkap": "Siswa Uji",
    }

    enrollments = [
        {
            "nama_program": "Matematika",
            "status": "menunggu_pembayaran",
        }
    ]

    stats = {
        "kelas_aktif": 0,
        "pertemuan_hadir": 0,
        "rata_nilai_tercatat": None,
        "tagihan_belum_lunas": 1,
        "jumlah_tagihan": 100000,
        "tagihan_terlambat": 0,
    }

    output = StringIO()
    console = Console(
        file=output,
        width=140,
        color_system=None,
        force_terminal=False,
    )

    dashboard = render_dashboard_siswa(
        pengguna,
        enrollments,
        stats,
        [],
        width=140,
    )

    console.print(dashboard)
    hasil = output.getvalue()

    assert hasil.count("PERLU PERHATIAN") == 1
    assert hasil.count(
        "1 pendaftaran menunggu pembayaran pertama."
    ) == 1

