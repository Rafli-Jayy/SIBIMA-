"""Dashboard dan navigasi Tutor dengan layout konsisten bersama Admin."""

import questionary
from questionary import Choice, Separator, Style
from rich.align import Align
from rich.box import ROUNDED
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app import session
from app.ui.console import console, bersihkan_layar, gagal, sukses
from app.ui.tutor_dashboard_grid import tampilkan_dashboard_tutor
from app.ui import menu_tutor_academic, menu_notifikasi
from app.services import engagement_service

_GAYA = Style([
    ("qmark", "fg:#00ffff bold"),
    ("question", "fg:#ffffff bold"),
    ("answer", "fg:#00ffff bold"),
    ("pointer", "fg:#00ffff bold"),
    ("highlighted", "fg:#00ffff bold"),
    ("selected", "fg:#00ffff"),
    ("separator", "fg:#526477"),
    ("instruction", "fg:#91a4b7 italic"),
])

_MENU_AKADEMIK = [
    ("Jadwal & Detail Kelas", "jadwal"),
    ("Kelas dan Siswa", "kelas"),
    ("Absensi", "absensi"),
    ("Nilai", "nilai"),
    ("Catatan Materi", "materi"),
]
_MENU_AKUN = [("Profil Saya", "profil")]


def _dashboard(pengguna):
    """Tampilkan informasi jadwal dan aktivitas Tutor dari database (PATCH-007B)."""
    tampilkan_dashboard_tutor(pengguna)

def jalankan():
    while True:
        pengguna = session.get_user()
        if not pengguna or pengguna.get("role") != "tutor":
            gagal("Akses ditolak. Silakan login menggunakan akun tutor.")
            return

        bersihkan_layar()
        _dashboard(pengguna)

        try:
            jumlah_belum_dibaca = engagement_service.jumlah_notifikasi_belum_dibaca("tutor")
        except Exception:
            jumlah_belum_dibaca = 0
        label_notifikasi = (
            f"  🔔  Notifikasi ({jumlah_belum_dibaca} belum dibaca)"
            if jumlah_belum_dibaca > 0 else "  🔔  Notifikasi"
        )

        choices = [Separator("────────── AKADEMIK ──────────")]
        choices.extend(
            Choice(f"  {index:02d}  {label}", value=kode)
            for index, (label, kode) in enumerate(_MENU_AKADEMIK, start=1)
        )
        choices.append(Choice(label_notifikasi, value="notifikasi"))
        choices.append(Separator("────────── AKUN ──────────────"))
        choices.extend(
            Choice(f"  {index:02d}  {label}", value=kode)
            for index, (label, kode) in enumerate(_MENU_AKUN, start=len(_MENU_AKADEMIK) + 1)
        )
        choices.extend([
            Separator("─────────────────────────────"),
            Choice("  00  Logout", value="logout"),
        ])

        pilihan = questionary.select(
            "MENU TUTOR  •  Pilih modul:",
            choices=choices,
            style=_GAYA,
            qmark="⚡",
            pointer="▶",
            instruction=" (↑/↓ navigasi • Enter pilih)",
        ).ask()
        if pilihan is None or pilihan == "logout":
            session.logout()
            bersihkan_layar()
            sukses("Logout berhasil. Sesi telah ditutup.")
            input("\nTekan Enter untuk kembali ke menu utama...")
            return

        if pilihan == "notifikasi":
            menu_notifikasi.jalankan("tutor")
        else:
            menu_tutor_academic.jalankan_modul(pilihan)
