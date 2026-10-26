"""Membuat struktur folder dan file kerangka proyek BIMBEL.

Cara pakai (dari folder proyek, .venv boleh belum aktif):
    python buat_struktur.py

File yang sudah ada TIDAK akan ditimpa, jadi aman dijalankan berulang kali.
"""
from pathlib import Path

BASE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------
# Pembantu untuk file kerangka (hanya docstring + daftar fungsi rencana)
# ---------------------------------------------------------------------
def stub(deskripsi, fungsi=None):
    baris = ['"""' + deskripsi]
    if fungsi:
        baris += ["", "Fungsi yang direncanakan:"]
        baris += [f"    - {f}" for f in fungsi]
    baris += ['"""', ""]
    return "\n".join(baris)


# ---------------------------------------------------------------------
# File dengan isi nyata (siap pakai)
# ---------------------------------------------------------------------
FILE_ISI = {}

FILE_ISI[".gitignore"] = r'''.venv/
.env
__pycache__/
*.pyc
.pytest_cache/
bukti/*
!bukti/.gitkeep
.vscode/
'''

FILE_ISI[".env.example"] = r'''# Salin file ini menjadi .env lalu isi nilainya. Jangan commit file .env.

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=bimbel_db
DB_USER=bimbel_user
DB_PASSWORD=ganti_dengan_password_kuat

# OTP: "simulasi" (kode tampil di terminal) atau "email" (kirim lewat SMTP)
OTP_MODE=simulasi
OTP_EXPIRE_MINUTES=5
OTP_MAX_ATTEMPTS=3

# Keamanan login
MAX_LOGIN_ATTEMPTS=3
LOCK_MINUTES=5

# Email (dipakai jika OTP_MODE=email)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=

# Gemini (opsional)
GEMINI_API_KEY=
'''

FILE_ISI["requirements.txt"] = r'''# Database
psycopg[binary,pool]>=3.2

# Konfigurasi dan keamanan
python-dotenv
bcrypt

# Tampilan dan interaksi CLI
rich
questionary

# Validasi
email-validator

# PDF bukti pembayaran
reportlab>=4.2

# AI (Gemini)
google-genai

# Pengujian
pytest
'''

FILE_ISI["README.md"] = r'''# BIMBEL CERDAS (CLI)

Program CLI Python untuk manajemen bimbingan belajar: admin, tutor, dan siswa.

## Menjalankan

1. Buat dan aktifkan virtual environment, lalu `python -m pip install -r requirements.txt`
2. Salin `.env.example` menjadi `.env` dan isi nilainya
3. Buat database, lalu jalankan `sql/schema.sql` dan `sql/seed.sql`
4. `python buat_admin.py` (sekali saja)
5. Jalankan program dari folder proyek: `python -m app.main`

## Struktur

- `app/repositories/` : semua query SQL
- `app/services/`     : aturan bisnis
- `app/ui/`           : menu dan tampilan CLI
- `app/utils/`        : validasi, keamanan, format
- `sql/`              : schema dan seed
- `tests/`            : pengujian
'''

FILE_ISI["app/config.py"] = r'''"""Konfigurasi aplikasi. Semua nilai dibaca dari file .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

# OTP
OTP_MODE = os.getenv("OTP_MODE", "simulasi")          # simulasi | email
OTP_EXPIRE_MINUTES = int(os.getenv("OTP_EXPIRE_MINUTES", "5"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "3"))

# Login
MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "3"))
LOCK_MINUTES = int(os.getenv("LOCK_MINUTES", "5"))

# Email
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Folder keluaran
BUKTI_DIR = BASE_DIR / "bukti"
'''

FILE_ISI["app/db.py"] = r'''"""Koneksi PostgreSQL dengan connection pool.

Pemakaian:
    from app.db import koneksi

    with koneksi() as conn:
        baris = conn.execute("SELECT * FROM users WHERE id = %s", (1,)).fetchone()

Blok `with` melakukan commit otomatis, dan rollback jika terjadi error.
Hasil query berupa dict (nama kolom -> nilai).
"""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import DB_CONFIG

_pool = None


def get_pool():
    """Membuat pool saat pertama kali dibutuhkan (bukan saat import)."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            kwargs={
                **DB_CONFIG,
                "row_factory": dict_row,
                "options": "-c timezone=Asia/Jakarta",
            },
            min_size=1,
            max_size=5,
            open=True,
        )
    return _pool


def koneksi():
    """Context manager koneksi: commit otomatis, rollback jika error."""
    return get_pool().connection()


def tutup_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
'''

