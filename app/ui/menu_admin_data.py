"""Submenu Manajemen Akun, Data Siswa, dan Data Tutor untuk admin."""

import psycopg
import questionary
from questionary import Choice, Separator, Style
from rich.align import Align
from rich.panel import Panel
from rich.table import Table

from app import session
from app.repositories import enrollment_repo, program_repo
from app.services import admin_management_service
from app.ui.console import console, bersihkan_layar, gagal, info, peringatan, sukses


GAYA = Style([
    ("qmark", "fg:#00ffff bold"),
    ("question", "fg:#ffffff bold"),
    ("answer", "fg:#00ffff bold"),
    ("pointer", "fg:#00ffff bold"),
    ("highlighted", "fg:#00ffff bold"),
    ("selected", "fg:#00ffff"),
    ("separator", "fg:#444444"),
    ("instruction", "fg:#888888 italic"),
])

_STATUS = [
    ("Belum verifikasi", "belum_verifikasi"),
    ("Menunggu konfirmasi", "menunggu_konfirmasi"),
    ("Aktif", "aktif"),
    ("Ditolak", "ditolak"),
    ("Nonaktif", "nonaktif"),
]


def _header(judul: str, subjudul: str):
    console.print(Panel(
        Align.center(f"[bold cyan]S I B I M A[/bold cyan]\n[bold white]{judul.upper()}[/bold white]\n[dim]{subjudul}[/dim]"),
        border_style="cyan", padding=(1, 3), expand=True,
    ))


def _pause():
    try:
        input("\nTekan Enter untuk kembali...")
    except (EOFError, KeyboardInterrupt):
        return


def _admin_aktif() -> bool:
    return session.punya_role("admin")


def _tabel_akun(rows):
    table = Table(title="Daftar Akun", header_style="bold cyan", expand=True)
    for name in ["ID", "Role", "Nama", "Username", "Status", "Email ✓", "NIS / Kode", "Kunci"]:
        table.add_column(name, overflow="fold")
    for row in rows:
        lock = "Terkunci" if row.get("locked_until") else ("Percobaan gagal" if row.get("failed_attempts", 0) else "-")
        identitas = row.get("nis") or row.get("kode_tutor") or "-"
        table.add_row(
            str(row["id"]), str(row["role"]), str(row["nama_lengkap"]),
            str(row["username"]), str(row["status"]),
            "Ya" if row.get("email_verified") else "Tidak", str(identitas), lock,
        )
    console.print(table)


def _ambil_filter_akun():
    role = questionary.select(
        "Filter role:",
        choices=[Choice("Semua role", "semua"), Choice("Siswa", "siswa"), Choice("Tutor", "tutor"), Choice("Admin", "admin"), Choice("Kembali", "kembali")],
        style=GAYA, qmark="⚡", pointer="▶",
    ).ask()
    if role is None or role == "kembali":
        return None
    status = questionary.select(
        "Filter status:",
        choices=[Choice("Semua status", "semua")] + [Choice(label, value) for label, value in _STATUS] + [Separator("────────"), Choice("Kembali", "kembali")],
        style=GAYA, qmark="⚡", pointer="▶",
    ).ask()
    if status is None or status == "kembali":
        return None
    return (None if role == "semua" else role, None if status == "semua" else status)


def _pilih_akun(*, role=None, status=None, hanya_siswa_tutor=False, status_diizinkan=None, petunjuk="Pilih akun:"):
    rows = admin_management_service.daftar_akun(role=role, status=status)
    if hanya_siswa_tutor:
        rows = [r for r in rows if r["role"] in {"siswa", "tutor"}]
    if status_diizinkan is not None:
        rows = [r for r in rows if r["status"] in status_diizinkan]
    if not rows:
        peringatan("Tidak ada akun yang cocok dengan filter.")
        return None
    _tabel_akun(rows)
    pilihan = questionary.select(
        petunjuk,
        choices=[Choice(
            f"ID {r['id']} • {r['nama_lengkap']} • {r['role']} • {r['status']}",
            value=r["id"],
        ) for r in rows] + [Separator("────────────────"), Choice("Kembali", "kembali")],
        style=GAYA, qmark="⚡", pointer="▶",
    ).ask()
    if type(pilihan) is not int:
        return None
    return next((r for r in rows if r["id"] == pilihan), None)


