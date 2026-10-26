"""Submenu laporan admin: laporan interaktif, ekspor CSV, dan Excel."""

from datetime import date, datetime
from decimal import Decimal

import psycopg
import questionary
from questionary import Choice, Separator, Style
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app import session
from app.services import report_service
from app.ui.console import bersihkan_layar, console, gagal, peringatan, sukses
from app.utils.formatters import rupiah

GAYA = Style([
    ("qmark", "fg:#00ffff bold"), ("question", "fg:#ffffff bold"),
    ("answer", "fg:#00ffff bold"), ("pointer", "fg:#00ffff bold"),
    ("highlighted", "fg:#00ffff bold"), ("selected", "fg:#00ffff"),
    ("separator", "fg:#444444"), ("instruction", "fg:#888888 italic"),
])


def _jeda():
    try:
        input("\nTekan Enter untuk kembali...")
    except (EOFError, KeyboardInterrupt):
        pass


def _header(subjudul):
    console.print(Panel(
        f"[bold cyan]S I B I M A[/bold cyan]\n[bold white]LAPORAN ADMIN[/bold white]\n[dim]{subjudul}[/dim]",
        border_style="cyan", padding=(1, 3), expand=True,
    ))


def _format(nilai, key):
    if nilai is None:
        return "-"
    if key == "total_pemasukan":
        return rupiah(nilai)
    if key == "persen_hadir":
        return f"{float(nilai):.1f}%"
    if isinstance(nilai, datetime):
        return nilai.strftime("%d-%m-%Y %H:%M")
    if isinstance(nilai, date):
        if key == "bulan":
            return nilai.strftime("%m-%Y")
        return nilai.strftime("%d-%m-%Y")
    if isinstance(nilai, Decimal):
        return f"{nilai:.2f}"
    return str(nilai)


def _tabel_halaman(laporan, halaman, ukuran=20):
    kolom = laporan["kolom"]
    semua = laporan["data"]
    awal = halaman * ukuran
    data = semua[awal:awal + ukuran]
    tabel = Table(title=laporan["judul"], header_style="bold cyan", border_style="blue", expand=True)
    for _, label in kolom:
        tabel.add_column(label, overflow="fold")
    if not data:
        tabel.add_row(*[Text("Tidak ada data") if i == 0 else Text("-") for i, _ in enumerate(kolom)])
    else:
        for baris in data:
            tabel.add_row(*[
                Text(_format(baris.get(kunci), kunci)) for kunci, _ in kolom
            ])
    console.print(tabel)
    console.print(f"[dim]Menampilkan {awal + 1 if data else 0}-{awal + len(data)} dari {len(semua)} baris[/dim]")


def _pesan_hak_akses_laporan():
    gagal(
        "Akun database belum memiliki hak baca untuk objek laporan. Jalankan dari root proyek "
        "dengan akun pemilik database: psql -U postgres -d bimbel_db -h localhost "
        "-v ON_ERROR_STOP=1 -f sql/permissions/20261026_laporan_select.sql. "
        "Jika akun pemilik bukan postgres, ganti nama akun pada perintah."
    )


def _tampilkan_laporan(kode):
    try:
        laporan = report_service.ambil_laporan(kode)
    except (ValueError, PermissionError) as exc:
        gagal(str(exc)); _jeda(); return
    except psycopg.errors.InsufficientPrivilege:
        _pesan_hak_akses_laporan(); _jeda(); return
    except (psycopg.Error, OSError) as exc:
        gagal(f"Laporan gagal diambil ({type(exc).__name__})."); _jeda(); return

    halaman = 0
    ukuran = 20
    while True:
        bersihkan_layar()
        _header(laporan["judul"])
        _tabel_halaman(laporan, halaman, ukuran)
        total = len(laporan["data"])
        if total <= ukuran:
            _jeda()
            return
        pilihan = []
        if halaman > 0:
            pilihan.append(Choice("Halaman sebelumnya", value="prev"))
        if (halaman + 1) * ukuran < total:
            pilihan.append(Choice("Halaman berikutnya", value="next"))
        pilihan.extend([
            Separator("────────────────────────"),
            Choice("Kembali", value="kembali"),
        ])
        aksi = questionary.select("Navigasi laporan:", choices=pilihan, style=GAYA).ask()
        if aksi in (None, "kembali"):
            return
        if aksi == "next":
            halaman += 1
        elif aksi == "prev":
            halaman = max(0, halaman - 1)