FILE_ISI["app/session.py"] = r'''"""Menyimpan pengguna yang sedang login selama program berjalan."""

_user = None


def set_user(user):
    """user: dict baris tabel users (minimal id, username, nama_lengkap, role)."""
    global _user
    _user = user


def get_user():
    return _user


def logout():
    global _user
    _user = None


def sudah_login():
    return _user is not None


def punya_role(*role):
    """Contoh: punya_role('admin') atau punya_role('tutor', 'admin')."""
    return _user is not None and _user["role"] in role
'''

FILE_ISI["app/main.py"] = r'''"""Titik masuk program. Jalankan dari folder proyek: python -m app.main"""
from app import db
from app.ui import menu_auth
from app.ui.console import console


def main():
    try:
        menu_auth.jalankan()
    except KeyboardInterrupt:
        console.print("\nProgram dihentikan.")
    finally:
        db.tutup_pool()


if __name__ == "__main__":
    main()
'''

FILE_ISI["app/ui/console.py"] = r'''"""Pembantu tampilan dasar berbasis rich."""
from rich.console import Console
from rich.panel import Panel

console = Console()


def judul(teks):
    console.print(Panel(f"[bold]{teks}[/bold]", border_style="cyan"))


def sukses(pesan):
    console.print(f"[bold green]✓[/bold green] {pesan}")


def gagal(pesan):
    console.print(f"[bold red]✗[/bold red] {pesan}")


def info(pesan):
    console.print(f"[bold cyan]i[/bold cyan] {pesan}")


def peringatan(pesan):
    console.print(f"[bold yellow]![/bold yellow] {pesan}")


def bersihkan_layar():
    console.clear()
'''

FILE_ISI["app/ui/tabel.py"] = r'''"""Pembantu menampilkan tabel dengan rich."""
from rich.table import Table

from app.ui.console import console


def tampilkan_tabel(judul, kolom, baris):
    """kolom: list nama kolom. baris: list of list/tuple nilai."""
    tabel = Table(title=judul, header_style="bold cyan")
    for nama in kolom:
        tabel.add_column(str(nama))
    for b in baris:
        tabel.add_row(*[str(x) for x in b])
    console.print(tabel)
'''

FILE_ISI["app/ui/menu_auth.py"] = r'''"""Menu awal: login, register, lupa password (kerangka)."""
import questionary

from app.ui.console import info, judul


def jalankan():
    while True:
        judul("BIMBEL CERDAS - SISTEM AKADEMIK")
        pilihan = questionary.select(
            "Menu utama",
            choices=["Login", "Register", "Lupa Password", "Keluar"],
        ).ask()
        if pilihan is None or pilihan == "Keluar":
            info("Sampai jumpa.")
            break
        info(f"Fitur '{pilihan}' belum dibuat.")
'''

FILE_ISI["app/utils/exceptions.py"] = r'''"""Exception khusus aplikasi. Lapisan UI menangkapnya dan menampilkan pesannya."""


class AppError(Exception):
    """Dasar semua error aplikasi. Pesan aman ditampilkan ke pengguna."""


class DataTidakValid(AppError):
    pass


class DataTidakDitemukan(AppError):
    pass


class DuplikatData(AppError):
    pass


class TidakDiizinkan(AppError):
    pass


class AkunTerkunci(AppError):
    pass


class KuotaPenuh(AppError):
    pass


class JadwalBentrok(AppError):
    pass
'''

FILE_ISI["app/utils/security.py"] = r'''"""Hash password dan pembuatan OTP."""
import secrets

import bcrypt


def hash_password(password):
    """Mengembalikan hash bcrypt (str). Password dibatasi 72 byte oleh bcrypt."""
    data = password.encode("utf-8")
    if len(data) > 72:
        raise ValueError("Password maksimal 72 byte.")
    return bcrypt.hashpw(data, bcrypt.gensalt()).decode("utf-8")


def verifikasi_password(password, hashed):
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def buat_otp(panjang=6):
    """OTP angka acak yang aman secara kriptografi, contoh '048213'."""
    return "".join(str(secrets.randbelow(10)) for _ in range(panjang))
'''

