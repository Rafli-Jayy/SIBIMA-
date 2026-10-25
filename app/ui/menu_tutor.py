"""Menu dan layar untuk role tutor.

Fungsi yang direncanakan:
    - jalankan()
    - menu_jadwal
    - menu_absensi
    - menu_nilai
    - menu_kuis
"""
"""Dashboard dan navigasi awal tutor SIBIMA."""

from app.ui.console import jalankan_menu_role


def jalankan():
    jalankan_menu_role(
        role="tutor",
        judul_halaman="S I B I M A",
        subtitle="DASHBOARD TUTOR",
        fitur=[
            ("Jadwal Mengajar", "jadwal"),
            ("Kelas dan Siswa", "kelas"),
            ("Absensi", "absensi"),
            ("Nilai Siswa", "nilai"),
            ("Kuis", "kuis"),
            ("Umpan Balik Siswa", "umpan_balik"),
            ("Honor dan Riwayat", "honor"),
            ("Profil Saya", "profil"),
        ],
    )