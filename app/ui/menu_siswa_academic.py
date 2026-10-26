"""Submenu akademik dan profil siswa dengan tampilan per layar."""

from datetime import date, datetime
from pathlib import Path
import re

import questionary
from questionary import Choice, Separator, Style
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.services import auth_service, student_service
from app.ui.console import bersihkan_layar, console, gagal, info, peringatan, sukses
from app.utils.formatters import rupiah, tanggal


GAYA = Style([
    ("qmark", "fg:#22d3ee bold"),
    ("question", "fg:#ffffff bold"),
    ("answer", "fg:#22d3ee bold"),
    ("pointer", "fg:#22d3ee bold"),
    ("highlighted", "fg:#22d3ee bold"),
    ("selected", "fg:#22d3ee"),
    ("separator", "fg:#475569"),
    ("instruction", "fg:#94a3b8 italic"),
])


HARI = ["senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu"]
HARI_LABEL = {h: h.capitalize() for h in HARI}
STATUS_ABSENSI = {"H": "Hadir", "I": "Izin", "S": "Sakit", "A": "Alpa"}


def _jeda(pesan="Tekan Enter untuk kembali..."):
    try:
        input(f"\n{pesan}")
    except (EOFError, KeyboardInterrupt):
        pass


def _header(judul: str, subjudul: str = ""):
    bersihkan_layar()
    isi = f"[bold cyan]S I B I M A[/bold cyan]\n[bold white]{judul.upper()}[/bold white]"
    if subjudul:
        isi += f"\n[dim]{subjudul}[/dim]"
    console.print(Panel(isi, border_style="cyan", padding=(1, 3), expand=True))


def _hasil(ok: bool, value, label: str):
    if ok:
        return value
    _header(label)
    gagal(str(value))
    _jeda()
    return None


def _nilai(value, digits=1):
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _tanggal(value):
    if not value:
        return "—"
    if isinstance(value, (date, datetime)):
        return tanggal(value.date() if isinstance(value, datetime) else value)
    return str(value)


def _waktu(value):
    if value is None:
        return "—"
    return value.strftime("%H:%M") if hasattr(value, "strftime") else str(value)[:5]