FILE_ISI["app/utils/validators.py"] = r'''"""Validasi input. Melempar DataTidakValid jika input salah."""
import re

from email_validator import EmailNotValidError, validate_email

from app.utils.exceptions import DataTidakValid


def validasi_username(username):
    username = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{4,30}", username):
        raise DataTidakValid("Username 4-30 karakter: huruf, angka, atau underscore.")
    return username


def validasi_email(email):
    try:
        return validate_email(email.strip(), check_deliverability=False).normalized
    except EmailNotValidError:
        raise DataTidakValid("Format email tidak valid.")


def validasi_password(password):
    if not 8 <= len(password) <= 64:
        raise DataTidakValid("Password harus 8-64 karakter.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise DataTidakValid("Password harus mengandung huruf dan angka.")
    return password


def validasi_no_hp(no_hp):
    bersih = re.sub(r"[\s-]", "", no_hp)
    if not re.fullmatch(r"(\+62|62|0)8\d{8,11}", bersih):
        raise DataTidakValid("Nomor HP tidak valid, contoh: 081234567890.")
    return bersih


def validasi_nominal(teks):
    try:
        nilai = int(str(teks).replace(".", "").strip())
    except ValueError:
        raise DataTidakValid("Nominal harus berupa angka.")
    if nilai <= 0:
        raise DataTidakValid("Nominal harus lebih dari 0.")
    return nilai


def validasi_nilai(teks):
    try:
        nilai = float(str(teks).replace(",", ".").strip())
    except ValueError:
        raise DataTidakValid("Nilai harus berupa angka.")
    if not 0 <= nilai <= 100:
        raise DataTidakValid("Nilai harus antara 0 sampai 100.")
    return nilai
'''

FILE_ISI["app/utils/formatters.py"] = r'''"""Format tampilan: rupiah, tanggal, persen."""
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
         "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def rupiah(angka):
    """450000 -> 'Rp 450.000'"""
    return "Rp " + f"{int(round(angka)):,}".replace(",", ".")


def tanggal(d):
    """date/datetime -> '21 Okt 2026'"""
    return f"{d.day:02d} {BULAN[d.month - 1]} {d.year}"


def persen(nilai):
    return f"{nilai:.1f}%"
'''

FILE_ISI["tests/test_validators.py"] = r'''import pytest

from app.utils.exceptions import DataTidakValid
from app.utils.validators import (
    validasi_email,
    validasi_no_hp,
    validasi_nominal,
    validasi_nilai,
    validasi_password,
    validasi_username,
)


def test_username_valid():
    assert validasi_username("budi01") == "budi01"


@pytest.mark.parametrize("u", ["ab", "budi santoso", "budi@01", "x" * 31])
def test_username_tidak_valid(u):
    with pytest.raises(DataTidakValid):
        validasi_username(u)


def test_email():
    assert validasi_email("budi@email.com") == "budi@email.com"
    with pytest.raises(DataTidakValid):
        validasi_email("bukan-email")


def test_password():
    assert validasi_password("rahasia123") == "rahasia123"
    with pytest.raises(DataTidakValid):
        validasi_password("pendek1")
    with pytest.raises(DataTidakValid):
        validasi_password("hanyahuruf")


def test_no_hp():
    assert validasi_no_hp("0812-3456-7890") == "081234567890"
    with pytest.raises(DataTidakValid):
        validasi_no_hp("12345")


def test_nominal_dan_nilai():
    assert validasi_nominal("450.000") == 450000
    with pytest.raises(DataTidakValid):
        validasi_nominal("-5")
    assert validasi_nilai("88,5") == 88.5
    with pytest.raises(DataTidakValid):
        validasi_nilai("101")
'''

FILE_ISI["tests/test_security.py"] = r'''from app.utils.security import buat_otp, hash_password, verifikasi_password


def test_hash_dan_verifikasi():
    h = hash_password("rahasia123")
    assert h != "rahasia123"
    assert verifikasi_password("rahasia123", h)
    assert not verifikasi_password("salah", h)


def test_otp_enam_digit():
    otp = buat_otp()
    assert len(otp) == 6 and otp.isdigit()
'''