def menu_manajemen_akun_admin():
    if not _admin_aktif():
        peringatan("Akses ditolak. Login sebagai admin aktif terlebih dahulu.")
        return
    while _admin_aktif():
        bersihkan_layar()
        _header("Manajemen Akun", "DAFTAR, STATUS, KUNCI LOGIN, DAN RESET PASSWORD")
        pilihan = questionary.select(
            "Pilih tindakan:",
            choices=[
                Choice("Daftar semua akun (filter role / status)", "daftar"),
                Choice("Nonaktifkan / aktifkan akun", "status"),
                Choice("Buka kunci akun", "unlock"),
                Choice("Reset password akun", "reset"),
                Separator("────────────────"), Choice("Kembali ke dashboard", "kembali"),
            ], style=GAYA, qmark="⚡", pointer="▶",
        ).ask()
        if pilihan is None or pilihan == "kembali":
            return
        try:
            if pilihan == "daftar":
                filters = _ambil_filter_akun()
                if filters is None:
                    continue
                rows = admin_management_service.daftar_akun(*filters)
                bersihkan_layar(); _header("Manajemen Akun", "HASIL FILTER")
                if rows:
                    _tabel_akun(rows)
                else:
                    peringatan("Tidak ada akun yang cocok dengan filter.")
                _pause()
            elif pilihan == "status":
                target = _pilih_akun(
                    hanya_siswa_tutor=True,
                    status_diizinkan={"aktif", "nonaktif"},
                    petunjuk="Pilih akun aktif/nonaktif yang statusnya akan diubah:",
                )
                if target is None:
                    _pause(); continue
                if target["status"] not in {"aktif", "nonaktif"} or target["role"] not in {"siswa", "tutor"}:
                    peringatan("Hanya akun siswa/tutor berstatus aktif atau nonaktif yang dapat diubah di sini.")
                    _pause(); continue
                status_baru = "nonaktif" if target["status"] == "aktif" else "aktif"
                yakin = questionary.confirm(
                    f"{status_baru.capitalize()}kan akun {target['username']}? Riwayat pendaftaran tidak dihapus.",
                    default=False, style=GAYA,
                ).ask()
                if yakin:
                    ok, pesan = admin_management_service.ubah_status_akun(target["id"], status_baru)
                    sukses(pesan) if ok else gagal(pesan)
                else:
                    info("Perubahan status dibatalkan.")
                _pause()
            elif pilihan == "unlock":
                target = _pilih_akun(petunjuk="Pilih akun yang akan dibuka kuncinya:")
                if target is None:
                    _pause(); continue
                ok, pesan = admin_management_service.buka_kunci_akun(target["id"])
                sukses(pesan) if ok else peringatan(pesan)
                _pause()
            elif pilihan == "reset":
                target = _pilih_akun(petunjuk="Pilih akun yang password-nya akan direset:")
                if target is None:
                    _pause(); continue
                yakin = questionary.confirm(
                    f"Reset password akun {target['username']}? Password sementara hanya ditampilkan sekali.",
                    default=False, style=GAYA,
                ).ask()
                if yakin:
                    ok, pesan, password = admin_management_service.reset_password_akun(target["id"])
                    if ok:
                        console.print(Panel(
                            f"[bold green]{pesan}[/bold green]\n\n[bold yellow]Password sementara:[/] [bold white]{password}[/bold white]\n\n[dim]Catat dan sampaikan lewat kanal aman. Jangan kirimkan di grup. Pemilik akun harus menggantinya saat login.[/dim]",
                            title="RESET PASSWORD BERHASIL", border_style="green", padding=(1, 2),
                        ))
                    else:
                        gagal(pesan)
                else:
                    info("Reset password dibatalkan.")
                _pause()
        except (psycopg.Error, PermissionError, ValueError) as exc:
            gagal(f"Operasi manajemen akun gagal ({type(exc).__name__}).")
            _pause()


