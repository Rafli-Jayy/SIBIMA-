"""Dashboard admin dan Pusat Konfirmasi akun SIBIMA."""

import psycopg
import questionary
from questionary import Choice, Separator, Style
from rich.align import Align
from rich.panel import Panel
from rich.table import Table

from app import session
from app.repositories import user_repo, enrollment_repo, program_repo
from app.services import approval_service, program_service, admin_enrollment_service, schedule_service
from app.ui import (
    menu_admin_data, menu_pembayaran, menu_admin_laporan, menu_admin_komunikasi,
)
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
    ("Pendaftaran", "pendaftaran"),
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


def _paket_menunggu_siswa(user_id: int):
    """Ambil paket yang masih menunggu untuk satu calon siswa."""
    try:
        riwayat = enrollment_repo.enrollment_siswa(user_id)
    except psycopg.Error:
        return None
    return [item for item in riwayat if item.get("status") == "menunggu"]


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

    if user.get("role") == "siswa":
        paket_menunggu = _paket_menunggu_siswa(user["id"])
        if paket_menunggu is None:
            peringatan("Detail pilihan paket belum dapat dibaca dari database.")
        elif not paket_menunggu:
            console.print(
                Panel(
                    "Siswa belum memilih paket bimbel. Akun tetap dapat disetujui "
                    "dan NIS akan diterbitkan. Siswa dapat memilih program setelah "
                    "akun aktif.",
                    title="[bold cyan]BELUM ADA PENDAFTARAN PROGRAM[/bold cyan]",
                    border_style="cyan",
                    padding=(1, 2),
                    expand=True,
                )
            )
        else:
            tabel_paket = Table(
                title="Pendaftaran program yang menunggu keputusan terpisah",
                header_style="bold cyan",
                expand=True,
            )
            tabel_paket.add_column("Program")
            tabel_paket.add_column("Kode")
            tabel_paket.add_column("Jenjang")
            tabel_paket.add_column("Biaya/bulan", justify="right")
            for paket in paket_menunggu:
                tabel_paket.add_row(
                    str(paket.get("nama_program") or "-"),
                    str(paket.get("kode_program") or "-"),
                    str(paket.get("jenjang") or "-"),
                    _format_rupiah(paket.get("harga_bulanan", 0)),
                )
            console.print(tabel_paket)
            console.print(
                Panel(
                    "Persetujuan akun hanya mengaktifkan akun dan menerbitkan NIS. "
                    "Pendaftaran program tetap menunggu keputusan pada antrean "
                    "Pendaftaran Program; tagihan baru dibuat saat program disetujui.",
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

        opsi_aksi = [
            Choice(
                "✓  Setujui akun dan terbitkan NIS"
                if user.get("role") == "siswa"
                else "✓  Setujui akun dan terbitkan kode tutor",
                value="setujui",
            ),
            Choice("✕  Tolak akun", value="tolak"),
            Separator("────────────────────────"),
            Choice("↩  Kembali ke daftar", value="kembali"),
        ]

        aksi = questionary.select(
            "Tindakan untuk akun ini:",
            choices=opsi_aksi,
            style=TEMA_ADMIN,
            qmark="⚡",
            pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()

        if aksi is None or aksi == "kembali":
            return

        if aksi == "setujui":
            deskripsi_aksi = (
                "akun siswa dan penerbitan NIS"
                if user.get("role") == "siswa"
                else "akun tutor dan penerbitan kode tutor"
            )
            yakin = questionary.confirm(
                f"Setujui {deskripsi_aksi} untuk {user.get('username')}?",
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
                "[dim]Persetujuan akun siswa dan tutor adalah keputusan tersendiri. "
                "Persetujuan akun siswa menerbitkan NIS; pendaftaran program tetap "
                "menunggu antrean konfirmasi program. Tagihan pertama dibuat setelah "
                "pendaftaran program disetujui. Email harus sudah terverifikasi.[/dim]",
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
    """Pilih antrean akun, pendaftaran program, atau pembayaran."""
    while session.punya_role("admin"):
        bersihkan_layar()
        _tampilkan_header("Pusat Konfirmasi", "PILIH JENIS ANTREAN")
        pilihan = questionary.select(
            "Antrean yang ingin diproses:",
            choices=[
                Choice("Akun siswa/tutor", value="akun"),
                Choice("Pendaftaran program bimbel", value="enrollment"),
                Choice("Konfirmasi pembayaran", value="pembayaran"),
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
        elif pilihan == "pembayaran":
            menu_pembayaran.menu_konfirmasi_pembayaran()

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



# ---------------------------------------------------------------------------
# Program, ruang, dan pengelolaan pendaftaran
# ---------------------------------------------------------------------------


def _tekan_enter(pesan="Tekan Enter untuk kembali..."):
    input(pesan)


def _pilih_program_admin(daftar=None, pertanyaan="Pilih program:"):
    """Pilih program berdasarkan ID; tidak mengembalikan ID program dari teks."""
    try:
        program = daftar if daftar is not None else program_repo.daftar_program_dengan_kuota()
    except psycopg.Error as exc:
        gagal("Gagal membaca data program dari database.")
        info(f"Jenis error: {type(exc).__name__}")
        _tekan_enter()
        return None

    if not program:
        peringatan("Belum ada program yang tersedia.")
        _tekan_enter()
        return None

    pilihan = [
        Choice(
            f"ID {item['id']} • {item['kode']} • {item['nama']} • "
            f"{item['status']} • kuota {item.get('sisa', '-')} tersisa",
            value=item["id"],
        )
        for item in program
    ]
    pilihan.extend([
        Separator("────────────────────────"),
        Choice("↩  Kembali", value="__kembali__"),
    ])
    nilai = questionary.select(
        pertanyaan, choices=pilihan, style=TEMA_ADMIN,
        qmark="⚡", pointer="▶", instruction=" (Gunakan ↑/↓ lalu Enter)",
    ).ask()
    return nilai if type(nilai) is int else None


def _tabel_program_admin(daftar):
    tabel = Table(
        title="Program Bimbel dan Kuota",
        header_style="bold cyan", border_style="blue", expand=True,
    )
    tabel.add_column("ID", justify="right", no_wrap=True)
    tabel.add_column("Kode", no_wrap=True)
    tabel.add_column("Nama Program", min_width=18)
    tabel.add_column("Jenjang", no_wrap=True)
    tabel.add_column("Harga/Bulan", justify="right", no_wrap=True)
    tabel.add_column("Terisi", justify="right")
    tabel.add_column("Sisa", justify="right")
    tabel.add_column("Status", no_wrap=True)
    for item in daftar:
        status = "[green]BUKA[/green]" if item["status"] == "buka" else "[yellow]TUTUP[/yellow]"
        tabel.add_row(
            str(item["id"]), str(item["kode"]), str(item["nama"]),
            str(item["jenjang"]), _format_rupiah(item["harga_bulanan"]),
            str(item.get("terisi", 0)), str(item.get("sisa", item["kuota"])), status,
        )
    console.print(tabel)


def _program_daftar_admin():
    bersihkan_layar()
    _tampilkan_header("Program dan Ruang", "DAFTAR PROGRAM DAN KUOTA")
    try:
        daftar = program_repo.daftar_program_dengan_kuota()
        if not daftar:
            peringatan("Belum ada program bimbel.")
        else:
            _tabel_program_admin(daftar)
    except psycopg.Error as exc:
        gagal("Gagal membaca daftar program.")
        info(f"Jenis error: {type(exc).__name__}")
    _tekan_enter()


def _program_tambah_admin():
    bersihkan_layar()
    _tampilkan_header("Program dan Ruang", "TAMBAH PROGRAM")
    console.print(Panel(
        "Bobot nilai awal: Tugas 30%, Kuis 20%, UTS 20%, UAS 30%. "
        "Total bobot harus 100%; bobot dapat diubah setelah program dibuat.",
        border_style="blue", padding=(1, 2), expand=True,
    ))
    kode = questionary.text("Kode program (maks. 10 karakter):", style=TEMA_ADMIN).ask()
    if kode is None:
        return
    nama = questionary.text("Nama program:", style=TEMA_ADMIN).ask()
    if nama is None:
        return
    jenjang = questionary.text("Jenjang (contoh: SMP, SMA, Umum):", style=TEMA_ADMIN).ask()
    if jenjang is None:
        return
    deskripsi = questionary.text("Deskripsi (opsional):", style=TEMA_ADMIN).ask()
    if deskripsi is None:
        return
    harga = questionary.text("Harga bulanan (contoh 250000):", style=TEMA_ADMIN).ask()
    if harga is None:
        return
    kuota = questionary.text("Kuota siswa (angka bulat):", style=TEMA_ADMIN).ask()
    if kuota is None:
        return
    yakin = questionary.confirm(
        f"Buat program {nama.strip() or '(tanpa nama)'}?", default=False, style=TEMA_ADMIN,
    ).ask()
    if yakin is not True:
        info("Penambahan program dibatalkan.")
        _tekan_enter()
        return
    berhasil, pesan = program_service.buat_program({
        "kode": kode, "nama": nama, "jenjang": jenjang,
        "deskripsi": deskripsi, "harga_bulanan": harga, "kuota": kuota,
    })
    sukses(pesan) if berhasil else gagal(pesan)
    _tekan_enter()


def _program_ubah_admin():
    bersihkan_layar()
    _tampilkan_header("Program dan Ruang", "UBAH DATA PROGRAM")
    try:
        daftar = program_repo.daftar_program_dengan_kuota()
    except psycopg.Error as exc:
        gagal("Gagal membaca daftar program.")
        info(f"Jenis error: {type(exc).__name__}")
        _tekan_enter()
        return
    program_id = _pilih_program_admin(daftar, "Pilih program yang ingin diubah:")
    if program_id is None:
        return
    item = next((x for x in daftar if x["id"] == program_id), None)
    if item is None:
        peringatan("Program tidak ditemukan; silakan muat ulang.")
        _tekan_enter()
        return

    bidang = questionary.select(
        f"Data yang akan diubah — {item['kode']} / {item['nama']}",
        choices=[
            Choice("Kode program", value="kode"),
            Choice("Nama program", value="nama"),
            Choice("Jenjang", value="jenjang"),
            Choice("Deskripsi", value="deskripsi"),
            Choice("Harga bulanan", value="harga_bulanan"),
            Choice("Kuota", value="kuota"),
            Choice("Bobot nilai (semua komponen sekaligus)", value="bobot"),
            Separator("────────────────────────"),
            Choice("Kembali", value="kembali"),
        ], style=TEMA_ADMIN, qmark="⚡", pointer="▶",
    ).ask()
    if bidang is None or bidang == "kembali":
        return

    perubahan = {}
    if bidang == "bobot":
        for kolom, label in [
            ("bobot_tugas", "Bobot tugas (%)"),
            ("bobot_kuis", "Bobot kuis (%)"),
            ("bobot_uts", "Bobot UTS (%)"),
            ("bobot_uas", "Bobot UAS (%)"),
        ]:
            nilai = questionary.text(
                f"{label} (saat ini {item[kolom]}):", default=str(item[kolom]), style=TEMA_ADMIN,
            ).ask()
            if nilai is None:
                return
            perubahan[kolom] = nilai
    else:
        label = {
            "kode": "Kode program", "nama": "Nama program", "jenjang": "Jenjang",
            "deskripsi": "Deskripsi (kosongkan untuk menghapus deskripsi)",
            "harga_bulanan": "Harga bulanan", "kuota": "Kuota siswa",
        }[bidang]
        default = "" if bidang == "deskripsi" and item.get(bidang) is None else str(item.get(bidang, ""))
        nilai = questionary.text(f"{label}:", default=default, style=TEMA_ADMIN).ask()
        if nilai is None:
            return
        if bidang == "deskripsi" and not nilai.strip():
            perubahan[bidang] = None
        else:
            perubahan[bidang] = nilai

    berhasil, pesan = program_service.ubah_program(program_id, perubahan)
    sukses(pesan) if berhasil else gagal(pesan)
    _tekan_enter()


def _program_toggle_admin():
    bersihkan_layar()
    _tampilkan_header("Program dan Ruang", "TUTUP / BUKA PROGRAM")
    try:
        daftar = program_repo.daftar_program_dengan_kuota()
    except psycopg.Error as exc:
        gagal("Gagal membaca daftar program.")
        info(f"Jenis error: {type(exc).__name__}")
        _tekan_enter()
        return
    program_id = _pilih_program_admin(daftar, "Pilih program:")
    if program_id is None:
        return
    item = next((x for x in daftar if x["id"] == program_id), None)
    if item is None:
        return
    status_baru = "tutup" if item["status"] == "buka" else "buka"
    aksi = "menutup" if status_baru == "tutup" else "membuka kembali"
    yakin = questionary.confirm(
        f"Yakin {aksi} program {item['nama']}?", default=False, style=TEMA_ADMIN,
    ).ask()
    if yakin is not True:
        info("Perubahan status dibatalkan.")
        _tekan_enter()
        return
    berhasil, pesan = program_service.ubah_program(program_id, {"status": status_baru})
    sukses(pesan) if berhasil else gagal(pesan)
    _tekan_enter()


def _ruang_daftar_admin():
    bersihkan_layar()
    _tampilkan_header("Program dan Ruang", "DAFTAR RUANG BELAJAR")
    try:
        daftar = program_repo.daftar_ruang()
        tabel = Table(title="Ruang Belajar", header_style="bold cyan", border_style="blue", expand=True)
        tabel.add_column("ID", justify="right")
        tabel.add_column("Nama Ruang")
        tabel.add_column("Kapasitas", justify="right")
        tabel.add_column("Status", justify="center")
        for item in daftar:
            tabel.add_row(
                str(item["id"]), str(item["nama"]), str(item["kapasitas"]),
                "[green]Aktif[/green]" if item["aktif"] else "[yellow]Nonaktif[/yellow]",
            )
        if daftar:
            console.print(tabel)
        else:
            peringatan("Belum ada ruang belajar.")
    except psycopg.Error as exc:
        gagal("Gagal membaca daftar ruang.")
        info(f"Jenis error: {type(exc).__name__}")
    _tekan_enter()


def _ruang_tambah_admin():
    bersihkan_layar()
    _tampilkan_header("Program dan Ruang", "TAMBAH RUANG")
    nama = questionary.text("Nama ruang (maks. 30 karakter):", style=TEMA_ADMIN).ask()
    if nama is None:
        return
    kapasitas = questionary.text("Kapasitas ruang:", style=TEMA_ADMIN).ask()
    if kapasitas is None:
        return
    berhasil, pesan = program_service.buat_ruang(nama, kapasitas)
    sukses(pesan) if berhasil else gagal(pesan)
    _tekan_enter()


def _ruang_ubah_admin():
    bersihkan_layar()
    _tampilkan_header("Program dan Ruang", "UBAH RUANG")
    try:
        daftar = program_repo.daftar_ruang()
    except psycopg.Error as exc:
        gagal("Gagal membaca daftar ruang.")
        info(f"Jenis error: {type(exc).__name__}")
        _tekan_enter()
        return
    if not daftar:
        peringatan("Belum ada ruang untuk diubah.")
        _tekan_enter()
        return
    pilihan = questionary.select(
        "Pilih ruang:",
        choices=[Choice(f"ID {x['id']} • {x['nama']} • kapasitas {x['kapasitas']}", value=x["id"]) for x in daftar]
        + [Separator("────────────────────────"), Choice("Kembali", value="kembali")],
        style=TEMA_ADMIN, qmark="⚡", pointer="▶",
    ).ask()
    if type(pilihan) is not int:
        return
    ruang = next((x for x in daftar if x["id"] == pilihan), None)
    if ruang is None:
        return
    nama = questionary.text("Nama ruang:", default=str(ruang["nama"]), style=TEMA_ADMIN).ask()
    if nama is None:
        return
    kapasitas = questionary.text("Kapasitas:", default=str(ruang["kapasitas"]), style=TEMA_ADMIN).ask()
    if kapasitas is None:
        return
    berhasil, pesan = program_service.ubah_ruang(pilihan, {"nama": nama, "kapasitas": kapasitas})
    sukses(pesan) if berhasil else gagal(pesan)
    _tekan_enter()


def menu_program_ruang():
    """Submenu program dan ruang sesuai rancangan MENU_CLI.md."""
    if not session.punya_role("admin"):
        peringatan("Akses ditolak. Silakan login sebagai admin.")
        return
    pilihan_aksi = {
        "daftar_program": _program_daftar_admin,
        "tambah_program": _program_tambah_admin,
        "ubah_program": _program_ubah_admin,
        "toggle_program": _program_toggle_admin,
        "daftar_ruang": _ruang_daftar_admin,
        "tambah_ruang": _ruang_tambah_admin,
        "ubah_ruang": _ruang_ubah_admin,
    }
    while session.punya_role("admin"):
        bersihkan_layar()
        _tampilkan_header("Program dan Ruang", "MANAJEMEN MASTER DATA")
        pilihan = questionary.select(
            "Pilih tindakan:",
            choices=[
                Choice("Daftar program (kuota terisi / sisa)", value="daftar_program"),
                Choice("Tambah program", value="tambah_program"),
                Choice("Ubah program (harga, kuota, bobot nilai)", value="ubah_program"),
                Choice("Tutup / buka program", value="toggle_program"),
                Separator("──────────── RUANG BELAJAR ────────────"),
                Choice("Daftar ruang", value="daftar_ruang"),
                Choice("Tambah ruang", value="tambah_ruang"),
                Choice("Ubah ruang", value="ubah_ruang"),
                Separator("────────────────────────"),
                Choice("Kembali ke dashboard", value="kembali"),
            ], style=TEMA_ADMIN, qmark="⚡", pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()
        if pilihan is None or pilihan == "kembali":
            return
        aksi = pilihan_aksi.get(pilihan)
        if aksi:
            aksi()



# ---------------------------------------------------------------------------
# Jadwal reguler: lihat/filter, tambah, ubah, dan nonaktifkan
# ---------------------------------------------------------------------------

_HARI_JADWAL = [
    ("Senin", "senin"), ("Selasa", "selasa"), ("Rabu", "rabu"),
    ("Kamis", "kamis"), ("Jumat", "jumat"), ("Sabtu", "sabtu"),
    ("Minggu", "minggu"),
]


def _tabel_jadwal_admin(daftar, judul="Jadwal Mengajar"):
    tabel = Table(title=judul, header_style="bold cyan", border_style="blue", expand=True)
    for nama, kwargs in [
        ("ID", {"justify": "right", "no_wrap": True}),
        ("Hari", {"no_wrap": True}),
        ("Waktu", {"no_wrap": True}),
        ("Program", {"overflow": "fold"}),
        ("Tutor", {"overflow": "fold"}),
        ("Ruang", {"no_wrap": True}),
        ("Siswa", {"justify": "right", "no_wrap": True}),
        ("Pertemuan", {"justify": "right", "no_wrap": True}),
        ("Kapasitas", {"justify": "right", "no_wrap": True}),
        ("Status", {"no_wrap": True}),
    ]:
        tabel.add_column(nama, **kwargs)
    for item in daftar:
        status = "[green]AKTIF[/green]" if item["aktif"] else "[dim]NONAKTIF[/dim]"
        tabel.add_row(
            str(item["id"]), str(item["hari"]).capitalize(),
            f"{item['jam_mulai'].strftime('%H:%M')}-{item['jam_selesai'].strftime('%H:%M')}",
            f"{item.get('kode_program') or '-'} — {item.get('nama_program') or '-'}",
            f"{item.get('kode_tutor') or '-'} — {item.get('nama_tutor') or '-'}",
            str(item.get("nama_ruang") or "-"), str(item.get("jumlah_siswa", 0)),
            str(item.get("jumlah_pertemuan", 0)), str(item.get("kapasitas_ruang", "-")), status,
        )
    console.print(tabel)


def _ambil_opsi_jadwal(jenis, pertanyaan, aktif_saja=True):
    fungsi = {
        "program": schedule_service.opsi_program,
        "tutor": schedule_service.opsi_tutor,
        "ruang": schedule_service.opsi_ruang,
    }[jenis]
    berhasil, hasil = fungsi(aktif_saja=aktif_saja)
    if not berhasil:
        gagal(hasil)
        _tekan_enter()
        return None
    if not hasil:
        peringatan({"program": "Belum ada program terbuka.", "tutor": "Belum ada tutor aktif.", "ruang": "Belum ada ruang aktif."}[jenis])
        _tekan_enter()
        return None

    def label(item):
        if jenis == "program":
            return f"ID {item['id']} • {item['kode']} • {item['nama']} ({item['jenjang']})"
        if jenis == "tutor":
            kode = item.get("kode_tutor") or "tanpa kode"
            return f"ID {item['id']} • {kode} • {item['nama_lengkap']}"
        return f"ID {item['id']} • {item['nama']} • kapasitas {item['kapasitas']}"

    pilihan = questionary.select(
        pertanyaan,
        choices=[Choice(label(item), value=item["id"]) for item in hasil]
        + [Separator("────────────────────────"), Choice("Kembali", value="kembali")],
        style=TEMA_ADMIN, qmark="⚡", pointer="▶",
        instruction=" (Gunakan ↑/↓ lalu Enter)",
    ).ask()
    return pilihan if type(pilihan) is int else None


def _pilih_hari_jadwal(pertanyaan="Pilih hari:"):
    hasil = questionary.select(
        pertanyaan,
        choices=[Choice(label, value=value) for label, value in _HARI_JADWAL]
        + [Separator("────────────────────────"), Choice("Kembali", value="kembali")],
        style=TEMA_ADMIN, qmark="⚡", pointer="▶",
    ).ask()
    return hasil if hasil in {value for _, value in _HARI_JADWAL} else None


def _pilih_satu_jadwal(pertanyaan, *, hanya_aktif=None):
    berhasil, hasil = schedule_service.daftar_jadwal(aktif=hanya_aktif)
    if not berhasil:
        gagal(hasil)
        _tekan_enter()
        return None
    if not hasil:
        peringatan("Tidak ada jadwal yang cocok.")
        _tekan_enter()
        return None
    _tabel_jadwal_admin(hasil)
    pilihan = questionary.select(
        pertanyaan,
        choices=[Choice(
            f"ID {x['id']} • {x['hari'].capitalize()} {x['jam_mulai'].strftime('%H:%M')}-"
            f"{x['jam_selesai'].strftime('%H:%M')} • {x['nama_program']} • {x['nama_tutor']} • {x['nama_ruang']}",
            value=x["id"],
        ) for x in hasil] + [Separator("────────────────────────"), Choice("Kembali", value="kembali")],
        style=TEMA_ADMIN, qmark="⚡", pointer="▶",
    ).ask()
    if type(pilihan) is not int:
        return None
    return next((x for x in hasil if x["id"] == pilihan), None)


def _jadwal_lihat_admin():
    bersihkan_layar()
    _tampilkan_header("Jadwal", "LIHAT JADWAL PER PROGRAM / TUTOR / RUANG / HARI")
    kategori = questionary.select(
        "Tampilkan jadwal berdasarkan:",
        choices=[
            Choice("Semua jadwal", "semua"), Choice("Per program", "program"),
            Choice("Per tutor", "tutor"), Choice("Per ruang", "ruang"),
            Choice("Per hari", "hari"),
            Separator("────────────────────────"), Choice("Kembali", "kembali"),
        ], style=TEMA_ADMIN, qmark="⚡", pointer="▶",
    ).ask()
    if kategori is None or kategori == "kembali":
        return
    filters = {}
    if kategori in {"program", "tutor", "ruang"}:
        identitas = _ambil_opsi_jadwal(kategori, f"{('Pilih ' + kategori)} untuk filter:", aktif_saja=False)
        if identitas is None:
            return
        filters[{"program": "program_id", "tutor": "tutor_id", "ruang": "room_id"}[kategori]] = identitas
    elif kategori == "hari":
        hari = _pilih_hari_jadwal("Pilih hari yang ingin dilihat:")
        if hari is None:
            return
        filters["hari"] = hari

    berhasil, hasil = schedule_service.daftar_jadwal(**filters)
    bersihkan_layar()
    _tampilkan_header("Jadwal", "HASIL DAFTAR JADWAL")
    if not berhasil:
        gagal(hasil)
    elif not hasil:
        peringatan("Belum ada jadwal untuk filter tersebut.")
    else:
        _tabel_jadwal_admin(hasil)
    _tekan_enter()


def _jadwal_tambah_admin():
    bersihkan_layar()
    _tampilkan_header("Jadwal", "TAMBAH JADWAL MENGAJAR")
    program_id = _ambil_opsi_jadwal("program", "Pilih program yang dijadwalkan:")
    if program_id is None:
        return
    tutor_id = _ambil_opsi_jadwal("tutor", "Pilih tutor:")
    if tutor_id is None:
        return
    room_id = _ambil_opsi_jadwal("ruang", "Pilih ruang:")
    if room_id is None:
        return
    hari = _pilih_hari_jadwal()
    if hari is None:
        return
    jam_mulai = questionary.text("Jam mulai (HH:MM, contoh 15:00):", style=TEMA_ADMIN).ask()
    if jam_mulai is None:
        return
    jam_selesai = questionary.text("Jam selesai (HH:MM, contoh 16:30):", style=TEMA_ADMIN).ask()
    if jam_selesai is None:
        return
    console.print(Panel(
        f"Program ID: {program_id}\nTutor ID: {tutor_id}\nRuang ID: {room_id}\n"
        f"Hari: {hari.capitalize()}\nWaktu: {jam_mulai}–{jam_selesai}",
        title="Ringkasan Jadwal", border_style="cyan", padding=(1, 2), expand=True,
    ))
    yakin = questionary.confirm("Simpan jadwal ini?", default=False, style=TEMA_ADMIN).ask()
    if yakin is not True:
        info("Pembuatan jadwal dibatalkan.")
        _tekan_enter()
        return
    berhasil, pesan = schedule_service.buat_jadwal({
        "program_id": program_id, "tutor_id": tutor_id, "room_id": room_id,
        "hari": hari, "jam_mulai": jam_mulai, "jam_selesai": jam_selesai,
    })
    sukses(pesan) if berhasil else gagal(pesan)
    _tekan_enter()


def _jadwal_ubah_admin():
    bersihkan_layar()
    _tampilkan_header("Jadwal", "UBAH JADWAL")
    item = _pilih_satu_jadwal("Pilih jadwal yang ingin diubah:", hanya_aktif=True)
    if item is None:
        return
    bidang = questionary.select(
        f"Pilih bagian jadwal ID {item['id']} yang ingin diubah:",
        choices=[
            Choice("Program", "program_id"), Choice("Tutor", "tutor_id"),
            Choice("Ruang", "room_id"), Choice("Hari", "hari"),
            Choice("Jam mulai", "jam_mulai"), Choice("Jam selesai", "jam_selesai"),
            Separator("────────────────────────"), Choice("Kembali", "kembali"),
        ], style=TEMA_ADMIN, qmark="⚡", pointer="▶",
    ).ask()
    if bidang is None or bidang == "kembali":
        return
    data = {}
    if bidang in {"program_id", "tutor_id", "room_id"}:
        jenis = {"program_id": "program", "tutor_id": "tutor", "room_id": "ruang"}[bidang]
        nilai = _ambil_opsi_jadwal(jenis, f"Pilih {jenis} yang baru:")
        if nilai is None:
            return
        data[bidang] = nilai
    elif bidang == "hari":
        nilai = _pilih_hari_jadwal("Pilih hari yang baru:")
        if nilai is None:
            return
        data[bidang] = nilai
    else:
        waktu_lama = item[bidang].strftime("%H:%M")
        nilai = questionary.text(
            f"{('Jam mulai' if bidang == 'jam_mulai' else 'Jam selesai')} baru (HH:MM):",
            default=waktu_lama, style=TEMA_ADMIN,
        ).ask()
        if nilai is None:
            return
        data[bidang] = nilai
    yakin = questionary.confirm("Simpan perubahan jadwal?", default=False, style=TEMA_ADMIN).ask()
    if yakin is not True:
        info("Perubahan jadwal dibatalkan.")
        _tekan_enter()
        return
    berhasil, pesan = schedule_service.ubah_jadwal(item["id"], data)
    sukses(pesan) if berhasil else gagal(pesan)
    _tekan_enter()


def _jadwal_nonaktifkan_admin():
    bersihkan_layar()
    _tampilkan_header("Jadwal", "NONAKTIFKAN JADWAL")
    item = _pilih_satu_jadwal("Pilih jadwal yang akan dinonaktifkan:", hanya_aktif=True)
    if item is None:
        return
    detail = (
        f"{item['hari'].capitalize()} {item['jam_mulai'].strftime('%H:%M')}-"
        f"{item['jam_selesai'].strftime('%H:%M')} • {item['nama_program']} • {item['nama_tutor']}"
    )
    yakin = questionary.confirm(
        f"Nonaktifkan jadwal ID {item['id']}? {detail}. Riwayat pertemuan tidak dihapus.",
        default=False, style=TEMA_ADMIN,
    ).ask()
    if yakin is not True:
        info("Penonaktifan jadwal dibatalkan.")
        _tekan_enter()
        return
    berhasil, pesan = schedule_service.nonaktifkan_jadwal(item["id"])
    sukses(pesan) if berhasil else gagal(pesan)
    _tekan_enter()


def menu_jadwal_admin():
    """Submenu jadwal admin menurut rancangan MENU_CLI.md."""
    if not session.punya_role("admin"):
        peringatan("Akses ditolak. Login sebagai admin terlebih dahulu.")
        return
    aksi = {
        "lihat": _jadwal_lihat_admin,
        "tambah": _jadwal_tambah_admin,
        "ubah": _jadwal_ubah_admin,
        "nonaktif": _jadwal_nonaktifkan_admin,
    }
    while session.punya_role("admin"):
        bersihkan_layar()
        _tampilkan_header("Jadwal", "MANAJEMEN JADWAL MENGAJAR")
        pilihan = questionary.select(
            "Pilih tindakan:",
            choices=[
                Choice("Lihat jadwal (per program / tutor / ruang / hari)", "lihat"),
                Choice("Tambah jadwal", "tambah"), Choice("Ubah jadwal", "ubah"),
                Choice("Nonaktifkan jadwal", "nonaktif"),
                Separator("────────────────────────"), Choice("Kembali ke dashboard", "kembali"),
            ], style=TEMA_ADMIN, qmark="⚡", pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()
        if pilihan is None or pilihan == "kembali":
            return
        fungsi = aksi.get(pilihan)
        if fungsi:
            fungsi()


def _tabel_pendaftaran_admin(daftar):
    tabel = Table(title="Daftar Pendaftaran Program", header_style="bold cyan", border_style="blue", expand=True)
    tabel.add_column("ID", justify="right", no_wrap=True)
    tabel.add_column("NIS", no_wrap=True)
    tabel.add_column("Nama Siswa", min_width=14)
    tabel.add_column("Program", min_width=14)
    tabel.add_column("Status", no_wrap=True)
    tabel.add_column("Tagihan", justify="right")
    tabel.add_column("Tanggal", no_wrap=True)
    for item in daftar:
        status = str(item["status"]).upper()
        tabel.add_row(
            str(item["enrollment_id"]), str(item.get("nis") or "-"),
            str(item.get("nama_siswa") or "-"),
            f"{item.get('kode_program') or '-'} — {item.get('nama_program') or '-'}",
            status, str(item.get("jumlah_tagihan", 0)), _format_waktu(item.get("created_at")),
        )
    console.print(tabel)


def _detail_pendaftaran_admin(enrollment_id: int):
    berhasil, hasil = admin_enrollment_service.detail_pendaftaran(enrollment_id)
    if not berhasil:
        gagal(hasil)
        _tekan_enter()
        return
    detail = hasil
    tabel = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    tabel.add_column("Informasi", style="cyan", width=24)
    tabel.add_column("Nilai", style="white", overflow="fold")
    for label, value in [
        ("ID pendaftaran", detail["enrollment_id"]),
        ("Nama siswa", detail.get("nama_siswa")),
        ("Username", detail.get("username")),
        ("NIS", detail.get("nis")),
        ("Email", detail.get("email")),
        ("Status akun", detail.get("status_akun")),
        ("Program", f"{detail.get('kode_program')} — {detail.get('nama_program')}"),
        ("Jenjang", detail.get("jenjang")),
        ("Harga program/bulan", _format_rupiah(detail.get("harga_bulanan", 0))),
        ("Status pendaftaran", detail.get("status")),
        ("Tanggal daftar", _format_waktu(detail.get("created_at"))),
        ("Diproses pada", _format_waktu(detail.get("processed_at"))),
        ("Diproses oleh", detail.get("diproses_oleh") or "-"),
        ("Catatan penolakan", detail.get("alasan_tolak") or "-"),
        ("Jumlah tagihan", detail.get("jumlah_tagihan", 0)),
        ("Total tagihan tidak batal", _format_rupiah(detail.get("total_tagihan", 0))),
        ("Total pembayaran lunas", _format_rupiah(detail.get("total_terbayar", 0))),
    ]:
        tabel.add_row(str(label), str(value if value is not None else "-"))
    console.print(Panel(tabel, title="DETAIL PENDAFTARAN", border_style="cyan", padding=(1, 2), expand=True))
    _tekan_enter()


def _menu_daftar_pendaftaran_admin():
    bersihkan_layar()
    _tampilkan_header("Pendaftaran", "DAFTAR DAN FILTER PENDAFTARAN")
    try:
        programs = program_repo.daftar_program()
    except psycopg.Error as exc:
        gagal("Gagal membaca program untuk filter.")
        info(f"Jenis error: {type(exc).__name__}")
        _tekan_enter()
        return
    status_filter = questionary.select(
        "Filter status:",
        choices=[
            Choice("Semua status", value="__semua__"),
            Choice("Menunggu", value="menunggu"),
            Choice("Aktif", value="aktif"),
            Choice("Ditolak", value="ditolak"),
            Choice("Dibatalkan", value="batal"),
            Choice("Selesai", value="selesai"),
            Choice("Kembali", value="__kembali__"),
        ], style=TEMA_ADMIN, qmark="⚡", pointer="▶",
    ).ask()
    if status_filter is None or status_filter == "__kembali__":
        return
    program_choices = [Choice("Semua program", value=0)] + [
        Choice(f"{p['kode']} • {p['nama']}", value=p["id"]) for p in programs
    ]
    program_choices.extend([Separator("────────────────────────"), Choice("Kembali", value=-1)])
    program_filter = questionary.select(
        "Filter program:", choices=program_choices, style=TEMA_ADMIN,
        qmark="⚡", pointer="▶",
    ).ask()
    if type(program_filter) is not int or program_filter == -1:
        return
    status = None if status_filter == "__semua__" else status_filter
    berhasil, hasil = admin_enrollment_service.daftar_pendaftaran(
        status=status, program_id=program_filter or None,
    )
    if not berhasil:
        gagal(hasil)
        _tekan_enter()
        return
    daftar = hasil
    bersihkan_layar()
    _tampilkan_header("Pendaftaran", "HASIL FILTER")
    if not daftar:
        peringatan("Tidak ada pendaftaran sesuai filter.")
        _tekan_enter()
        return
    _tabel_pendaftaran_admin(daftar)
    pilihan = questionary.select(
        "Pilih pendaftaran untuk melihat detail:",
        choices=[Choice(
            f"ID {x['enrollment_id']} • {x['nama_siswa']} • {x['nama_program']} • {x['status']}",
            value=x["enrollment_id"],
        ) for x in daftar] + [Separator("────────────────────────"), Choice("Kembali", value="kembali")],
        style=TEMA_ADMIN, qmark="⚡", pointer="▶",
    ).ask()
    if type(pilihan) is int:
        _detail_pendaftaran_admin(pilihan)


def _pilih_pendaftaran_dengan_status(statuses, pertanyaan):
    daftar_gabung = []
    for status in statuses:
        berhasil, hasil = admin_enrollment_service.daftar_pendaftaran(status=status)
        if not berhasil:
            gagal(hasil)
            _tekan_enter()
            return None
        daftar_gabung.extend(hasil)
    daftar_gabung.sort(key=lambda item: (item.get("created_at") or 0, item["enrollment_id"]), reverse=True)
    if not daftar_gabung:
        peringatan("Tidak ada pendaftaran yang memenuhi syarat.")
        _tekan_enter()
        return None
    pilihan = questionary.select(
        pertanyaan,
        choices=[Choice(
            f"ID {x['enrollment_id']} • {x.get('nama_siswa')} • {x.get('nama_program')} • {x['status']}",
            value=x["enrollment_id"],
        ) for x in daftar_gabung] + [Separator("────────────────────────"), Choice("Kembali", value="kembali")],
        style=TEMA_ADMIN, qmark="⚡", pointer="▶",
    ).ask()
    if type(pilihan) is not int:
        return None
    item = next((x for x in daftar_gabung if x["enrollment_id"] == pilihan), None)
    return item


def _menu_pindahkan_pendaftaran_admin():
    bersihkan_layar()
    _tampilkan_header("Pendaftaran", "PINDAHKAN SISWA KE PROGRAM LAIN")
    asal = _pilih_pendaftaran_dengan_status(["aktif"], "Pilih pendaftaran aktif yang akan dipindahkan:")
    if asal is None:
        return
    try:
        seluruh_riwayat = enrollment_repo.enrollment_siswa(asal["student_id"])
        program = program_repo.daftar_program_dengan_kuota()
    except psycopg.Error as exc:
        gagal("Gagal membaca riwayat siswa atau program tujuan.")
        info(f"Jenis error: {type(exc).__name__}")
        _tekan_enter()
        return
    id_riwayat = {x["program_id"] for x in seluruh_riwayat}
    tujuan = [
        x for x in program
        if x["id"] != asal["program_id"]
        and x["status"] == "buka"
        and x.get("sisa", 0) > 0
        and x["id"] not in id_riwayat
    ]
    if not tujuan:
        peringatan("Tidak ada program tujuan yang buka, masih memiliki kuota, dan belum pernah diikuti siswa.")
        _tekan_enter()
        return
    program_id = _pilih_program_admin(tujuan, "Pilih program tujuan:")
    if program_id is None:
        return
    target = next((x for x in tujuan if x["id"] == program_id), None)
    if target is None:
        return
    console.print(Panel(
        "Pemindahan akan mengakhiri enrollment lama dan membuat enrollment aktif baru. "
        "Riwayat tagihan lama tetap disimpan. Tagihan periode berjalan yang belum lunas "
        "akan diganti sesuai harga program tujuan. Jika periode berjalan sudah lunas, "
        "tidak akan dibuat tagihan kedua pada bulan ini. Tidak ada prorata/refund otomatis.",
        title="Dampak pemindahan", border_style="yellow", padding=(1, 2), expand=True,
    ))
    yakin = questionary.confirm(
        f"Pindahkan {asal['nama_siswa']} dari {asal['nama_program']} ke {target['nama']}?",
        default=False, style=TEMA_ADMIN,
    ).ask()
    if yakin is not True:
        info("Pemindahan dibatalkan.")
        _tekan_enter()
        return
    berhasil, pesan = admin_enrollment_service.pindahkan_pendaftaran(asal["enrollment_id"], program_id)
    sukses(pesan) if berhasil else gagal(pesan)
    _tekan_enter()


def _menu_batalkan_pendaftaran_admin():
    bersihkan_layar()
    _tampilkan_header("Pendaftaran", "BATALKAN PENDAFTARAN")
    item = _pilih_pendaftaran_dengan_status(
        ["menunggu", "aktif"], "Pilih pendaftaran yang ingin dibatalkan:"
    )
    if item is None:
        return
    alasan = questionary.text(
        "Alasan pembatalan (opsional):", style=TEMA_ADMIN, qmark="📝",
    ).ask()
    if alasan is None:
        return
    console.print(Panel(
        "Status pendaftaran akan menjadi BATAL. Riwayat tagihan tidak dihapus; "
        "tagihan yang sudah terbit tetap dapat ditagihkan. Periksa konsekuensi ini sebelum melanjutkan.",
        title="Konfirmasi pembatalan", border_style="yellow", padding=(1, 2), expand=True,
    ))
    yakin = questionary.confirm(
        f"Batalkan pendaftaran {item['nama_program']} milik {item['nama_siswa']}?",
        default=False, style=TEMA_ADMIN,
    ).ask()
    if yakin is not True:
        info("Pembatalan pendaftaran dibatalkan.")
        _tekan_enter()
        return
    berhasil, pesan = admin_enrollment_service.batalkan_pendaftaran(item["enrollment_id"], alasan)
    sukses(pesan) if berhasil else gagal(pesan)
    _tekan_enter()


def menu_pendaftaran_admin():
    """Submenu pengelolaan enrollment terpisah dari persetujuan di Pusat Konfirmasi."""
    if not session.punya_role("admin"):
        peringatan("Akses ditolak. Silakan login sebagai admin.")
        return
    while session.punya_role("admin"):
        bersihkan_layar()
        _tampilkan_header("Pendaftaran", "PENGELOLAAN PENDAFTARAN SISWA")
        pilihan = questionary.select(
            "Pilih tindakan:",
            choices=[
                Choice("Daftar pendaftaran (filter status / program)", value="daftar"),
                Choice("Pindahkan siswa ke program lain", value="pindah"),
                Choice("Batalkan pendaftaran", value="batal"),
                Separator("────────────────────────"),
                Choice("Kembali ke dashboard", value="kembali"),
            ], style=TEMA_ADMIN, qmark="⚡", pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()
        if pilihan is None or pilihan == "kembali":
            return
        if pilihan == "daftar":
            _menu_daftar_pendaftaran_admin()
        elif pilihan == "pindah":
            _menu_pindahkan_pendaftaran_admin()
        elif pilihan == "batal":
            _menu_batalkan_pendaftaran_admin()


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
                "[dim]Pusat Konfirmasi, Manajemen Akun, Data Siswa/Tutor, "
                "Program/Ruang, dan Pendaftaran telah dihubungkan ke database.[/dim]",
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
        if pilihan == "program":
            menu_program_ruang()
            continue
        if pilihan == "pendaftaran":
            menu_pendaftaran_admin()
            continue
        if pilihan == "akun":
            menu_admin_data.menu_manajemen_akun_admin()
            continue
        if pilihan == "siswa":
            menu_admin_data.menu_data_siswa_admin()
            continue
        if pilihan == "tutor":
            menu_admin_data.menu_data_tutor_admin()
            continue
        if pilihan == "jadwal":
            menu_jadwal_admin()
            continue
        if pilihan == "pembayaran":
            menu_pembayaran.menu_pembayaran_admin()
            continue
        if pilihan == "laporan":
            menu_admin_laporan.menu_laporan_admin()
            continue
        if pilihan == "pengumuman":
            menu_admin_komunikasi.menu_pengumuman_admin()
            continue
        if pilihan == "log":
            menu_admin_komunikasi.menu_log_aktivitas_admin()
            continue

        label = next(
            (teks for teks, kode in MENU_ADMIN if kode == pilihan),
            pilihan,
        )
        _tampilkan_modul_belum_tersedia(label)