def _tabel_paginasi(judul, rows, kolom, render_row, *, page_size=10, subjudul="", back_label="Kembali"):
    """Render tabel data bertahap supaya output terminal tidak bertumpuk."""
    if not rows:
        _header(judul, subjudul)
        info("Belum ada data yang dapat ditampilkan.")
        _jeda()
        return
    page = 0
    total_pages = max(1, (len(rows) + page_size - 1) // page_size)
    while True:
        start = page * page_size
        current = rows[start:start + page_size]
        keterangan = f"Halaman {page + 1} dari {total_pages} • {len(rows)} data"
        if subjudul:
            keterangan = f"{subjudul} • {keterangan}"
        _header(judul, keterangan)
        table = Table(show_header=True, header_style="bold cyan", expand=True, box=None, pad_edge=False)
        for col, opts in kolom:
            table.add_column(col, **opts)
        for row in current:
            table.add_row(*render_row(row))
        console.print(Panel(table, border_style="bright_blue", padding=(1, 1), expand=True))

        choices = []
        if page > 0:
            choices.append(Choice("← Halaman sebelumnya", value="prev"))
        if page < total_pages - 1:
            choices.append(Choice("Halaman berikutnya →", value="next"))
        choices.append(Choice(back_label, value="back"))
        selected = questionary.select("Navigasi data:", choices=choices, style=GAYA, qmark="◆", pointer="▶").ask()
        if selected == "prev":
            page -= 1
        elif selected == "next":
            page += 1
        else:
            return


def _pilih_data(prompt, rows, labeler, value_key, *, page_size=8):
    """Select dengan maksimal delapan entri di layar sekaligus."""
    if not rows:
        return None
    index = 0
    max_page = (len(rows) - 1) // page_size
    while True:
        start = index * page_size
        part = rows[start:start + page_size]
        choices = [Choice(labeler(row), value=row[value_key]) for row in part]
        _header("PILIH DATA", f"{prompt} • Halaman {index + 1}/{max_page + 1} • {len(rows)} data")
        if index > 0:
            choices.append(Separator("────────────────────────"))
            choices.append(Choice("← Halaman sebelumnya", value="__prev__"))
        if index < max_page:
            choices.append(Choice("Halaman berikutnya →", value="__next__"))
        choices.append(Separator("────────────────────────"))
        choices.append(Choice("Kembali", value="__back__"))
        selected = questionary.select(
            f"{prompt} (halaman {index + 1}/{max_page + 1})",
            choices=choices, style=GAYA, qmark="◆", pointer="▶",
            instruction=" (↑/↓ untuk memilih, Enter untuk membuka)",
        ).ask()
        if selected == "__next__":
            index += 1
        elif selected == "__prev__":
            index -= 1
        elif selected == "__back__" or selected is None:
            return None
        else:
            return selected


def _program_akademik(*, aktif_saja=False):
    if aktif_saja:
        ok, payload = student_service.kelas_saya()
        if ok:
            payload = [
                {**row, "status_enrollment": row.get("status")}
                for row in payload if row.get("status") == "aktif"
            ]
    else:
        ok, payload = student_service.program_akademik()
    programs = _hasil(ok, payload, "PILIH PROGRAM")
    if programs is None:
        return None
    if not programs:
        _header("PROGRAM AKADEMIK")
        peringatan("Belum ada program aktif/selesai. Fitur ini tersedia setelah pendaftaran disetujui.")
        _jeda()
        return None
    chosen = _pilih_data(
        "Pilih program",
        programs,
        lambda r: f"{r['nama_program']} | {r['jenjang']} | {r['status_enrollment'].upper()}",
        "program_id",
    )
    if chosen is None:
        return None
    return next((p for p in programs if p["program_id"] == chosen), None)



def pilih_data_paginasi(prompt, rows, labeler, value_key, *, page_size=8):
    """API helper untuk menu siswa lain yang membutuhkan daftar pilihan panjang."""
    return _pilih_data(prompt, rows, labeler, value_key, page_size=page_size)


def tampilkan_katalog_paginasi(programs):
    _tabel_paginasi(
        "KATALOG PROGRAM", programs,
        [("Kode", {"width": 8}), ("Nama program", {"min_width": 24}), ("Jenjang", {"width": 12}), ("Biaya/bulan", {"min_width": 16, "justify": "right"}), ("Kuota", {"width": 12, "justify": "center"}), ("Deskripsi", {"min_width": 24})],
        lambda p: (str(p.get("kode", "—")), str(p.get("nama", "—")), str(p.get("jenjang", "—")), rupiah(p.get("harga_bulanan") or 0), f"{p.get('sisa', 0)}/{p.get('kuota', 0)}", str(p.get("deskripsi") or "—")),
        subjudul="Harga bulanan dan kuota tersedia.",
        back_label="Lanjut pilih program",
    )

def menu_kelas_saya():
    ok, payload = student_service.kelas_saya()
    rows = _hasil(ok, payload, "KELAS SAYA")
    if rows is None:
        return
    _tabel_paginasi(
        "KELAS SAYA", rows,
        [("Program", {"min_width": 24}), ("Jenjang", {"width": 12}), ("Tutor", {"min_width": 20}), ("Status", {"width": 24}), ("Terdaftar", {"width": 15})],
        lambda r: (str(r.get("nama_program") or "—"), str(r.get("jenjang") or "—"), str(r.get("tutor") or "—"), str(r.get("status") or "—").upper(), _tanggal(r.get("created_at"))),
        subjudul="Program yang sedang diikuti dan riwayat pendaftaran.",
    )


def menu_jadwal_saya():
    while True:
        _header("JADWAL SAYA", "Lihat jadwal hari ini, semua jadwal mingguan, atau satu program.")
        action = questionary.select(
            "Pilih tampilan jadwal:",
            choices=[
                Choice("Jadwal hari ini", value="today"),
                Choice("Jadwal mingguan", value="week"),
                Choice("Filter berdasarkan program", value="program"),
                Choice("Kembali", value="back"),
            ], style=GAYA, qmark="◆", pointer="▶",
        ).ask()
        if action is None or action == "back":
            return
        program_id = None
        if action == "program":
            p = _program_akademik(aktif_saja=True)
            if not p:
                continue
            program_id = p["program_id"]
        day = HARI[date.today().weekday()] if action == "today" else None
        ok, payload = student_service.jadwal_saya(hari=day, program_id=program_id)
        rows = _hasil(ok, payload, "JADWAL SAYA")
        if rows is None:
            continue
        title = "JADWAL HARI INI" if action == "today" else "JADWAL MINGGUAN"
        if program_id:
            title = f"JADWAL — {p['nama_program']}"
        _tabel_paginasi(
            title, rows,
            [("Hari", {"width": 10}), ("Waktu", {"width": 15}), ("Program", {"min_width": 22}), ("Tutor", {"min_width": 20}), ("Ruang", {"width": 12})],
            lambda r: (HARI_LABEL.get(r.get("hari"), str(r.get("hari", "—")).capitalize()), f"{_waktu(r.get('jam_mulai'))}-{_waktu(r.get('jam_selesai'))}", str(r.get("nama_program") or "—"), str(r.get("nama_tutor") or "—"), str(r.get("nama_ruang") or "—")),
            subjudul="Hanya jadwal aktif dari program yang pendaftarannya aktif.",
        )


def menu_absensi_siswa():
    p = _program_akademik()
    if not p:
        return
    ok_sum, summary = student_service.rekap_absensi(p["program_id"])
    summaries = _hasil(ok_sum, summary, "RIWAYAT ABSENSI")
    if summaries is None:
        return
    ok_rows, rows = student_service.riwayat_absensi(p["program_id"])
    rows = _hasil(ok_rows, rows, "RIWAYAT ABSENSI")
    if rows is None:
        return
    _header("RIWAYAT ABSENSI", p["nama_program"])
    if summaries:
        r = summaries[0]
        t = Table(show_header=True, header_style="bold cyan", expand=True)
        for c in ["Pertemuan", "Hadir", "Izin", "Sakit", "Alpa", "% Hadir"]:
            t.add_column(c, justify="right")
        t.add_row(str(r.get("total_pertemuan", 0)), str(r.get("hadir", 0)), str(r.get("izin", 0)), str(r.get("sakit", 0)), str(r.get("alpa", 0)), f"{_nilai(r.get('persen_hadir'))}%")
        console.print(Panel(t, title="RINGKASAN", border_style="green", expand=True))
    else:
        info("Belum ada absensi tercatat untuk program ini.")
    if rows:
        _jeda("Tekan Enter untuk melihat riwayat per pertemuan...")
        _tabel_paginasi(
            "RIWAYAT PER PERTEMUAN", rows,
            [("Tanggal", {"width": 14}), ("Ke-", {"width": 5}), ("Status", {"width": 12}), ("Topik", {"min_width": 22}), ("Keterangan", {"min_width": 22})],
            lambda r: (_tanggal(r.get("tanggal")), str(r.get("pertemuan_ke") or "—"), STATUS_ABSENSI.get(r.get("status_absensi"), str(r.get("status_absensi") or "—")), str(r.get("topik") or "—"), str(r.get("keterangan") or "—")),
            subjudul=p["nama_program"],
        )
    else:
        _jeda()


def _build_rapor_text(profile, summary, grades):
    now = datetime.now().strftime("%d-%m-%Y %H:%M")
    lines = [
        "SIBIMA - RAPOR AKADEMIK SISWA",
        "=" * 56,
        f"Nama       : {profile.get('nama_lengkap') or '-'}",
        f"NIS        : {profile.get('nis') or '-'}",
        f"Username   : {profile.get('username') or '-'}",
        f"Program    : {summary.get('nama_program') or '-'} ({summary.get('jenjang') or '-'})",
        f"Status     : {str(summary.get('status_enrollment') or '-').upper()}",
        f"Dicetak    : {now}",
        "",
        "RINGKASAN NILAI",
        "-" * 56,
        f"Tugas : {_nilai(summary.get('tugas'), 2)} (bobot {summary.get('bobot_tugas', 0)}%)",
        f"Kuis  : {_nilai(summary.get('kuis'), 2)} (bobot {summary.get('bobot_kuis', 0)}%)",
        f"UTS   : {_nilai(summary.get('uts'), 2)} (bobot {summary.get('bobot_uts', 0)}%)",
        f"UAS   : {_nilai(summary.get('uas'), 2)} (bobot {summary.get('bobot_uas', 0)}%)",
        f"NILAI AKHIR BERBOBOT: {_nilai(summary.get('nilai_akhir'), 2)}",
        "",
        "RINCIAN NILAI",
        "-" * 56,
        "Tanggal | Jenis | Judul | Nilai | Tutor",
    ]
    if grades:
        for g in grades:
            lines.append(f"{_tanggal(g.get('tanggal'))} | {g.get('jenis', '-').upper()} | {g.get('judul') or '-'} | {_nilai(g.get('nilai'), 2)} | {g.get('nama_tutor') or '-'}")
    else:
        lines.append("Belum ada rincian nilai yang diinput.")
    lines += ["", "Dokumen ini dibuat oleh SIBIMA berdasarkan data akademik yang tersimpan."]
    return "\n".join(lines) + "\n"


def menu_nilai_rapor():
    p = _program_akademik()
    if not p:
        return
    ok, summaries = student_service.ringkasan_nilai(p["program_id"])
    summaries = _hasil(ok, summaries, "NILAI DAN RAPOR")
    if summaries is None:
        return
    summary = summaries[0] if summaries else None
    ok, grades = student_service.detail_nilai(p["program_id"])
    grades = _hasil(ok, grades, "NILAI DAN RAPOR")
    if grades is None:
        return
    while True:
        _header("NILAI DAN RAPOR", p["nama_program"])
        t = Table(title="Nilai akhir berbobot", header_style="bold cyan", expand=True)
        for c in ["Tugas", "Kuis", "UTS", "UAS", "Nilai akhir"]:
            t.add_column(c, justify="right")
        if summary:
            t.add_row(_nilai(summary.get("tugas"), 2), _nilai(summary.get("kuis"), 2), _nilai(summary.get("uts"), 2), _nilai(summary.get("uas"), 2), _nilai(summary.get("nilai_akhir"), 2))
        else:
            t.add_row("—", "—", "—", "—", "—")
        console.print(t)
        info("Komponen yang belum diinput ditampilkan sebagai —. Nilai akhir memakai bobot program dan hanya komponen yang sudah tersedia.")
        choice = questionary.select(
            "Tindakan:", choices=[
                Choice("Lihat rincian nilai", value="detail"),
                Choice("Cetak rapor TXT", value="txt"),
                Choice("Kembali", value="back"),
            ], style=GAYA, qmark="◆", pointer="▶",
        ).ask()
        if choice is None or choice == "back":
            return
        if choice == "detail":
            _tabel_paginasi(
                "RINCIAN NILAI", grades,
                [("Tanggal", {"width": 14}), ("Jenis", {"width": 10}), ("Judul", {"min_width": 26}), ("Nilai", {"width": 8, "justify": "right"}), ("Tutor", {"min_width": 20})],
                lambda g: (_tanggal(g.get("tanggal")), str(g.get("jenis") or "—").upper(), str(g.get("judul") or "—"), _nilai(g.get("nilai"), 2), str(g.get("nama_tutor") or "—")),
            )
        elif choice == "txt":
            ok, profile = student_service.profil_saya()
            profile = _hasil(ok, profile, "CETAK RAPOR")
            if profile is None:
                continue
            if not summary:
                peringatan("Ringkasan nilai tidak ditemukan untuk program ini.")
                _jeda()
                continue
            try:
                report_dir = Path("rapor")
                report_dir.mkdir(parents=True, exist_ok=True)
                nis_safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(profile.get("nis") or profile.get("id")))
                prog_safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(p["program_id"]))
                path = report_dir / f"rapor_{nis_safe}_program_{prog_safe}_{datetime.now():%Y%m%d_%H%M%S}.txt"
                path.write_text(_build_rapor_text(profile, summary, grades), encoding="utf-8")
                _header("RAPOR BERHASIL DICETAK")
                sukses(f"Rapor tersimpan: {path}")
                _jeda()
            except OSError as exc:
                _header("CETAK RAPOR")
                gagal(f"File rapor tidak dapat dibuat ({type(exc).__name__}).")
                _jeda()