def _tabel_siswa(rows, title="Daftar Siswa"):
    table = Table(title=title, header_style="bold cyan", expand=True)
    for col in ["User ID", "NIS", "Nama", "Jenjang", "Program aktif/menunggu", "Status"]:
        table.add_column(col, overflow="fold")
    for row in rows:
        table.add_row(
            str(row.get("user_id", "-")), str(row.get("nis") or "Belum terbit"),
            str(row.get("nama_lengkap") or "-"), str(row.get("jenjang") or "-"),
            str(row.get("program") or "-"), str(row.get("status") or "-"),
        )
    console.print(table)


def _pilih_siswa(*, cari=None, jenjang=None, program_id=None, status=None, petunjuk="Pilih siswa:"):
    rows = admin_management_service.daftar_siswa(jenjang=jenjang, program_id=program_id, status=status, cari=cari)
    if not rows:
        peringatan("Tidak ditemukan siswa yang cocok.")
        return None
    _tabel_siswa(rows)
    pilihan = questionary.select(
        petunjuk,
        choices=[Choice(
            f"{r.get('nis') or 'Tanpa NIS'} • {r['nama_lengkap']} • {r.get('jenjang') or '-'} • {r['status']}", value=r["user_id"]
        ) for r in rows] + [Separator("────────────────"), Choice("Kembali", "kembali")],
        style=GAYA, qmark="⚡", pointer="▶",
    ).ask()
    if type(pilihan) is not int:
        return None
    return next((r for r in rows if r["user_id"] == pilihan), None)


def _detail_siswa(row):
    detail = admin_management_service.detail_siswa(row["user_id"])
    if not detail:
        peringatan("Data siswa tidak ditemukan.")
        return
    labels = [
        ("User ID", detail.get("user_id")), ("NIS", detail.get("nis") or "Belum terbit"),
        ("Nama", detail.get("nama_lengkap")), ("Username", detail.get("username")),
        ("Email", detail.get("email")), ("Status akun", detail.get("status")),
        ("Email terverifikasi", "Ya" if detail.get("email_verified") else "Tidak"),
        ("Jenjang", detail.get("jenjang") or "-"), ("Sekolah", detail.get("sekolah") or "-"),
        ("No. HP", detail.get("no_hp") or "-"), ("Nama wali", detail.get("nama_wali") or "-"),
        ("Program saat ini", detail.get("program") or "Belum ada program"),
    ]
    table = Table(title="Detail Siswa", header_style="bold cyan", show_header=True, expand=True)
    table.add_column("Data", style="cyan", width=24); table.add_column("Nilai", overflow="fold")
    for label, value in labels:
        table.add_row(label, str(value if value is not None else "-"))
    console.print(table)
    history = enrollment_repo.enrollment_siswa(row["user_id"])
    hist = Table(title="Riwayat Pendaftaran Program", header_style="bold cyan", expand=True)
    for col in ["ID", "Program", "Status", "Tanggal daftar", "Diproses"]:
        hist.add_column(col, overflow="fold")
    for item in history:
        hist.add_row(
            str(item["enrollment_id"]), str(item["nama_program"]), str(item["status"]),
            str(item.get("created_at") or "-"), str(item.get("processed_at") or "-"),
        )
    if history:
        console.print(hist)
    else:
        info("Siswa belum memiliki riwayat pendaftaran program.")


