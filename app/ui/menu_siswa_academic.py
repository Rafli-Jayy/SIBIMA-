"""Submenu akademik dan profil siswa dengan tampilan per layar."""

from datetime import date, datetime
from pathlib import Path
import re

import questionary
from questionary import Choice, Separator, Style
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markup import escape

from app.services import auth_service, student_service
from app.ui.console import bersihkan_layar, console, gagal, info, peringatan, sukses
from app.ui.jadwal_context import kondisi_jadwal_siswa, jadwal_rutin_terdekat, jam_jadwal, label_hari
from app.ui.proyeksi_pertemuan import proyeksi_jadwal, CATATAN_PROYEKSI
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
        isi += f"\n[dim]{escape(str(subjudul))}[/dim]"
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
        lambda r: (f"{r['nama_program']} | {r['jenjang']} | "
                   f"{'AKSES TERKUNCI - TAGIHAN' if r.get('akses_terkunci') else r['status_enrollment'].upper()}"),
        "program_id",
    )
    if chosen is None:
        return None
    dipilih = next((p for p in programs if p["program_id"] == chosen), None)
    if dipilih and dipilih.get("akses_terkunci"):
        _header("AKSES KELAS TERKUNCI", dipilih["nama_program"])
        peringatan(
            "Tagihan kelas ini telah melewati H+3. Silakan lunasi semua "
            "tagihan tertunggak di menu Tagihan dan Pembayaran. "
            "Akses akan terbuka otomatis setelah pembayaran berhasil."
        )
        _jeda()
        return None
    return dipilih



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

def _panel_info_kelas(row, jadwal=None):
    """Identitas satu kelas tanpa menebak jadwal atau aktivitas tutor."""
    status = str(row.get("status") or "—")
    locked = status == "aktif" and bool(row.get("akses_terkunci"))
    status_txt = "AKSES TERKUNCI (TAGIHAN)" if locked else status.upper()
    konten = (
        f"[bold]Program[/bold]       : {escape(str(row.get('nama_program') or '—'))} "
        f"({escape(str(row.get('kode') or '—'))})\n"
        f"[bold]Jenjang[/bold]       : {escape(str(row.get('jenjang') or '—'))}\n"
        f"[bold]Tutor terjadwal[/bold]: {escape(str(row.get('tutor') or 'Belum ditentukan'))}\n"
        f"[bold]Status[/bold]        : {escape(status_txt)}\n"
        f"[bold]Terdaftar[/bold]     : {escape(_tanggal(row.get('created_at')))}"
    )
    console.print(Panel(konten, title="INFORMASI KELAS", border_style="cyan", expand=True))
    if locked:
        peringatan("Akses akademik ditangguhkan karena tagihan lewat H+3. "
                   "Menu Tagihan dan Pembayaran tetap bisa digunakan.")
    elif status == "menunggu_pembayaran":
        info("Pendaftaran belum aktif. Selesaikan pembayaran melalui menu Tagihan dan Pembayaran.")
    elif status == "menunggu":
        info("Pembayaran/pendaftaran sedang menunggu keputusan Admin.")
    elif status == "aktif" and jadwal is not None:
        if not jadwal:
            peringatan("Kelas aktif, tetapi jadwal rutin belum tersedia. Silakan periksa dengan Admin.")
        else:
            table = Table(show_header=True, header_style="bold cyan", expand=True)
            for name in ("Hari", "Waktu", "Tutor", "Ruang"):
                table.add_column(name)
            for r in jadwal:
                table.add_row(label_hari(r.get("hari")), jam_jadwal(r),
                              str(r.get("nama_tutor") or "Belum ditentukan"),
                              str(r.get("nama_ruang") or "—"))
            console.print(Panel(table, title="JADWAL RUTIN (bukan laporan pertemuan)",
                                border_style="bright_blue", expand=True))


def _label_status_sesi(status):
    return {'batal': 'Dibatalkan', 'perlu_laporan': 'Menunggu laporan Tutor',
            'selesai': 'Selesai', 'terlaksana': 'Catatan sesi tersedia (legacy; belum diverifikasi selesai)'}.get(
                status, 'Status belum tersedia')


