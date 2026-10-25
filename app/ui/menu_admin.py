"""Dashboard admin dan Pusat Konfirmasi akun SIBIMA."""

import psycopg
import questionary
from questionary import Choice, Separator, Style
from rich.align import Align
from rich.panel import Panel
from rich.table import Table

from app import session
from app.repositories import user_repo, enrollment_repo
from app.services import approval_service
from app.ui.console import (
    console,
    bersihkan_layar,
    gagal,
    info,
    peringatan,
    sukses,
)


TEMA_ADMIN = Style([
    ("qmark", "fg:#00ffff bold"),
    ("question", "fg:#ffffff bold"),
    ("answer", "fg:#00ffff bold"),
    ("pointer", "fg:#00ffff bold"),
    ("highlighted", "fg:#00ffff bold"),
    ("selected", "fg:#00ffff"),
    ("separator", "fg:#444444"),
    ("instruction", "fg:#888888 italic"),
])


MENU_ADMIN = [
    ("Pusat Konfirmasi", "konfirmasi"),
    ("Manajemen Akun", "akun"),
    ("Data Siswa", "siswa"),
    ("Data Tutor", "tutor"),
    ("Program dan Ruang", "program"),
    ("Jadwal", "jadwal"),
    ("Pembayaran", "pembayaran"),
    ("Laporan", "laporan"),
    ("Pengumuman", "pengumuman"),
    ("Log Aktivitas", "log"),
]


def _format_waktu(nilai):
    if nilai is None:
        return "-"
    try:
        return nilai.strftime("%d %b %Y %H:%M")
    except (AttributeError, ValueError):
        return str(nilai)


def _tampilkan_header(halaman: str, subtitle: str):
    console.print(
        Panel(
            Align.center(
                f"[bold cyan]S I B I M A[/bold cyan]\n"
                f"[bold white]{halaman.upper()}[/bold white]\n"
                f"[dim]{subtitle}[/dim]"
            ),
            border_style="cyan",
            padding=(1, 4),
            expand=True,
        )
    )


def _tampilkan_detail_akun(user: dict):
    tabel = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    tabel.add_column("Informasi", style="cyan", width=22)
    tabel.add_column("Nilai", style="white", overflow="fold")

    tabel.add_row("ID pengguna", str(user.get("id", "-")))
    tabel.add_row("Nama lengkap", str(user.get("nama_lengkap") or "-"))
    tabel.add_row("Username", str(user.get("username") or "-"))
    tabel.add_row("Email", str(user.get("email") or "-"))
    tabel.add_row("Role", str(user.get("role") or "-").upper())
    tabel.add_row(
        "Email terverifikasi",
        "Ya" if user.get("email_verified") else "Tidak",
    )
    tabel.add_row("Status akun", str(user.get("status") or "-"))
    tabel.add_row("Didaftarkan", _format_waktu(user.get("created_at")))

    console.print(
        Panel(
            tabel,
            title="[bold cyan]DETAIL PENDAFTAR[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
            expand=True,
        )
    )


def _daftar_akun_menunggu():
    """Ambil akun non-admin yang menunggu keputusan admin."""
    return [
        user
        for user in user_repo.daftar_by_status("menunggu_konfirmasi")
        if user.get("role") in {"siswa", "tutor"}
    ]


def _tampilkan_daftar_akun(daftar: list[dict]):
    tabel = Table(
        title="Akun Menunggu Persetujuan",
        header_style="bold cyan",
        border_style="blue",
        expand=True,
    )
    tabel.add_column("ID", justify="right", no_wrap=True)
    tabel.add_column("Role", no_wrap=True)
    tabel.add_column("Nama", min_width=15)
    tabel.add_column("Username", min_width=10)
    tabel.add_column("Email terverifikasi", justify="center")
    tabel.add_column("Tanggal daftar", no_wrap=True)

    for user in daftar:
        tabel.add_row(
            str(user.get("id", "-")),
            str(user.get("role", "-")).upper(),
            str(user.get("nama_lengkap") or "-"),
            str(user.get("username") or "-"),
            "[green]Ya[/green]" if user.get("email_verified") else "[red]Tidak[/red]",
            _format_waktu(user.get("created_at")),
        )

    console.print(tabel)