def _filter_siswa():
    jenjang = questionary.text("Filter jenjang (kosong = semua):", style=GAYA).ask()
    if jenjang is None:
        return None
    try:
        programs = program_repo.daftar_program()
    except psycopg.Error:
        gagal("Gagal mengambil program untuk filter.")
        return None
    program_choices = [Choice("Semua program", "semua")] + [
        Choice(f"{p['kode']} • {p['nama']} • {p['status']}", p["id"]) for p in programs
    ] + [Separator("────────"), Choice("Kembali", "kembali")]
    pid = questionary.select("Filter program:", choices=program_choices, style=GAYA, qmark="⚡", pointer="▶").ask()
    if pid is None or pid == "kembali":
        return None
    status = questionary.select(
        "Filter status akun siswa:",
        choices=[Choice("Semua status", "semua")] + [Choice(label, value) for label, value in _STATUS] + [Separator("────────"), Choice("Kembali", "kembali")],
        style=GAYA, qmark="⚡", pointer="▶",
    ).ask()
    if status is None or status == "kembali":
        return None
    return jenjang.strip() or None, (None if pid == "semua" else pid), (None if status == "semua" else status)


def _edit_siswa(row):
    detail = admin_management_service.detail_siswa(row["user_id"])
    if not detail:
        peringatan("Siswa tidak ditemukan."); return
    console.print(Panel("Kosongkan kolom opsional untuk menghapus nilai lama. Untuk nama lengkap, isi nama yang valid.", border_style="yellow"))
    data = {}
    specs = [
        ("nama_lengkap", "Nama lengkap", detail.get("nama_lengkap") or ""),
        ("jenjang", "Jenjang", detail.get("jenjang") or ""),
        ("sekolah", "Sekolah", detail.get("sekolah") or ""),
        ("no_hp", "Nomor HP", detail.get("no_hp") or ""),
        ("nama_wali", "Nama wali", detail.get("nama_wali") or ""),
    ]
    for key, prompt, default in specs:
        value = questionary.text(f"{prompt}:", default=default, style=GAYA).ask()
        if value is None:
            info("Perubahan dibatalkan."); return
        data[key] = value
    yakin = questionary.confirm("Simpan perubahan profil siswa?", default=False, style=GAYA).ask()
    if not yakin:
        info("Perubahan dibatalkan."); return
    ok, pesan = admin_management_service.ubah_siswa(row["user_id"], data)
    sukses(pesan) if ok else gagal(pesan)


def menu_data_siswa_admin():
    if not _admin_aktif():
        peringatan("Akses ditolak. Login sebagai admin aktif terlebih dahulu."); return
    while _admin_aktif():
        bersihkan_layar(); _header("Data Siswa", "PENCARIAN DAN PENGELOLAAN PROFIL SISWA")
        pilihan = questionary.select(
            "Pilih tindakan:",
            choices=[
                Choice("Lihat daftar siswa", "daftar"),
                Choice("Cari siswa (nama / NIS)", "cari"),
                Choice("Filter (jenjang / program / status)", "filter"),
                Choice("Lihat detail siswa dan riwayat program", "detail"),
                Choice("Ubah data siswa", "ubah"),
                Choice("Nonaktifkan akun siswa", "nonaktif"),
                Separator("────────────────"), Choice("Kembali ke dashboard", "kembali"),
            ], style=GAYA, qmark="⚡", pointer="▶",
        ).ask()
        if pilihan is None or pilihan == "kembali": return
        try:
            if pilihan == "daftar":
                rows = admin_management_service.daftar_siswa()
                _tabel_siswa(rows); _pause()
            elif pilihan == "cari":
                teks = questionary.text("Masukkan nama atau NIS:", style=GAYA).ask()
                if teks is None: continue
                rows = admin_management_service.daftar_siswa(cari=teks)
                _tabel_siswa(rows, "Hasil Pencarian Siswa") if rows else peringatan("Siswa tidak ditemukan.")
                _pause()
            elif pilihan == "filter":
                filters = _filter_siswa()
                if filters is None: continue
                rows = admin_management_service.daftar_siswa(jenjang=filters[0], program_id=filters[1], status=filters[2])
                _tabel_siswa(rows, "Hasil Filter Siswa") if rows else peringatan("Tidak ada siswa sesuai filter.")
                _pause()
            elif pilihan == "detail":
                row = _pilih_siswa()
                if row:
                    bersihkan_layar(); _header("Data Siswa", "DETAIL PROFIL DAN RIWAYAT PROGRAM")
                    _detail_siswa(row); _pause()
            elif pilihan == "ubah":
                row = _pilih_siswa(petunjuk="Pilih siswa yang profilnya akan diubah:")
                if row:
                    bersihkan_layar(); _header("Data Siswa", "UBAH PROFIL SISWA")
                    _edit_siswa(row); _pause()
            elif pilihan == "nonaktif":
                row = _pilih_siswa(status="aktif", petunjuk="Pilih siswa aktif yang akan dinonaktifkan:")
                if row:
                    yakin = questionary.confirm(
                        f"Nonaktifkan akun {row['nama_lengkap']}? Riwayat enrollment dan tagihan tetap disimpan.",
                        default=False, style=GAYA,
                    ).ask()
                    if yakin:
                        ok, pesan = admin_management_service.ubah_status_akun(row["user_id"], "nonaktif")
                        sukses(pesan) if ok else gagal(pesan)
                    else: info("Penonaktifan dibatalkan.")
                    _pause()
        except (psycopg.Error, PermissionError, ValueError) as exc:
            gagal(f"Operasi data siswa gagal ({type(exc).__name__})."); _pause()