def _riwayat_pertemuan_siswa(row):
    """Riwayat hanya memuat sesi yang benar-benar tersimpan oleh tutor."""
    ok, payload = student_service.pertemuan_saya(row["program_id"])
    rows = _hasil(ok, payload, "PERTEMUAN TERCATAT")
    if rows is None:
        return
    while True:
        _header("PERTEMUAN TERCATAT", row["nama_program"])
        if not rows:
            info("Belum ada laporan pertemuan dari tutor. Jadwal rutin bukan bukti kelas sudah terlaksana.")
            _jeda()
            return
        t = Table(show_header=True, header_style="bold cyan", expand=True)
        for title in ("Tanggal", "Ke-", "Materi", "Catatan", "Kehadiran saya"):
            t.add_column(title, overflow="fold")
        for s in rows[:20]:
            status = ("Dibatalkan" if s.get("status_pertemuan") == "batal" else
                      STATUS_ABSENSI.get(s.get("status_absensi"), "Belum dicatat tutor"))
            t.add_row(_tanggal(s.get("tanggal")), str(s.get("pertemuan_ke") or "—"),
                      str(s.get("topik") or "Belum dilaporkan"),
                      "Ada" if s.get("ringkasan") else "Belum dilaporkan", status)
        console.print(Panel(t, title="RIWAYAT SESI (maks. 20 terbaru)", border_style="blue", expand=True))
        choices = [Choice(
            f"#{s.get('pertemuan_ke') or '—'} • {_tanggal(s.get('tanggal'))} • "
            f"{s.get('topik') or 'Materi belum dilaporkan'}", value=s["session_id"]
        ) for s in rows[:20]]
        pilihan = questionary.select("Lihat detail pertemuan:", choices=choices + [
            Separator("────────────────────"), Choice("Kembali ke kelas", value="__back__")
        ], style=GAYA, qmark="◆", pointer="▶").ask()
        if pilihan in (None, "__back__"):
            return
        s = next((r for r in rows if r["session_id"] == pilihan), None)
        if s is None:
            continue
        _header(f"DETAIL PERTEMUAN #{s.get('pertemuan_ke') or '—'}", row["nama_program"])
        konten = (f"[bold]Tanggal[/bold] : {escape(_tanggal(s.get('tanggal')))}\n"
                  f"[bold]Waktu[/bold]   : {escape(jam_jadwal(s))}\n"
                  f"[bold]Tutor[/bold]   : {escape(str(s.get('nama_tutor') or '—'))}\n"
                  f"[bold]Ruang[/bold]   : {escape(str(s.get('nama_ruang') or '—'))}\n"
                  f"[bold]Status[/bold]  : {escape(_label_status_sesi(s.get('status_pertemuan')))}\n"
                  f"[bold]Materi[/bold]  : {escape(str(s.get('topik') or 'Belum dilaporkan tutor'))}\n"
                  f"[bold]Ringkasan[/bold]: {escape(str(s.get('ringkasan') or 'Belum dilaporkan tutor'))}\n"
                  f"[bold]Absensi saya[/bold]: {escape('Dibatalkan' if s.get('status_pertemuan') == 'batal' else STATUS_ABSENSI.get(s.get('status_absensi'), 'Belum dicatat tutor'))}")
        console.print(Panel(konten, title="INFORMASI PEMBELAJARAN", border_style="cyan", expand=True))
        _jeda()


def _sesi_per_program_jadwal(jadwal):
    """Hanya untuk jadwal yang sudah dibatasi student_service (enrollment aktif, H+3).

    Jika fetch gagal, None berarti status TIDAK DIKETAHUI, bukan 'belum dilaporkan'.
    """
    result = {}
    for program_id in {j.get("program_id") for j in jadwal if j.get("program_id") is not None}:
        ok, payload = student_service.pertemuan_saya(program_id)
        result[program_id] = payload if ok else None
    return result


def _panel_rencana_siswa(jadwal, sesis, enrollments=()):
    """Ringkas slot untuk kelas yang dapat diakses, perhatikan tanggal masuk siswa."""
    active_since = {}
    for e in enrollments:
        if e.get("status") != "aktif" or e.get("akses_terkunci"):
            continue
        created = e.get("created_at")
        enrolled_day = created.date() if isinstance(created, datetime) else created
        if isinstance(enrolled_day, date):
            active_since[e.get("program_id")] = max(
                enrolled_day, active_since.get(e.get("program_id"), date.min)
            )
    for j in jadwal:
        proyeksi = proyeksi_jadwal(j, sesis.get(j.get("program_id")))
        if proyeksi is None:
            continue
        sebelumnya, berikutnya = proyeksi["sebelumnya"], proyeksi["berikutnya"]
        since = active_since.get(j.get("program_id"))
        if since and sebelumnya["tanggal"] < since:
            sebelumnya = {**sebelumnya, "status": "Sebelum pendaftaran ini (tidak dihitung)"}
        konten = (
            f"[bold]{escape(str(j.get('nama_program') or 'Kelas'))}[/bold] • "
            f"{escape(label_hari(j.get('hari')))} {escape(jam_jadwal(j))}\n"
            f"[bold]Jadwal sebelumnya (perkiraan)[/bold]: {_tanggal(sebelumnya['tanggal'])}\n"
            f"  {escape(sebelumnya['status'])}\n"
            f"[bold]Jadwal berikutnya (perkiraan)[/bold]: {_tanggal(berikutnya['tanggal'])}\n"
            f"  {escape(berikutnya['status'])}"
        )
        console.print(Panel(konten, title="RENCANA DAN LAPORAN PERTEMUAN", border_style="blue", expand=True))
    info(CATATAN_PROYEKSI)