def _pilih_jenis_ekspor(format_label):
    try:
        jenis = report_service.daftar_jenis_laporan()
    except PermissionError as exc:
        gagal(str(exc)); _jeda(); return None
    except psycopg.errors.InsufficientPrivilege:
        _pesan_hak_akses_laporan(); _jeda(); return None
    except psycopg.Error as exc:
        gagal(f"Daftar laporan gagal dimuat ({type(exc).__name__})."); _jeda(); return None

    pilihan = questionary.select(
        f"Pilih laporan yang akan diekspor ke {format_label}:",
        choices=[Choice(item["judul"], value=item["kode"]) for item in jenis]
        + [Separator("────────────────────────"), Choice("Kembali", value="kembali")],
        style=GAYA,
    ).ask()
    return None if not pilihan or pilihan == "kembali" else pilihan


def _ekspor_csv():
    pilihan = _pilih_jenis_ekspor("CSV")
    if not pilihan:
        return
    yakin = questionary.confirm(
        "Ekspor CSV dengan pemisah titik koma agar kolom lebih mudah dibuka di Excel Indonesia?",
        default=True, style=GAYA,
    ).ask()
    if not yakin:
        return
    try:
        path = report_service.ekspor_csv(pilihan)
        sukses(f"CSV berhasil diekspor: {path}")
        console.print("[dim]CSV menyimpan data mentah tanpa warna/format sel. Untuk laporan berformat, gunakan ekspor Excel (.xlsx).[/dim]")
    except (ValueError, PermissionError) as exc:
        gagal(str(exc))
    except psycopg.errors.InsufficientPrivilege:
        _pesan_hak_akses_laporan()
    except RuntimeError as exc:
        gagal(str(exc))
    except (psycopg.Error, OSError) as exc:
        gagal(f"Ekspor CSV gagal ({type(exc).__name__}).")
    _jeda()


def _ekspor_excel():
    pilihan = _pilih_jenis_ekspor("Excel (.xlsx)")
    if not pilihan:
        return
    yakin = questionary.confirm(
        "Ekspor workbook Excel berformat dengan judul, filter, lebar kolom, dan format angka?",
        default=True, style=GAYA,
    ).ask()
    if not yakin:
        return
    try:
        path = report_service.ekspor_excel(pilihan)
        sukses(f"Workbook Excel berhasil diekspor: {path}")
    except (ValueError, PermissionError) as exc:
        gagal(str(exc))
    except psycopg.errors.InsufficientPrivilege:
        _pesan_hak_akses_laporan()
    except RuntimeError as exc:
        gagal(str(exc))
    except (psycopg.Error, OSError) as exc:
        gagal(f"Ekspor Excel gagal ({type(exc).__name__}).")
    _jeda()

def menu_laporan_admin():
    if not session.punya_role("admin"):
        peringatan("Akses laporan ditolak. Login sebagai admin.")
        return
    tindakan = {
        "pemasukan": ("pemasukan",),
        "siswa": ("siswa_program",),
        "kehadiran": ("kehadiran",),
        "nilai": ("nilai",),
    }
    while session.punya_role("admin"):
        bersihkan_layar()
        _header("Laporan pemasukan, siswa, kehadiran, dan nilai")
        pilihan = questionary.select(
            "Pilih jenis laporan:",
            choices=[
                Choice("Pemasukan per bulan", value="pemasukan"),
                Choice("Siswa per program", value="siswa"),
                Choice("Rekap kehadiran", value="kehadiran"),
                Choice("Rata-rata nilai per program", value="nilai"),
                Choice("Ekspor laporan ke CSV (.csv)", value="csv"),
                Choice("Ekspor laporan ke Excel (.xlsx) — format rapi", value="xlsx"),
                Separator("────────────────────────"),
                Choice("Kembali ke dashboard", value="kembali"),
            ], style=GAYA, qmark="⚡", pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()
        if pilihan in (None, "kembali"):
            return
        if pilihan == "csv":
            _ekspor_csv()
        elif pilihan == "xlsx":
            _ekspor_excel()
        elif pilihan in tindakan:
            _tampilkan_laporan(tindakan[pilihan][0])