def _tabel_tutor(rows, title="Daftar Tutor"):
    table = Table(title=title, header_style="bold cyan", expand=True)
    for col in ["User ID", "Kode Tutor", "Nama", "Keahlian", "Jadwal aktif", "Program", "Status"]:
        table.add_column(col, overflow="fold")
    for row in rows:
        table.add_row(
            str(row.get("user_id", "-")), str(row.get("kode_tutor") or "Belum terbit"),
            str(row.get("nama_lengkap") or "-"), str(row.get("keahlian") or "-"),
            str(row.get("jumlah_jadwal", 0)), str(row.get("program") or "-"), str(row.get("status") or "-"),
        )
    console.print(table)


def _pilih_tutor(petunjuk="Pilih tutor:"):
    rows = admin_management_service.daftar_tutor()
    if not rows:
        peringatan("Belum ada data tutor."); return None
    _tabel_tutor(rows)
    pilihan = questionary.select(
        petunjuk,
        choices=[Choice(
            f"{r.get('kode_tutor') or 'Tanpa kode'} • {r['nama_lengkap']} • {r['status']}", value=r["user_id"]
        ) for r in rows] + [Separator("────────────────"), Choice("Kembali", "kembali")],
        style=GAYA, qmark="⚡", pointer="▶",
    ).ask()
    if type(pilihan) is not int: return None
    return next((r for r in rows if r["user_id"] == pilihan), None)


def _detail_tutor(row):
    detail = admin_management_service.detail_tutor(row["user_id"])
    if not detail:
        peringatan("Data tutor tidak ditemukan."); return
    table = Table(title="Detail Tutor", header_style="bold cyan", expand=True)
    table.add_column("Data", style="cyan", width=24); table.add_column("Nilai", overflow="fold")
    for label, value in [
        ("User ID", detail.get("user_id")), ("Kode tutor", detail.get("kode_tutor") or "Belum terbit"),
        ("Nama", detail.get("nama_lengkap")), ("Username", detail.get("username")),
        ("Email", detail.get("email")), ("Status akun", detail.get("status")),
        ("Email terverifikasi", "Ya" if detail.get("email_verified") else "Tidak"),
        ("Keahlian", detail.get("keahlian") or "-"), ("No. HP", detail.get("no_hp") or "-"),
    ]:
        table.add_row(label, str(value if value is not None else "-"))
    console.print(table)
    jadwal = admin_management_service.jadwal_tutor(row["user_id"])
    tbl = Table(title="Jadwal Mengajar Tutor", header_style="bold cyan", expand=True)
    for col in ["ID", "Program", "Hari", "Jam", "Ruang", "Status"]:
        tbl.add_column(col, overflow="fold")
    for item in jadwal:
        tbl.add_row(
            str(item["id"]), f"{item['kode_program']} • {item['nama_program']}",
            item["hari"].capitalize(), f"{item['jam_mulai']}–{item['jam_selesai']}",
            item["ruang"], "Aktif" if item["aktif"] else "Nonaktif",
        )
    if jadwal: console.print(tbl)
    else: info("Tutor belum memiliki jadwal mengajar.")