def menu_catatan_materi():
    p = _program_akademik()
    if not p:
        return
    ok, rows = student_service.catatan_materi(p["program_id"])
    rows = _hasil(ok, rows, "CATATAN MATERI")
    if rows is None:
        return
    _tabel_paginasi(
        "CATATAN MATERI", rows,
        [("Tanggal", {"width": 14}), ("Ke-", {"width": 5}), ("Tutor", {"min_width": 20}), ("Topik", {"min_width": 22}), ("Ringkasan", {"min_width": 35})],
        lambda r: (_tanggal(r.get("tanggal")), str(r.get("pertemuan_ke") or "—"), str(r.get("nama_tutor") or "—"), str(r.get("topik") or "—"), str(r.get("ringkasan") or "—")),
        subjudul=p["nama_program"],
    )


def _lihat_profil(profile):
    _header("PROFIL SAYA", "Data yang dapat diubah siswa ditampilkan terpisah dari identitas akun.")
    table = Table(show_header=False, box=None, expand=True, pad_edge=False)
    table.add_column("Label", style="dim", width=22)
    table.add_column("Nilai", style="white")
    fields = [
        ("Nama lengkap", profile.get("nama_lengkap")),
        ("Username", profile.get("username")),
        ("Email", profile.get("email")),
        ("NIS", profile.get("nis")),
        ("Status akun", profile.get("status")),
        ("Jenjang", profile.get("jenjang")),
        ("Sekolah", profile.get("sekolah")),
        ("Nomor HP", profile.get("no_hp")),
        ("Nama wali", profile.get("nama_wali")),
    ]
    for label, val in fields:
        table.add_row(label, str(val or "Belum diisi"))
    console.print(Panel(table, border_style="bright_blue", title="INFORMASI AKUN", expand=True))