def _detail_kelas_siswa(row):
    """Halaman konteks satu enrollment; tidak membuka akademik jika H+3 terkunci."""
    while True:
        _header("DETAIL KELAS", str(row.get("nama_program") or "Kelas"))
        status = row.get("status")
        locked = bool(row.get("akses_terkunci"))
        schedule = None
        if status == "aktif" and not locked:
            ok, payload = student_service.jadwal_saya(program_id=row["program_id"])
            if not ok:
                gagal(str(payload))
            else:
                schedule = payload
        _panel_info_kelas(row, schedule)
        if schedule and status == "aktif" and not locked:
            _panel_rencana_siswa(schedule, _sesi_per_program_jadwal(schedule), [row])
        choices = []
        if status == "aktif" and not locked and schedule is not None:
            choices.append(Choice("Riwayat pertemuan dan materi", value="sessions"))
        choices.append(Choice("Kembali ke daftar kelas", value="back"))
        action = questionary.select("Pilih tindakan kelas:", choices=choices,
                                    style=GAYA, qmark="◆", pointer="▶").ask()
        if action in (None, "back"):
            return
        if action == "sessions":
            _riwayat_pertemuan_siswa(row)


def menu_kelas_saya():
    while True:
        ok, payload = student_service.kelas_saya()
        rows = _hasil(ok, payload, "KELAS SAYA")
        if rows is None:
            return
        rows = [r for r in rows if r.get("status") in {"menunggu_pembayaran", "menunggu", "aktif"}]
        if not rows:
            _header("KELAS SAYA")
            info("Belum ada kelas aktif atau pendaftaran berjalan. Buka Katalog Program untuk mendaftar.")
            _jeda()
            return
        # Pada daftar panjang, tampilkan tabel berpaginasi seperti versi sebelumnya
        # sebelum pengguna memilih detail satu enrollment.
        if len(rows) > 12:
            _tabel_paginasi(
                "KELAS SAYA", rows,
                [("Program", {"min_width": 22}), ("Jenjang", {"width": 12}),
                 ("Tutor", {"min_width": 18}), ("Status", {"width": 22})],
                lambda r: (str(r.get("nama_program") or "—"), str(r.get("jenjang") or "—"),
                           str(r.get("tutor") or "—"),
                           "TERKUNCI (TAGIHAN)" if r.get("akses_terkunci") else str(r.get("status") or "—").upper()),
                subjudul="Pilih satu kelas setelah melihat daftar.", back_label="Lanjut ke detail kelas",
            )
        _header("KELAS SAYA", "Pilih salah satu kelas untuk melihat informasi lengkap.")
        t = Table(show_header=True, header_style="bold cyan", expand=True)
        for name in ("Program", "Tutor terjadwal", "Status"):
            t.add_column(name, overflow="fold")
        for r in rows[:12]:
            status = "TERKUNCI (TAGIHAN)" if r.get("akses_terkunci") else str(r.get("status") or "—").upper()
            t.add_row(str(r.get("nama_program") or "—"), str(r.get("tutor") or "Belum ditentukan"), status)
        console.print(Panel(t, title="KELAS DAN PENDAFTARAN BERJALAN", border_style="blue", expand=True))
        selected = _pilih_data("Pilih kelas untuk detail", rows,
            lambda r: f"{r.get('nama_program') or '—'} • {'TAGIHAN H+3' if r.get('akses_terkunci') else str(r.get('status') or '—').upper()}",
            "enrollment_id")
        if selected is None:
            return
        detail = next((r for r in rows if r.get("enrollment_id") == selected), None)
        if detail:
            _detail_kelas_siswa(detail)


def _info_jadwal_kosong(kondisi, jadwal_semua):
    if kondisi == "belum_ada_kelas":
        info("Belum ada kelas aktif. Lihat Katalog Program untuk mendaftar, atau periksa status pendaftaran.")
    elif kondisi == "terkunci_tagihan":
        peringatan("Kelas aktif sedang terkunci karena tagihan H+3. "
                   "Buka Tagihan dan Pembayaran untuk melunasi tunggakan.")
    elif kondisi == "belum_dijadwalkan":
        peringatan("Kelas aktif, tetapi jadwal rutin belum tersedia. Silakan periksa dengan Admin.")
    elif kondisi == "tidak_ada_hari_ini":
        info("Tidak ada kelas hari ini. Kelas kamu tetap aktif.")
        upcoming = jadwal_rutin_terdekat(jadwal_semua)
        if upcoming:
            dt, item = upcoming
            console.print(Panel(
                f"[bold]{escape(str(item.get('nama_program') or '—'))}[/bold]\n"
                f"{dt.strftime('%d-%m-%Y')} • {escape(jam_jadwal(item))} • "
                f"Tutor {escape(str(item.get('nama_tutor') or '—'))}\n"
                "[dim]Perkiraan berdasarkan jadwal rutin, bukan konfirmasi sesi.[/dim]",
                title="JADWAL RUTIN BERIKUTNYA", border_style="cyan", expand=True))