def _edit_tutor(row):
    detail = admin_management_service.detail_tutor(row["user_id"])
    if not detail:
        peringatan("Tutor tidak ditemukan."); return
    console.print(Panel("Kosongkan keahlian atau nomor HP untuk menghapus nilai lama. Nama wajib diisi.", border_style="yellow"))
    data = {}
    for key, prompt, default in [
        ("nama_lengkap", "Nama lengkap", detail.get("nama_lengkap") or ""),
        ("keahlian", "Keahlian", detail.get("keahlian") or ""),
        ("no_hp", "Nomor HP", detail.get("no_hp") or ""),
    ]:
        value = questionary.text(f"{prompt}:", default=default, style=GAYA).ask()
        if value is None:
            info("Perubahan dibatalkan."); return
        data[key] = value
    yakin = questionary.confirm("Simpan perubahan profil tutor?", default=False, style=GAYA).ask()
    if not yakin:
        info("Perubahan dibatalkan."); return
    ok, pesan = admin_management_service.ubah_tutor(row["user_id"], data)
    sukses(pesan) if ok else gagal(pesan)


def menu_data_tutor_admin():
    if not _admin_aktif():
        peringatan("Akses ditolak. Login sebagai admin aktif terlebih dahulu."); return
    while _admin_aktif():
        bersihkan_layar(); _header("Data Tutor", "PROFIL TUTOR DAN JADWAL MENGAJAR")
        pilihan = questionary.select(
            "Pilih tindakan:",
            choices=[
                Choice("Lihat daftar tutor", "daftar"),
                Choice("Lihat detail dan jadwal mengajar", "detail"),
                Choice("Ubah data tutor", "ubah"),
                Choice("Nonaktifkan akun tutor", "nonaktif"),
                Separator("────────────────"), Choice("Kembali ke dashboard", "kembali"),
            ], style=GAYA, qmark="⚡", pointer="▶",
        ).ask()
        if pilihan is None or pilihan == "kembali": return
        try:
            if pilihan == "daftar":
                rows = admin_management_service.daftar_tutor()
                _tabel_tutor(rows); _pause()
            elif pilihan == "detail":
                row = _pilih_tutor()
                if row:
                    bersihkan_layar(); _header("Data Tutor", "DETAIL DAN JADWAL MENGAJAR")
                    _detail_tutor(row); _pause()
            elif pilihan == "ubah":
                row = _pilih_tutor("Pilih tutor yang profilnya akan diubah:")
                if row:
                    bersihkan_layar(); _header("Data Tutor", "UBAH PROFIL TUTOR")
                    _edit_tutor(row)
                    _pause()
            elif pilihan == "nonaktif":
                row = _pilih_tutor("Pilih tutor aktif yang akan dinonaktifkan:")
                if row:
                    if row["status"] != "aktif":
                        peringatan("Tutor tersebut tidak berstatus aktif.")
                    else:
                        console.print(Panel(
                            "Akun tutor akan dinonaktifkan, tetapi jadwal dan riwayat akademik tetap disimpan. Pastikan penjadwalan ulang dilakukan bila diperlukan.",
                            border_style="yellow",
                        ))
                        yakin = questionary.confirm(f"Nonaktifkan akun {row['nama_lengkap']}?", default=False, style=GAYA).ask()
                        if yakin:
                            ok, pesan = admin_management_service.ubah_status_akun(row["user_id"], "nonaktif")
                            sukses(pesan) if ok else gagal(pesan)
                        else: info("Penonaktifan dibatalkan.")
                    _pause()
        except (psycopg.Error, PermissionError, ValueError) as exc:
            gagal(f"Operasi data tutor gagal ({type(exc).__name__})."); _pause()