def _proses_aksi_akun(user: dict):
    """Tampilkan detail lalu minta konfirmasi sebelum mengubah status."""
    while session.punya_role("admin"):
        bersihkan_layar()
        _tampilkan_header("Pusat Konfirmasi", "PENDAFTARAN AKUN SISWA DAN TUTOR")
        _tampilkan_detail_akun(user)

        if not user.get("email_verified"):
            peringatan(
                "Email akun ini belum terverifikasi. Persetujuan akan ditolak "
                "oleh service sampai verifikasi selesai."
            )

        aksi = questionary.select(
            "Tindakan untuk akun ini:",
            choices=[
                Choice("✓  Setujui akun", value="setujui"),
                Choice("✕  Tolak akun", value="tolak"),
                Separator("────────────────────────"),
                Choice("↩  Kembali ke daftar", value="kembali"),
            ],
            style=TEMA_ADMIN,
            qmark="⚡",
            pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()

        if aksi is None or aksi == "kembali":
            return

        if aksi == "setujui":
            yakin = questionary.confirm(
                f"Setujui akun {user.get('username')}?",
                default=False,
                style=TEMA_ADMIN,
            ).ask()

            if yakin is not True:
                info("Persetujuan dibatalkan; tidak ada perubahan.")
                input("Tekan Enter untuk kembali ke detail...")
                continue

            berhasil, pesan = approval_service.setujui_akun(user["id"])

        else:
            alasan = questionary.text(
                "Alasan penolakan (wajib diisi):",
                style=TEMA_ADMIN,
                qmark="📝",
            ).ask()

            if alasan is None:
                peringatan("Penolakan dibatalkan; tidak ada perubahan.")
                input("Tekan Enter untuk kembali ke detail...")
                continue

            alasan = alasan.strip()
            if not alasan:
                gagal("Alasan penolakan wajib diisi.")
                input("Tekan Enter untuk kembali ke detail...")
                continue

            yakin = questionary.confirm(
                f"Tolak akun {user.get('username')} dengan alasan tersebut?",
                default=False,
                style=TEMA_ADMIN,
            ).ask()

            if yakin is not True:
                info("Penolakan dibatalkan; tidak ada perubahan.")
                input("Tekan Enter untuk kembali ke detail...")
                continue

            berhasil, pesan = approval_service.tolak_akun(
                user["id"], alasan
            )

        if berhasil:
            sukses(pesan)
        else:
            gagal(pesan)

        input("Tekan Enter untuk kembali ke daftar akun...")
        return


def _menu_konfirmasi_akun():
    """Antrean akun siswa/tutor untuk disetujui atau ditolak."""
    while session.punya_role("admin"):
        bersihkan_layar()
        _tampilkan_header(
            "Pusat Konfirmasi",
            "ANTREAN AKUN SISWA DAN TUTOR",
        )
        console.print(
            Panel(
                "[white]Pilih pendaftar untuk melihat detail, lalu setujui "
                "atau tolak dengan alasan.[/white]\n\n"
                "[dim]Pada antrean ini hanya akun siswa/tutor yang diproses. Email wajib "
                "sudah terverifikasi sebelum akun disetujui.[/dim]",
                border_style="blue",
                padding=(1, 2),
                expand=True,
            )
        )

        try:
            daftar = _daftar_akun_menunggu()
        except psycopg.Error as exc:
            gagal("Gagal membaca antrean akun dari database.")
            info(f"Jenis error: {type(exc).__name__}")
            input("Tekan Enter untuk kembali...")
            return

        if daftar:
            _tampilkan_daftar_akun(daftar)
            pilihan_akun = [
                Choice(
                    title=(
                        f"ID {user['id']}  •  {user['role'].upper()}  •  "
                        f"{user['nama_lengkap']} (@{user['username']})"
                    ),
                    value=user["id"],
                )
                for user in daftar
            ]
            pilihan_akun.extend([
                Separator("────────────────────────"),
                Choice("↻  Muat ulang daftar", value="refresh"),
                Choice("↩  Kembali ke jenis konfirmasi", value="kembali"),
            ])
        else:
            console.print(
                Panel(
                    "[bold green]Tidak ada akun yang menunggu persetujuan.[/bold green]\n"
                    "[dim]Daftar ini akan diperbarui ketika ada pendaftar baru "
                    "yang menyelesaikan verifikasi email.[/dim]",
                    border_style="green",
                    padding=(1, 2),
                    expand=True,
                )
            )
            pilihan_akun = [
                Choice("↻  Muat ulang daftar", value="refresh"),
                Choice("↩  Kembali ke dashboard", value="kembali"),
            ]

        pilihan = questionary.select(
            "Pilih akun atau tindakan:",
            choices=pilihan_akun,
            style=TEMA_ADMIN,
            qmark="⚡",
            pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()

        if pilihan is None or pilihan == "kembali":
            return

        if pilihan == "refresh":
            continue

        user = next((u for u in daftar if u["id"] == pilihan), None)
        if user is None:
            peringatan("Akun tidak ditemukan pada daftar terbaru. Muat ulang.")
            input("Tekan Enter untuk melanjutkan...")
            continue

        _proses_aksi_akun(user)



def _format_rupiah(nilai) -> str:
    try:
        return "Rp " + f"{nilai:,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(nilai)


def _tampilkan_daftar_enrollment(daftar: list[dict]):
    tabel = Table(
        title="Pendaftaran Program Menunggu Persetujuan",
        header_style="bold cyan",
        border_style="blue",
        expand=True,
    )
    tabel.add_column("ID", justify="right", no_wrap=True)
    tabel.add_column("Nama Siswa", min_width=15)
    tabel.add_column("Username", min_width=10)
    tabel.add_column("Program", min_width=16)
    tabel.add_column("Jenjang", no_wrap=True)
    tabel.add_column("Biaya/Bulan", justify="right", no_wrap=True)
    tabel.add_column("Didaftarkan", no_wrap=True)

    for item in daftar:
        tabel.add_row(
            str(item.get("enrollment_id", "-")),
            str(item.get("nama_siswa") or "-"),
            str(item.get("username") or "-"),
            f"{item.get('nama_program', '-')} ({item.get('kode_program', '-')})",
            str(item.get("jenjang") or "-"),
            _format_rupiah(item.get("harga_bulanan", 0)),
            _format_waktu(item.get("created_at")),
        )
    console.print(tabel)


def _tampilkan_detail_enrollment(item: dict):
    tabel = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    tabel.add_column("Informasi", style="cyan", width=22)
    tabel.add_column("Nilai", style="white", overflow="fold")
    tabel.add_row("ID pendaftaran", str(item.get("enrollment_id", "-")))
    tabel.add_row("ID siswa", str(item.get("student_id", "-")))
    tabel.add_row("Nama siswa", str(item.get("nama_siswa") or "-"))
    tabel.add_row("Username", str(item.get("username") or "-"))
    tabel.add_row("Email", str(item.get("email") or "-"))
    tabel.add_row("NIS", str(item.get("nis") or "Belum tersedia"))
    tabel.add_row("Program", str(item.get("nama_program") or "-"))
    tabel.add_row("Kode program", str(item.get("kode_program") or "-"))
    tabel.add_row("Jenjang", str(item.get("jenjang") or "-"))
    tabel.add_row("Biaya per bulan", _format_rupiah(item.get("harga_bulanan", 0)))
    tabel.add_row("Status", str(item.get("status") or "-"))
    tabel.add_row("Tanggal daftar", _format_waktu(item.get("created_at")))
    console.print(
        Panel(
            tabel,
            title="[bold cyan]DETAIL PENDAFTARAN PROGRAM[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
            expand=True,
        )
    )


def _proses_aksi_enrollment(item: dict):
    """Tampilkan detail pendaftaran lalu proses aksi admin yang dipilih."""
    while session.punya_role("admin"):
        bersihkan_layar()
        _tampilkan_header(
            "Pusat Konfirmasi",
            "PENDAFTARAN PROGRAM SISWA",
        )
        _tampilkan_detail_enrollment(item)
        console.print(
            Panel(
                "[white]Jika disetujui, enrollment diaktifkan dan tagihan "
                "pertama dibuat dalam transaksi database yang sama.[/white]\n"
                "[dim]Periode tagihan adalah bulan saat persetujuan. Jatuh tempo "
                "awal adalah 7 hari kalender setelah persetujuan. Program gratis "
                "tidak membuat invoice bernilai nol.[/dim]",
                border_style="blue",
                padding=(1, 2),
                expand=True,
            )
        )

        aksi = questionary.select(
            "Tindakan untuk pendaftaran ini:",
            choices=[
                Choice("✓  Setujui pendaftaran + buat tagihan pertama", value="setujui"),
                Choice("✕  Tolak pendaftaran", value="tolak"),
                Separator("────────────────────────"),
                Choice("↩  Kembali ke daftar", value="kembali"),
            ],
            style=TEMA_ADMIN,
            qmark="⚡",
            pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()

        if aksi is None or aksi == "kembali":
            return

        if aksi == "setujui":
            yakin = questionary.confirm(
                f"Setujui pendaftaran {item.get('nama_program')} untuk "
                f"{item.get('nama_siswa')} dan buat tagihan pertama?",
                default=False,
                style=TEMA_ADMIN,
            ).ask()
            if yakin is not True:
                info("Persetujuan dibatalkan; tidak ada perubahan.")
                input("Tekan Enter untuk kembali ke detail...")
                continue

            berhasil, pesan = approval_service.setujui_enrollment(
                item["enrollment_id"]
            )
        else:
            alasan = questionary.text(
                "Alasan penolakan (wajib diisi):",
                style=TEMA_ADMIN,
                qmark="📝",
            ).ask()
            if alasan is None:
                peringatan("Penolakan dibatalkan; tidak ada perubahan.")
                input("Tekan Enter untuk kembali ke detail...")
                continue
            alasan = alasan.strip()
            if not alasan:
                gagal("Alasan penolakan wajib diisi.")
                input("Tekan Enter untuk kembali ke detail...")
                continue
            yakin = questionary.confirm(
                f"Tolak pendaftaran {item.get('nama_program')} untuk "
                f"{item.get('nama_siswa')} dengan alasan tersebut?",
                default=False,
                style=TEMA_ADMIN,
            ).ask()
            if yakin is not True:
                info("Penolakan dibatalkan; tidak ada perubahan.")
                input("Tekan Enter untuk kembali ke detail...")
                continue
            berhasil, pesan = approval_service.tolak_enrollment(
                item["enrollment_id"], alasan
            )

        if berhasil:
            sukses(pesan)
        else:
            gagal(pesan)
        input("Tekan Enter untuk kembali ke daftar pendaftaran...")
        return


def _menu_konfirmasi_enrollment():
    """Antrean enrollment yang menunggu persetujuan admin."""
    while session.punya_role("admin"):
        bersihkan_layar()
        _tampilkan_header(
            "Pusat Konfirmasi",
            "ANTREAN PENDAFTARAN PROGRAM",
        )
        console.print(
            Panel(
                "[white]Pilih pendaftaran siswa untuk melihat detail, lalu "
                "setujui atau tolak dengan alasan.[/white]\n\n"
                "[dim]Persetujuan mengaktifkan enrollment dan membuat tagihan "
                "pertama secara atomik jika program berbayar. Tagihan awal "
                "jatuh tempo 7 hari setelah persetujuan.[/dim]",
                border_style="blue",
                padding=(1, 2),
                expand=True,
            )
        )
        try:
            daftar = enrollment_repo.daftar_menunggu()
        except psycopg.Error as exc:
            gagal("Gagal membaca antrean pendaftaran program dari database.")
            info(f"Jenis error: {type(exc).__name__}")
            input("Tekan Enter untuk kembali...")
            return

        if daftar:
            _tampilkan_daftar_enrollment(daftar)
            pilihan_daftar = [
                Choice(
                    title=(
                        f"ID {item['enrollment_id']} • {item['nama_siswa']} • "
                        f"{item['nama_program']}"
                    ),
                    value=item["enrollment_id"],
                )
                for item in daftar
            ]
        else:
            console.print(
                Panel(
                    "[bold green]Tidak ada pendaftaran program yang menunggu.[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                    expand=True,
                )
            )
            pilihan_daftar = []

        pilihan_daftar.extend([
            Separator("────────────────────────"),
            Choice("↻  Muat ulang daftar", value="refresh"),
            Choice("↩  Kembali ke jenis konfirmasi", value="kembali"),
        ])
        pilihan = questionary.select(
            "Pilih pendaftaran atau tindakan:",
            choices=pilihan_daftar,
            style=TEMA_ADMIN,
            qmark="⚡",
            pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()

        if pilihan is None or pilihan == "kembali":
            return
        if pilihan == "refresh":
            continue

        item = next(
            (x for x in daftar if x["enrollment_id"] == pilihan),
            None,
        )
        if item is None:
            peringatan("Pendaftaran tidak ditemukan pada daftar terbaru. Muat ulang.")
            input("Tekan Enter untuk melanjutkan...")
            continue
        _proses_aksi_enrollment(item)


def menu_konfirmasi():
    """Pilih antrean konfirmasi akun atau pendaftaran program."""
    while session.punya_role("admin"):
        bersihkan_layar()
        _tampilkan_header("Pusat Konfirmasi", "PILIH JENIS ANTREAN")
        pilihan = questionary.select(
            "Antrean yang ingin diproses:",
            choices=[
                Choice("Akun siswa/tutor", value="akun"),
                Choice("Pendaftaran program bimbel", value="enrollment"),
                Separator("────────────────────────"),
                Choice("Kembali ke dashboard", value="kembali"),
            ],
            style=TEMA_ADMIN,
            qmark="⚡",
            pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()
        if pilihan is None or pilihan == "kembali":
            return
        if pilihan == "akun":
            _menu_konfirmasi_akun()
        elif pilihan == "enrollment":
            _menu_konfirmasi_enrollment()

def _tampilkan_modul_belum_tersedia(nama_modul: str):
    bersihkan_layar()
    _tampilkan_header("Modul Admin", nama_modul)
    console.print(
        Panel(
            f"[bold yellow]{nama_modul}[/bold yellow]\n\n"
            "[white]Modul ini masih dalam tahap pengembangan.[/white]\n"
            "[dim]Belum ada operasi bisnis yang dijalankan dari halaman ini.[/dim]",
            border_style="yellow",
            padding=(1, 3),
            expand=True,
        )
    )
    input("Tekan Enter untuk kembali ke dashboard...")


def jalankan():
    """Dashboard admin SIBIMA."""
    while True:
        if not session.punya_role("admin"):
            peringatan("Akses dashboard ditolak. Silakan login sebagai admin.")
            return

        bersihkan_layar()
        pengguna = session.get_user() or {}
        nama = pengguna.get("nama_lengkap") or pengguna.get("username") or "Admin"

        console.print(
            Panel(
                Align.center(
                    "[bold cyan]S I B I M A[/bold cyan]\n"
                    "[bold white]PUSAT KENDALI ADMINISTRATOR[/bold white]"
                ),
                border_style="cyan",
                padding=(1, 4),
                expand=True,
            )
        )
        console.print(
            Panel(
                f"[bold white]Selamat datang, [cyan]{nama}[/cyan]![/bold white]\n"
                "[dim]ROLE: ADMIN  •  SESI AKTIF[/dim]\n\n"
                "[white]Pilih modul yang ingin dibuka.[/white]\n"
                "[dim]Pusat Konfirmasi akun dan pendaftaran program sudah terhubung. "
                "Modul lain dikembangkan bertahap.[/dim]",
                title="[bold cyan]DASHBOARD[/bold cyan]",
                border_style="bright_blue",
                padding=(1, 2),
                expand=True,
            )
        )

        pilihan_menu = [
            Choice(f"  {label}", value=kode)
            for label, kode in MENU_ADMIN
        ]
        pilihan_menu.extend([
            Separator("────────────────────────"),
            Choice("  🚪 Logout", value="logout"),
        ])

        pilihan = questionary.select(
            "Pilih modul:",
            choices=pilihan_menu,
            style=TEMA_ADMIN,
            qmark="⚡",
            pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()

        if pilihan is None or pilihan == "logout":
            session.logout()
            sukses("Logout berhasil. Sesi telah ditutup.")
            return

        if pilihan == "konfirmasi":
            menu_konfirmasi()
            continue

        label = next(
            (teks for teks, kode in MENU_ADMIN if kode == pilihan),
            pilihan,
        )
        _tampilkan_modul_belum_tersedia(label)