FILE_ISI["tests/test_formatters.py"] = r'''from datetime import date

from app.utils.formatters import persen, rupiah, tanggal


def test_rupiah():
    assert rupiah(450000) == "Rp 450.000"
    assert rupiah(0) == "Rp 0"


def test_tanggal():
    assert tanggal(date(2026, 10, 21)) == "21 Okt 2026"


def test_persen():
    assert persen(91.04) == "91.0%"
'''


# ---------------------------------------------------------------------
# File kerangka: path -> (deskripsi, fungsi yang direncanakan)
# ---------------------------------------------------------------------
FILE_STUB = {
    # ---- repositories: hanya berisi query SQL ----
    "app/repositories/user_repo.py": (
        "Query tabel users.",
        ["buat_user", "cari_by_username", "cari_by_id", "cari_by_email",
         "daftar_by_status", "set_status", "catat_gagal_login", "reset_gagal_login",
         "set_password", "set_terverifikasi", "set_persetujuan"]),
    "app/repositories/otp_repo.py": (
        "Query tabel otp_codes.",
        ["simpan_otp", "ambil_otp_aktif", "tambah_percobaan", "tandai_terpakai",
         "hitung_kirim_terakhir"]),
    "app/repositories/profile_repo.py": (
        "Query tabel students dan tutors.",
        ["buat_profil_siswa", "buat_profil_tutor", "ubah_profil_siswa",
         "ubah_profil_tutor", "terbitkan_nis", "terbitkan_kode_tutor",
         "daftar_siswa", "daftar_tutor", "cari_siswa"]),
    "app/repositories/program_repo.py": (
        "Query tabel programs dan rooms.",
        ["tambah_program", "ubah_program", "tutup_program", "daftar_program",
         "daftar_program_buka_dengan_kuota", "tambah_ruang", "daftar_ruang"]),
    "app/repositories/schedule_repo.py": (
        "Query tabel schedules.",
        ["tambah_jadwal", "ubah_jadwal", "nonaktifkan_jadwal", "jadwal_tutor",
         "jadwal_siswa", "jadwal_program", "cek_bentrok"]),
    "app/repositories/enrollment_repo.py": (
        "Query tabel enrollments.",
        ["kunci_program", "hitung_terisi", "buat_enrollment", "daftar_menunggu",
         "set_status", "enrollment_siswa", "siswa_aktif_di_program"]),
    "app/repositories/billing_repo.py": (
        "Query tabel invoices dan payments dengan Virtual Account dan pembayaran penuh.",
        ["buat_tagihan_bulanan", "daftar_tagihan_siswa", "buat_pembayaran_va",
         "tandai_sudah_bayar", "daftar_pembayaran_menunggu", "set_status_pembayaran",
         "hitung_ulang_status_invoice", "data_bukti"]),
    "app/repositories/academic_repo.py": (
        "Query tabel class_sessions, attendances, dan grades.",
        ["buat_pertemuan", "pertemuan_berikutnya", "simpan_absensi",
         "absensi_siswa", "tambah_nilai", "ubah_nilai", "nilai_siswa"]),
    "app/repositories/engagement_repo.py": (
        "Query tabel announcements.",
        ["buat_pengumuman", "daftar_pengumuman"]),
    "app/repositories/log_repo.py": (
        "Query tabel activity_logs.",
        ["catat", "daftar_terbaru"]),
    "app/repositories/report_repo.py": (
        "Membaca view laporan.",
        ["pemasukan_bulanan", "rekap_kehadiran", "nilai_akhir_siswa",
         "ringkasan_dashboard_admin"]),

    # ---- services: aturan bisnis, memanggil repository ----
    "app/services/auth_service.py": (
        "Register, login, ganti dan reset password.",
        ["register(role, data)", "login(username, password)", "ganti_password",
         "reset_password"]),
    "app/services/otp_service.py": (
        "Pembuatan, pengiriman, dan verifikasi OTP.",
        ["kirim_otp(user_id, tujuan)", "verifikasi_otp(user_id, kode, tujuan)"]),
    "app/services/email_service.py": (
        "Pengiriman email OTP (SMTP) atau simulasi di terminal sesuai OTP_MODE.",
        ["kirim_otp_email(email, kode)", "tampilkan_otp_simulasi(kode)"]),
    "app/services/approval_service.py": (
        "Pusat Konfirmasi admin: akun, pendaftaran program, dan pembayaran.",
        ["setujui_akun", "tolak_akun", "setujui_enrollment", "tolak_enrollment"]),
    "app/services/enrollment_service.py": (
        "Pendaftaran siswa ke program (kuota aman lewat transaksi).",
        ["daftar_program(student_id, program_id)", "batalkan(enrollment_id)"]),
    "app/services/billing_service.py": (
        "Tagihan dan simulasi pembayaran Virtual Account penuh.",
        ["buat_tagihan_bulanan", "mulai_pembayaran_va", "konfirmasi_sudah_bayar",
         "konfirmasi_admin", "tolak_admin", "cetak_bukti"]),
    "app/services/academic_service.py": (
        "Pertemuan, absensi, dan nilai (dengan pengecekan hak akses tutor).",
        ["buka_pertemuan", "isi_absensi", "input_nilai", "rapor_siswa"]),
    "app/services/report_service.py": (
        "Menyusun laporan dan ekspor CSV.",
        ["laporan_bulanan", "ekspor_csv"]),
    "app/services/ai_service.py": (
        "Integrasi Gemini untuk tanya materi (opsional).",
        ["tanya_materi"]),

    # ---- ui: menu per role ----
    "app/ui/menu_admin.py": (
        "Menu dan layar untuk role admin.",
        ["jalankan()", "menu_konfirmasi", "menu_siswa", "menu_tutor", "menu_program",
         "menu_jadwal", "menu_pembayaran", "menu_laporan"]),
    "app/ui/menu_tutor.py": (
        "Menu dan layar untuk role tutor.",
        ["jalankan()", "menu_jadwal", "menu_absensi", "menu_nilai", "menu_catatan_materi"]),
    "app/ui/menu_siswa.py": (
        "Menu dan layar untuk role siswa.",
        ["jalankan()", "menu_katalog", "menu_jadwal", "menu_nilai",
         "menu_pembayaran", "menu_catatan_materi"]),
}