def menu_profil_siswa():
    while True:
        ok, profile = student_service.profil_saya()
        profile = _hasil(ok, profile, "PROFIL SAYA")
        if profile is None:
            return
        _lihat_profil(profile)
        pilihan = questionary.select(
            "Pilih tindakan profil:", choices=[
                Choice("Lengkapi / ubah profil", value="edit"),
                Choice("Ganti password", value="password"),
                Choice("Kembali", value="back"),
            ], style=GAYA, qmark="◆", pointer="▶",
        ).ask()
        if pilihan is None or pilihan == "back":
            return
        if pilihan == "edit":
            jenjang = questionary.text("Jenjang", default=str(profile.get("jenjang") or ""), style=GAYA).ask()
            if jenjang is None: continue
            sekolah = questionary.text("Sekolah", default=str(profile.get("sekolah") or ""), style=GAYA).ask()
            if sekolah is None: continue
            no_hp = questionary.text("Nomor HP (kosongkan jika belum ada)", default=str(profile.get("no_hp") or ""), style=GAYA).ask()
            if no_hp is None: continue
            nama_wali = questionary.text("Nama wali", default=str(profile.get("nama_wali") or ""), style=GAYA).ask()
            if nama_wali is None: continue
            ok, pesan = student_service.ubah_profil({"jenjang": jenjang, "sekolah": sekolah, "no_hp": no_hp, "nama_wali": nama_wali})
            _header("UBAH PROFIL")
            sukses(pesan) if ok else gagal(pesan)
            _jeda()
        elif pilihan == "password":
            lama = questionary.password("Password saat ini:", style=GAYA).ask()
            if lama is None: continue
            baru = questionary.password("Password baru:", style=GAYA).ask()
            if baru is None: continue
            konfirmasi = questionary.password("Ulangi password baru:", style=GAYA).ask()
            if konfirmasi is None: continue
            if baru != konfirmasi:
                _header("GANTI PASSWORD")
                gagal("Konfirmasi password baru tidak cocok.")
                _jeda()
                continue
            ok, pesan = student_service.ganti_password(lama, baru)
            _header("GANTI PASSWORD")
            sukses(pesan) if ok else gagal(pesan)
            _jeda()


def menu_tanya_ai_info():
    _header("TANYA AI", "Fitur opsional SIBIMA")
    console.print(Panel(
        "Integrasi Gemini belum diaktifkan pada tahap ini.\n\n"
        "Menu akan tersedia setelah konfigurasi API, pengelolaan kunci rahasia, batas penggunaan, dan penanganan error diselesaikan.",
        border_style="yellow", title="FITUR TAHAP BERIKUTNYA", padding=(1, 3), expand=True,
    ))
    _jeda()
