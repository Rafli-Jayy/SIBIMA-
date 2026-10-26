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
            ("Catatan Materi", "materi"),
            ("Profil Saya", "profil"),
        ],
    )