FOLDER_KOSONG = ["sql", "bukti"]
FILE_KOSONG = ["bukti/.gitkeep"]
PAKET_PYTHON = ["app", "app/repositories", "app/services", "app/ui", "app/utils", "tests"]


# ---------------------------------------------------------------------
# Proses pembuatan
# ---------------------------------------------------------------------
def tulis(path_relatif, isi, hasil):
    path = BASE / path_relatif
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        hasil["dilewati"].append(path_relatif)
        return
    path.write_text(isi, encoding="utf-8")
    hasil["dibuat"].append(path_relatif)


def cetak_pohon(root, awalan=""):
    abaikan = {".venv", "__pycache__", ".git", ".pytest_cache", "node_modules"}
    isi = sorted(
        (p for p in root.iterdir() if p.name not in abaikan),
        key=lambda p: (p.is_file(), p.name),
    )
    for i, p in enumerate(isi):
        terakhir = i == len(isi) - 1
        print(f"{awalan}{'└── ' if terakhir else '├── '}{p.name}{'/' if p.is_dir() else ''}")
        if p.is_dir():
            cetak_pohon(p, awalan + ("    " if terakhir else "│   "))


def main():
    hasil = {"dibuat": [], "dilewati": []}

    for folder in FOLDER_KOSONG:
        (BASE / folder).mkdir(exist_ok=True)

    for paket in PAKET_PYTHON:
        tulis(f"{paket}/__init__.py", "", hasil)

    for path, isi in FILE_ISI.items():
        tulis(path, isi, hasil)

    for path, (deskripsi, fungsi) in FILE_STUB.items():
        tulis(path, stub(deskripsi, fungsi), hasil)

    for path in FILE_KOSONG:
        tulis(path, "", hasil)

    print(f"\nDibuat    : {len(hasil['dibuat'])} file")
    print(f"Dilewati  : {len(hasil['dilewati'])} file (sudah ada, tidak ditimpa)")
    if hasil["dilewati"]:
        for p in hasil["dilewati"]:
            print(f"   - {p}")
    print(f"\n{BASE.name}/")
    cetak_pohon(BASE)
    print("\nLangkah berikut: salin .env.example menjadi .env lalu isi nilainya.")


if __name__ == "__main__":
    main()