def menu_jadwal_saya():
    while True:
        _header("JADWAL SAYA", "Jadwal rutin ≠ laporan pertemuan. Pilih ringkasan yang ingin dibuka.")
        action = questionary.select("Pilih tampilan jadwal:", choices=[
            Choice("Jadwal hari ini", value="today"),
            Choice("Jadwal mingguan", value="week"),
            Choice("Filter berdasarkan program", value="program"),
            Choice("Kembali", value="back"),
        ], style=GAYA, qmark="◆", pointer="▶").ask()
        if action in (None, "back"):
            return
        program_id = None
        if action == "program":
            p = _program_akademik(aktif_saja=True)
            if not p:
                continue
            program_id = p["program_id"]
        ok, enrollments = student_service.kelas_saya()
        if not ok:
            _header("JADWAL SAYA"); gagal(str(enrollments)); _jeda(); continue
        ok, all_schedules = student_service.jadwal_saya(program_id=program_id)
        if not ok:
            _header("JADWAL SAYA"); gagal(str(all_schedules)); _jeda(); continue
        day = HARI[date.today().weekday()]
        rows = [j for j in all_schedules if j.get("hari") == day] if action == "today" else all_schedules
        kondisi = kondisi_jadwal_siswa(enrollments, all_schedules,
                                      day if action == "today" else None)
        title = "JADWAL HARI INI" if action == "today" else "JADWAL MINGGUAN"
        if program_id:
            title = f"JADWAL — {p['nama_program']}"
        _header(title, "Informasi jadwal rutin; belum tentu pertemuan sudah dilaksanakan.")
        if not rows:
            _info_jadwal_kosong(kondisi, all_schedules)
            _jeda()
            continue
        t = Table(show_header=True, header_style="bold cyan", expand=True)
        for name in ("Hari", "Waktu", "Program", "Tutor", "Ruang"):
            t.add_column(name, overflow="fold")
        for r in rows:
            t.add_row(label_hari(r.get("hari")), jam_jadwal(r),
                      str(r.get("nama_program") or "—"), str(r.get("nama_tutor") or "—"),
                      str(r.get("nama_ruang") or "—"))
        console.print(Panel(t, title="JADWAL RUTIN", border_style="blue", expand=True))
        _panel_rencana_siswa(rows, _sesi_per_program_jadwal(rows), enrollments)
        accessible_programs = {r.get("program_id") for r in all_schedules}
        missing = [r.get("nama_program") for r in enrollments
                   if r.get("status") == "aktif" and not r.get("akses_terkunci")
                   and r.get("program_id") not in accessible_programs]
        if missing:
            peringatan("Ada kelas aktif yang belum dijadwalkan: " + ", ".join(str(n) for n in missing))
        _jeda()


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
        info(f"Pendaftaran #{r.get('enrollment_id') or '—'} • "
             "Rekap hanya menghitung sesi selesai; absensi dalam proses belum final.")
        t = Table(show_header=True, header_style="bold cyan", expand=True)
        for c in ["Pertemuan", "Hadir", "Izin", "Sakit", "Alpa", "% Hadir"]:
            t.add_column(c, justify="right")
        t.add_row(str(r.get("total_pertemuan", 0)), str(r.get("hadir", 0)), str(r.get("izin", 0)), str(r.get("sakit", 0)), str(r.get("alpa", 0)), (f"{_nilai(r.get('persen_hadir'))}%" if r.get('persen_hadir') is not None else "—"))
        console.print(Panel(t, title="RINGKASAN", border_style="green", expand=True))
    else:
        info("Belum ada absensi tercatat untuk program ini.")
    if rows:
        _jeda("Tekan Enter untuk melihat riwayat per pertemuan...")
        _tabel_paginasi(
            "RIWAYAT PER PERTEMUAN", rows,
            [("Tanggal", {"width": 14}), ("Ke-", {"width": 5}), ("Status", {"width": 12}), ("Sesi", {"width": 17}), ("Topik", {"min_width": 22}), ("Keterangan", {"min_width": 22})],
            lambda r: (_tanggal(r.get("tanggal")), str(r.get("pertemuan_ke") or "—"),
                       STATUS_ABSENSI.get(r.get("status_absensi"), str(r.get("status_absensi") or "—")),
                       "Selesai" if r.get("status_pertemuan") == "selesai" else "Dalam proses/arsip",
                       str(r.get("topik") or "—"), str(r.get("keterangan") or "—")),
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
