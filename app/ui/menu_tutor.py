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
from app.ui import menu_tutor_academic

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
    ("Jadwal Mengajar", "jadwal"),
    ("Kelas dan Siswa", "kelas"),
    ("Absensi", "absensi"),
    ("Nilai", "nilai"),
    ("Catatan Materi", "materi"),
]
_MENU_AKUN = [("Profil Saya", "profil")]


def _dashboard(pengguna):
    """Render dashboard yang ringkas, tanpa statistik rekaan."""
    nama = pengguna.get("nama_lengkap") or pengguna.get("username") or "Tutor"
    username = pengguna.get("username") or "-"

    brand = Text()
    brand.append("S I B I M A\n", style="bold cyan")
    brand.append("PORTAL TUTOR\n", style="bold white")
    brand.append(f"Selamat datang, {nama}  •  @{username}\n", style="white")
    brand.append("JADWAL  •  KELAS  •  ABSENSI  •  NILAI  •  MATERI  •  PROFIL", style="dim")
    console.print(Panel(
        Align.center(brand),
        border_style="cyan", box=ROUNDED, padding=(1, 3), expand=True,
    ))

    kategori = Table.grid(expand=True, padding=(0, 1))
    kategori.add_column(ratio=1)
    kategori.add_column(ratio=1)
    kategori.add_row(
        Panel(
            "Jadwal Mengajar\nKelas dan Siswa\nAbsensi",
            title="[bold cyan]PENGELOLAAN KELAS[/bold cyan]",
            border_style="cyan", box=ROUNDED, padding=(0, 2), expand=True,
        ),
        Panel(
            "Nilai  •  Catatan Materi\nProfil Saya",
            title="[bold cyan]AKADEMIK & AKUN[/bold cyan]",
            border_style="cyan", box=ROUNDED, padding=(0, 2), expand=True,
        ),
    )
    console.print(kategori)
    console.print("[dim]Navigasi: ↑/↓ pilih • Enter buka • Ctrl+C batalkan prompt[/dim]")


def jalankan():
    while True:
        pengguna = session.get_user()
        if not pengguna or pengguna.get("role") != "tutor":
            gagal("Akses ditolak. Silakan login menggunakan akun tutor.")
            return

        bersihkan_layar()
        _dashboard(pengguna)

        choices = [Separator("────────── AKADEMIK ──────────")]
        choices.extend(
            Choice(f"  {index:02d}  {label}", value=kode)
            for index, (label, kode) in enumerate(_MENU_AKADEMIK, start=1)
        )
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

        menu_tutor_academic.jalankan_modul(pilihan)
