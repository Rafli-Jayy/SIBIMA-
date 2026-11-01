"""Submenu fungsional untuk tutor: jadwal, kelas, absensi, nilai, materi, profil."""

from datetime import date
from math import ceil

import questionary
from questionary import Choice, Style
from rich.align import Align
from rich.box import ROUNDED
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markup import escape
from app.ui.jadwal_context import jadwal_rutin_terdekat, jam_jadwal, label_hari
from app.ui.proyeksi_pertemuan import proyeksi_jadwal, CATATAN_PROYEKSI

from app.services import academic_service, tutor_service
from app.ui.console import console, bersihkan_layar, gagal, sukses, peringatan, info

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
_HARI = ("senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu")
_LABEL_JENIS = {"tugas": "Tugas", "kuis": "Kuis (nilai manual)", "uts": "UTS", "uas": "UAS"}
_LABEL_ABSEN = {"H": "Hadir", "I": "Izin", "S": "Sakit", "A": "Alpa"}
_PAGE_SIZE = 8
_PAGINASI_LANJUT = "__sibima_tutor_next_page__"
_PAGINASI_SEBELUM = "__sibima_tutor_prev_page__"


def _layar(judul, subjudul):
    """Bersihkan terminal dan tampilkan header konsisten dengan dashboard admin."""
    bersihkan_layar()
    isi = Text()
    isi.append("S I B I M A\n", style="bold cyan")
    isi.append(str(judul).upper() + "\n", style="bold white")
    isi.append(str(subjudul), style="dim")
    console.print(Panel(
        Align.center(isi),
        border_style="cyan",
        box=ROUNDED,
        padding=(1, 3),
        expand=True,
    ))


def _pause():
    input("\n↵ Tekan Enter untuk kembali...")


def _hasil(pesan, berhasil=True, bagian="HASIL OPERASI"):
    _layar(bagian, "Ringkasan hasil tindakan")
    (sukses if berhasil else gagal)(pesan if isinstance(pesan, str) else "Operasi berhasil.")


def _form_teks(prompt, *, default=None, bagian="FORMULIR TUTOR", password=False):
    _layar(bagian, "Isi kolom di bawah. Ctrl+C untuk membatalkan input.")
    kwargs = {"style": _GAYA}
    if default is not None:
        kwargs["default"] = default
    fungsi = questionary.password if password else questionary.text
    return fungsi(prompt, **kwargs).ask()


def _konfirmasi(prompt, *, default=True, bagian="KONFIRMASI TUTOR"):
    _layar(bagian, "Periksa tindakan sebelum melanjutkan.")
    return questionary.confirm(prompt, default=default, style=_GAYA).ask()


def _pilih(prompt, choices):
    """Pilihan selalu dimulai di layar bersih; daftar panjang dibagi per halaman."""
    options = list(choices or [])
    if not options:
        _layar("PILIHAN TUTOR", prompt)
        peringatan("Belum ada data yang dapat dipilih.")
        _pause()
        return None

    # Aksi navigasi tetap terlihat di setiap halaman pilihan data panjang.
    control_values = {"back", "__back__", "logout", "__cancel__"}
    fixed = [c for c in options if getattr(c, "value", None) in control_values or getattr(c, "value", object()) is None]
    selectable = [c for c in options if c not in fixed]
    can_page = len(selectable) > _PAGE_SIZE and all(hasattr(c, "value") for c in selectable)
    if not can_page:
        _layar("PILIHAN TUTOR", prompt)
        return questionary.select(
            "Pilih opsi:", choices=options, style=_GAYA, qmark="⚡", pointer="▶",
            instruction=" (↑/↓ navigasi • Enter pilih • Ctrl+C batal)",
        ).ask()

    total_pages = ceil(len(selectable) / _PAGE_SIZE)
    page = 0
    while True:
        start = page * _PAGE_SIZE
        visible = selectable[start:start + _PAGE_SIZE]
        if page > 0:
            visible.append(Choice("← Halaman sebelumnya", value=_PAGINASI_SEBELUM))
        if page < total_pages - 1:
            visible.append(Choice("Halaman berikutnya →", value=_PAGINASI_LANJUT))
        visible.extend(fixed)
        _layar("PILIHAN TUTOR", f"{prompt}  •  Halaman {page + 1}/{total_pages}")
        result = questionary.select(
            "Pilih opsi:", choices=visible, style=_GAYA, qmark="⚡", pointer="▶",
            instruction=" (↑/↓ navigasi • Enter pilih • Ctrl+C batal)",
        ).ask()
        if result == _PAGINASI_LANJUT:
            page = min(page + 1, total_pages - 1)
            continue
        if result == _PAGINASI_SEBELUM:
            page = max(page - 1, 0)
            continue
        return result


def _teks_nilai(value):
    if value is None:
        return "-"
    if hasattr(value, "strftime"):
        if value.__class__.__name__ == "time":
            return value.strftime("%H:%M")
        return value.strftime("%d-%m-%Y")
    return str(value)


def _tabel(judul, rows, columns):
    _layar(judul, "DATA AKADEMIK  •  Tabel dibatasi lebar terminal")
    if not rows:
        console.print(Panel(
            "Belum ada data untuk ditampilkan.",
            title="[bold yellow]DATA KOSONG[/bold yellow]",
            border_style="yellow", box=ROUNDED, padding=(1, 2), expand=True,
        ))
        return
    table = Table(
        header_style="bold cyan", border_style="bright_blue", box=ROUNDED,
        show_lines=False, expand=True, pad_edge=False, row_styles=["", "dim"],
    )
    for key, label in columns:
        table.add_column(label, overflow="fold", vertical="middle")
    for row in rows:
        table.add_row(*(Text(_teks_nilai(row.get(key)), overflow="fold") for key, _ in columns))
    console.print(Panel(table, border_style="bright_blue", box=ROUNDED, padding=(0, 1), expand=True))


def _run_service(call, *args, **kwargs):
    result = call(*args, **kwargs)
    ok, data = result
    if not ok:
        _layar("OPERASI GAGAL", "SIBIMA tidak dapat menyelesaikan tindakan ini")
        gagal(data)
    return ok, data


def _programs():
    ok, data = _run_service(academic_service.program_tutor)
    if not ok:
        _pause()
        return None
    return data


def _pilih_program(prompt="Pilih kelas/program:"):
    data = _programs()
    # None berarti query gagal dan layar error sudah ditampilkan oleh service.
    if data is None:
        return None
    if not data:
        _layar("KELAS TUTOR", "Daftar kelas yang ditugaskan")
        peringatan("Belum ada kelas yang ditugaskan kepada akun tutor ini.")
        _pause()
        return None
    choices = [Choice(
        f"{r['kode']} | {r['nama']} ({r['jenjang']}) | {r['siswa_aktif']} siswa aktif",
        value=r["id"],
    ) for r in data]
    return _pilih(prompt, choices)


def _jadwal(aktif=True):
    ok, data = _run_service(academic_service.jadwal, aktif=aktif)
    if not ok:
        _pause()
        return None
    return data


def _pilih_jadwal(*, aktif=True):
    data = _jadwal(aktif=aktif)
    # None berarti query gagal dan sudah meminta jeda pada fungsi _jadwal.
    if data is None:
        return None
    if not data:
        _layar("JADWAL TUTOR", "Pilih jadwal mengajar")
        peringatan("Belum ada jadwal yang sesuai untuk akun ini.")
        _pause()
        return None
    choices = [Choice(
        f"ID {r['id']} | {r['kode_program']} {r['nama_program']} | {r['hari'].title()} "
        f"{_teks_nilai(r['jam_mulai'])}-{_teks_nilai(r['jam_selesai'])} | {_teks_nilai(r['nama_ruang'])}",
        value=r["id"],
    ) for r in data]
    return _pilih("Pilih jadwal:", choices)


def _pilih_siswa(program_id):
    ok, data = _run_service(academic_service.daftar_siswa, program_id)
    if not ok:
        _pause()
        return None
    if not data:
        _layar("DAFTAR SISWA", "Siswa aktif pada program yang dipilih")
        peringatan("Belum ada siswa aktif pada program ini.")
        _pause()
        return None
    return _pilih("Pilih siswa:", [Choice(f"{r.get('nis') or 'Tanpa NIS'} | {r['nama_lengkap']}", value=r["student_id"]) for r in data])


def _pilih_pertemuan(program_id=None, *, dengan_detail=False):
    ok, data = _run_service(academic_service.daftar_pertemuan, program_id)
    if not ok:
        _pause()
        return None
    if not data:
        _layar("DAFTAR PERTEMUAN", "Sesi kelas yang tersedia")
        peringatan("Belum ada laporan pertemuan. Gunakan Kelola Pertemuan pada hari yang dijadwalkan.")
        _pause()
        return None
    choices = [Choice(
        f"ID {r['session_id']} | {r['kode_program']} {r['nama_program']} | "
        f"{_teks_nilai(r['tanggal'])} | Pertemuan {r['pertemuan_ke']} | "
        f"{r['jumlah_absen']} absensi | {r['status_pertemuan']}",
        value=r["session_id"],
    ) for r in data]
    chosen = _pilih("Pilih pertemuan:", choices)
    if chosen is None:
        return None
    if dengan_detail:
        return next((s for s in data if s["session_id"] == chosen), None)
    return chosen


def _detail_jadwal_tutor(item):
    """Halaman konteks jadwal; sesi hanya dilaporkan jika ada catatan nyata."""
    while True:
        ok, payload = academic_service.pertemuan_per_jadwal(item["id"])
        if not ok:
            _layar("DETAIL JADWAL", str(item.get("nama_program") or "—"))
            gagal(str(payload)); _pause(); return
        sessions = payload
        _layar("DETAIL JADWAL TUTOR", f"{item.get('kode_program') or '—'} • {item.get('nama_program') or '—'}")
        message = (
            f"[bold]Program[/bold]       : {escape(str(item.get('nama_program') or '—'))}\n"
            f"[bold]Jenjang[/bold]       : {escape(str(item.get('jenjang') or '—'))}\n"
            f"[bold]Jadwal rutin[/bold]  : {escape(label_hari(item.get('hari')))} • {escape(jam_jadwal(item))}\n"
            f"[bold]Ruangan[/bold]       : {escape(str(item.get('nama_ruang') or '—'))}\n"
            f"[bold]Status jadwal[/bold] : {'Aktif' if item.get('aktif') else 'Nonaktif'}\n"
            f"[bold]Peserta program[/bold]: {item.get('jumlah_siswa') or 0} enrollment aktif (bukan per sesi)"
        )
        console.print(Panel(message, title="INFORMASI KELAS & JADWAL", border_style="cyan", expand=True))
        if item.get("aktif"):
            rencana = proyeksi_jadwal(item, sessions)
            if rencana is not None:
                sebelumnya, berikutnya = rencana["sebelumnya"], rencana["berikutnya"]
                konten = (
                    f"[bold]Jadwal sebelumnya (perkiraan)[/bold]: {_teks_nilai(sebelumnya['tanggal'])}\n"
                    f"  {escape(sebelumnya['status'])}\n"
                    f"[bold]Jadwal berikutnya (perkiraan)[/bold]: {_teks_nilai(berikutnya['tanggal'])}\n"
                    f"  {escape(berikutnya['status'])}\n"
                    "[dim]Nomor pertemuan hanya ada setelah tutor mencatat sesi.[/dim]"
                )
                console.print(Panel(konten, title="RENCANA PERTEMUAN", border_style="bright_blue", expand=True))
                info(CATATAN_PROYEKSI)
        if not sessions:
            console.print(Panel(
                "Belum ada laporan pertemuan tercatat untuk jadwal ini. "
                "Jadwal rutin tidak membuktikan pembelajaran telah berlangsung.",
                title="AKTIVITAS PEMBELAJARAN", border_style="yellow", expand=True))
        else:
            latest = sessions[0]
            status = _label_pertemuan(latest.get("status_pertemuan"))
            latest_txt = (
                f"[bold]Pertemuan #{latest.get('pertemuan_ke') or '—'}[/bold] • "
                f"{escape(_teks_nilai(latest.get('tanggal')))}\n"
                f"[bold]Status[/bold]       : {status}\n"
                f"[bold]Materi[/bold]       : {escape(str(latest.get('topik') or 'Belum dilaporkan'))}\n"
                f"[bold]Absensi tercatat[/bold]: {latest.get('jumlah_absen') or 0} entri "
                "(bukan jaminan lengkap)"
            )
            console.print(Panel(latest_txt, title="PERTEMUAN TERAKHIR TERCATAT", border_style="bright_blue", expand=True))
        chosen = questionary.select("Pilih informasi yang ingin dilihat:", choices=[
            Choice("Riwayat pertemuan yang tercatat", value="riwayat"),
            Choice("Daftar siswa aktif program", value="siswa"),
            Choice("Kembali ke jadwal", value="back"),
        ], style=_GAYA, qmark="⚡", pointer="▶").ask()
        if chosen in (None, "back"):
            return
        if chosen == "riwayat":
            _layar("RIWAYAT PERTEMUAN", str(item.get("nama_program") or "—"))
            if not sessions:
                peringatan("Belum ada sesi tercatat pada jadwal ini.")
            else:
                tbl = Table(show_header=True, header_style="bold cyan", expand=True)
                for col in ("Ke-", "Tanggal", "Materi", "Status catatan", "Absensi"):
                    tbl.add_column(col, overflow="fold")
                for s in sessions:
                    tbl.add_row(str(s.get("pertemuan_ke") or "—"), _teks_nilai(s.get("tanggal")),
                                str(s.get("topik") or "Belum dilaporkan"),
                                _label_pertemuan(s.get("status_pertemuan")),
                                str(s.get("jumlah_absen") or 0))
                console.print(Panel(tbl, border_style="blue", expand=True))
                info("Status 'tercatat' tidak berarti absensi lengkap atau kelas sudah ditutup tutor.")
            _pause()
        elif chosen == "siswa":
            ok, students = _run_service(academic_service.daftar_siswa, item["program_id"])
            if not ok:
                _pause(); continue
            _tabel(f"PESERTA PROGRAM {item.get('nama_program') or '—'}", students,
                   [("nis", "NIS"), ("nama_lengkap", "Nama siswa")])
            info("Peserta berasal dari program, bukan daftar rombongan per jadwal.")
            _pause()


def _jelajah_jadwal_tutor(rows, title, semua=None):
    """Daftar jadwal -> detail tanpa kehilangan identitas program."""
    page = 0
    page_size = 8
    while True:
        _layar(title, "Pilih jadwal untuk melihat informasi lengkap kelas dan sesi.")
        if not rows:
            peringatan("Tidak ada jadwal mengajar hari ini." if "HARI INI" in title else
                       "Belum ada jadwal mengajar aktif yang ditugaskan Admin.")
            if semua:
                next_slot = jadwal_rutin_terdekat(semua)
                if next_slot:
                    dt, nearest = next_slot
                    info(f"Jadwal rutin terdekat (perkiraan): {nearest.get('nama_program') or '—'} "
                         f"• {dt:%d-%m-%Y} • {jam_jadwal(nearest)}")
            _pause(); return
        page_rows = rows[page * page_size:(page + 1) * page_size]
        tbl = Table(show_header=True, header_style="bold cyan", expand=True)
        for col in ("Hari", "Waktu", "Program", "Ruang", "Peserta program"):
            tbl.add_column(col, overflow="fold")
        for r in page_rows:
            tbl.add_row(label_hari(r.get("hari")), jam_jadwal(r),
                        str(r.get("nama_program") or "—"), str(r.get("nama_ruang") or "—"),
                        str(r.get("jumlah_siswa") or 0))
        console.print(Panel(tbl, title="JADWAL RUTIN", border_style="blue", expand=True))
        choices = [Choice(f"{r.get('nama_program') or '—'} • "
                          f"{label_hari(r.get('hari'))} {jam_jadwal(r)} • "
                          f"{r.get('nama_ruang') or '—'}", value=r["id"]) for r in page_rows]
        if page > 0:
            choices.append(Choice("← Halaman sebelumnya", value="__prev__"))
        if (page + 1) * page_size < len(rows):
            choices.append(Choice("Halaman berikutnya →", value="__next__"))
        choices.append(Choice("Kembali", value="__back__"))
        selected = questionary.select("Pilih jadwal untuk detail:", choices=choices,
            style=_GAYA, qmark="⚡", pointer="▶").ask()
        if selected in (None, "__back__"):
            return
        if selected == "__next__":
            page += 1
            continue
        if selected == "__prev__":
            page = max(0, page - 1)
            continue
        row = next((r for r in rows if r["id"] == selected), None)
        if row is not None:
            _detail_jadwal_tutor(row)


def _jadwal_hari_ini():
    data = _jadwal(aktif=True)
    if data is None:
        return
    hari_ini = _HARI[date.today().weekday()]
    rows = [r for r in data if r.get("hari") == hari_ini]
    _jelajah_jadwal_tutor(rows, "JADWAL MENGAJAR HARI INI", semua=data)


def _jadwal_mingguan():
    data = _jadwal(aktif=True)
    if data is None:
        return
    _jelajah_jadwal_tutor(data, "JADWAL MENGAJAR MINGGUAN", semua=data)


def _kelas_dan_siswa():
    while True:
        choice = _pilih("Kelas dan Siswa", [
            Choice("Pilih kelas → Daftar siswa", value="daftar"),
            Choice("Detail seorang siswa", value="detail"),
            Choice("Kembali", value="back"),
        ])
        if choice in (None, "back"):
            return
        program_id = _pilih_program()
        if program_id is None:
            continue
        ok, data = _run_service(academic_service.daftar_siswa, program_id)
        if not ok:
            _pause(); continue
        if choice == "daftar":
            _tabel("Siswa Aktif di Kelas", data, [
                ("nis", "NIS"), ("nama_lengkap", "Nama"), ("enrollment_id", "Pendaftaran"), ("tugas", "Tugas"),
                ("kuis", "Kuis"), ("uts", "UTS"), ("uas", "UAS"),
                ("nilai_akhir", "Nilai Akhir"), ("total_absensi", "Absen Tercatat"),
                ("persen_hadir", "% Hadir"),
            ])
            _pause()
        else:
            student_id = _pilih_siswa(program_id)
            if student_id is None:
                continue
            ok, detail = _run_service(academic_service.detail_siswa, program_id, student_id)
            if not ok:
                _pause(); continue
            _layar("DETAIL SISWA", "Informasi siswa pada kelas yang diampu")
            console.print(Panel(
                f"[bold cyan]{detail['nama_lengkap']}[/]\nNIS: {detail.get('nis') or '-'}\n"
                f"Email: {detail.get('email') or '-'}\nUsername: {detail.get('username') or '-'}\n"
                f"Sekolah: {detail.get('sekolah') or '-'}\nJenjang: {detail.get('jenjang') or '-'}\n"
                f"Nomor HP: {detail.get('no_hp') or '-'}\nNama wali: {detail.get('nama_wali') or '-'}\n"
                f"Kelas: {detail['kode_program']} - {detail['nama_program']}\n"
                f"ID pendaftaran: {detail.get('enrollment_id') or '—'}\n"
                f"Nilai akhir: {_teks_nilai(detail.get('nilai_akhir'))}\n"
                f"Kehadiran: {_teks_nilai(detail.get('persen_hadir'))}% "
                f"(H {detail['hadir']}, I {detail['izin']}, S {detail['sakit']}, A {detail['alpa']})",
                title="Detail Siswa", border_style="cyan", padding=(1, 2),
            ))
            _pause()


def _buka_pertemuan():
    schedule_id = _pilih_jadwal(aktif=True)
    if schedule_id is None:
        return
    ok, result = _run_service(academic_service.buka_pertemuan, schedule_id)
    if ok:
        _hasil(result, True, "PERTEMUAN SIAP")
    _pause()



def _label_pertemuan(status):
    return {
        'batal': 'Dibatalkan', 'selesai': 'Selesai (dikonfirmasi)',
        'perlu_laporan': 'Perlu absensi / laporan',
        'terlaksana': 'Catatan lama (belum terverifikasi selesai)',
    }.get(status, 'Status tidak diketahui')


def _catatan_pada_pertemuan(pertemuan):
    _layar('CATATAN MATERI', f"{pertemuan.get('nama_program') or '—'} • "
           f"Pertemuan #{pertemuan.get('pertemuan_ke') or '—'}")
    topik = questionary.text('Topik pembelajaran:',
        default=pertemuan.get('topik') or '', style=_GAYA).ask()
    if topik is None:
        return
    ringkasan = questionary.text('Ringkasan pembelajaran:',
        default=pertemuan.get('ringkasan') or '', style=_GAYA).ask()
    if ringkasan is None:
        return
    ok, message = _run_service(academic_service.simpan_catatan,
                               pertemuan['session_id'], topik, ringkasan)
    if ok:
        _hasil(message, True, 'MATERI DISIMPAN')
    _pause()


def _kelola_detail_pertemuan(session_id):
    """Selalu refresh status sebelum aksi; konfirmasi selesai di backend atomik."""
    while True:
        ok, info_sesi = _run_service(academic_service.ringkasan_pertemuan, session_id)
        if not ok:
            _pause(); return
        status = info_sesi['status_pertemuan']
        _layar('KELOLA PERTEMUAN',
            f"{info_sesi.get('nama_program') or '—'} • #{info_sesi.get('pertemuan_ke') or '—'} • "
            f"{_teks_nilai(info_sesi.get('tanggal'))}")
        contents = (
            f"[bold]Program[/bold]      : {escape(str(info_sesi.get('nama_program') or '—'))} "
            f"({escape(str(info_sesi.get('kode_program') or '—'))})\n"
            f"[bold]Pertemuan[/bold]    : #{info_sesi.get('pertemuan_ke') or '—'}\n"
            f"[bold]Tanggal[/bold]      : {escape(_teks_nilai(info_sesi.get('tanggal')))}\n"
            f"[bold]Waktu / Ruang[/bold]: {escape(jam_jadwal(info_sesi))} / "
            f"{escape(str(info_sesi.get('nama_ruang') or '—'))}\n"
            f"[bold]Status[/bold]       : {escape(_label_pertemuan(status))}\n"
            f"[bold]Materi[/bold]       : {escape(str(info_sesi.get('topik') or 'Belum dilaporkan'))}\n"
            f"[bold]Absensi[/bold]      : {info_sesi.get('jumlah_absen') or 0} tercatat "
            '(kelengkapan dicek saat menyelesaikan)'
        )
        if status == 'batal':
            contents += '\n[bold]Alasan batal[/bold] : ' + escape(str(info_sesi.get('alasan_batal') or 'Arsip lama (tidak tercatat)'))
        console.print(Panel(contents, title='INFORMASI PERTEMUAN', border_style='cyan', expand=True))
        choices = []
        if status not in ('batal', 'selesai'):
            choices.extend([
                Choice('Isi / Koreksi Absensi Siswa', value='absensi'),
                Choice('Isi Materi & Catatan', value='materi'),
                Choice('Konfirmasi pertemuan selesai', value='selesai'),
                Choice('Laporkan pertemuan dibatalkan', value='batal'),
            ])
        choices.append(Choice('Kembali', value='back'))
        action = questionary.select('Tindakan untuk pertemuan ini:',
            choices=choices, style=_GAYA, qmark='⚡', pointer='▶').ask()
        if action in (None, 'back'):
            return
        if action == 'absensi':
            _isi_absensi(session_id, pertemuan=info_sesi)
        elif action == 'materi':
            _catatan_pada_pertemuan(info_sesi)
        elif action == 'selesai':
            if _konfirmasi('Semua peserta sudah diabsen? Selesaikan pertemuan ini?',
                          default=False, bagian='KONFIRMASI PENYELESAIAN'):
                ok, result = _run_service(academic_service.selesaikan_pertemuan, session_id)
                if ok:
                    _hasil(result, True, 'PERTEMUAN SELESAI')
                _pause()
        elif action == 'batal':
            alasan = _form_teks('Alasan pertemuan tidak berlangsung (wajib):',
                                bagian='PEMBATALAN PERTEMUAN')
            if alasan is None or not alasan.strip():
                continue
            if _konfirmasi('Batalkan pertemuan ini? Absensi belum boleh tercatat.',
                          default=False, bagian='KONFIRMASI PEMBATALAN'):
                ok, result = _run_service(academic_service.batalkan_pertemuan, session_id, alasan)
                if ok:
                    _hasil(result, True, 'PERTEMUAN DIBATALKAN')
                _pause()


def _kelola_pertemuan_hari_ini():
    """Tidak membuat jadwal baru: hanya menyiapkan catatan pada tanggal jadwal."""
    schedule_id = _pilih_jadwal(aktif=True)
    if schedule_id is None:
        return
    _layar('KELOLA PERTEMUAN', 'SIBIMA memakai jadwal rutin Admin; satu catatan per tanggal')
    ok, result = _run_service(academic_service.siapkan_pertemuan, schedule_id)
    if not ok:
        _pause(); return
    _kelola_detail_pertemuan(result['session_id'])

def _peserta_absensi_unik(roster):
    """Satu prompt per siswa, meskipun join enrollment lama menghasilkan duplikat."""
    result = []
    seen = set()
    for student in roster:
        student_id = student.get("student_id")
        if student_id is None or student_id in seen:
            continue
        seen.add(student_id)
        result.append(student)
    return result


def _layar_absensi_siswa(pertemuan, student, index, total, *, pilihan_status=None):
    """Konteks peserta & pertemuan tetap terlihat tepat di atas input Questionary."""
    name = str(student.get("nama_lengkap") or "Nama belum tersedia")
    nis = str(student.get("nis") or "Belum ada")
    program = str(pertemuan.get("nama_program") or "Program tidak tersedia")
    kode = str(pertemuan.get("kode_program") or "—")
    nomor = str(pertemuan.get("pertemuan_ke") or "—")
    tanggal = _teks_nilai(pertemuan.get("tanggal"))
    _layar("ABSENSI • SISWA", f"Pertemuan #{nomor} • {program} • {tanggal}")
    status_lama = student.get("status_absensi")
    status_text = _LABEL_ABSEN.get(status_lama, "Belum dicatat")
    lines = (
        f"[bold cyan]SISWA {index} DARI {total}[/bold cyan]\n"
        f"[bold]Nama[/bold]               : {escape(name)}\n"
        f"[bold]NIS[/bold]                : {escape(nis)}\n"
        f"[bold]Program[/bold]            : {escape(program)} ({escape(kode)})\n"
        f"[bold]Pertemuan[/bold]         : #{escape(nomor)} • {escape(tanggal)}\n"
        f"[bold]Waktu / Ruang[/bold]     : {escape(jam_jadwal(pertemuan))} / "
        f"{escape(str(pertemuan.get('nama_ruang') or '—'))}\n"
        f"[bold]Absensi sebelumnya[/bold] : {escape(status_text)}"
    )
    if pilihan_status is not None:
        lines += f"\n[bold green]Status dipilih[/bold green]      : {escape(_LABEL_ABSEN[pilihan_status])}"
    console.print(Panel(lines, title="IDENTITAS SISWA & PERTEMUAN", border_style="cyan", expand=True))


def _isi_absensi(session_id, *, pertemuan=None):
    # Identitas pertemuan diambil dari service yang memeriksa kepemilikan tutor.
    if pertemuan is None:
        ok, sessions = _run_service(academic_service.daftar_pertemuan)
        if not ok:
            _pause(); return
        pertemuan = next((s for s in sessions if s.get("session_id") == session_id), None)
    if pertemuan is None or pertemuan.get("session_id") != session_id:
        _layar("ABSENSI TUTOR", "Verifikasi identitas pertemuan")
        peringatan("Identitas pertemuan tidak tersedia. Absensi dibatalkan agar tidak salah kelas.")
        _pause(); return
    if pertemuan.get("status_pertemuan") in ("batal", "selesai"):
        _layar("ABSENSI TUTOR", "Pertemuan sudah ditutup")
        peringatan("Absensi tidak bisa diubah pada pertemuan yang sudah selesai atau dibatalkan.")
        _pause(); return

    ok, roster = _run_service(academic_service.daftar_absensi, session_id)
    if not ok:
        _pause(); return
    students = _peserta_absensi_unik(roster)
    if not students:
        _layar("ABSENSI TUTOR", str(pertemuan.get("nama_program") or "—"))
        peringatan("Belum ada siswa yang dapat diabsen untuk pertemuan ini.")
        _pause(); return

    records = []
    preview = []
    total = len(students)
    for index, student in enumerate(students, start=1):
        nama = str(student.get("nama_lengkap") or "Nama belum tersedia")
        _layar_absensi_siswa(pertemuan, student, index, total)
        initial = student.get("status_absensi")
        choices = [Choice(
            f"{label}" + (" (status sebelumnya)" if code == initial else ""),
            value=code,
        ) for code, label in _LABEL_ABSEN.items()]
        choices.append(Choice("Batalkan seluruh pengisian (belum disimpan)", value="__back__"))
        # Nama siswa ada pada panel dan di pertanyaan, bukan hanya subtitle yang bisa terhapus.
        status = questionary.select(
            f"Status kehadiran untuk {nama}:", choices=choices,
            style=_GAYA, qmark="⚡", pointer="▶",
            instruction=" (↑/↓ pilih status • Enter lanjut • Ctrl+C batal)",
        ).ask()
        if status not in _LABEL_ABSEN:
            peringatan("Pengisian dibatalkan; tidak ada absensi yang disimpan.")
            _pause(); return

        _layar_absensi_siswa(pertemuan, student, index, total, pilihan_status=status)
        keterangan = questionary.text(
            f"Keterangan untuk {nama} (opsional):",
            default=student.get("keterangan") or "", style=_GAYA,
        ).ask()
        if keterangan is None:
            peringatan("Pengisian dibatalkan; tidak ada absensi yang disimpan.")
            _pause(); return
        records.append({"student_id": student["student_id"], "status": status, "keterangan": keterangan})
        preview.append({"nis": student.get("nis") or "—", "nama": nama,
                        "status": _LABEL_ABSEN[status], "keterangan": keterangan})

    _layar("KONFIRMASI ABSENSI", f"{pertemuan.get('nama_program') or '—'} • "
           f"Pertemuan #{pertemuan.get('pertemuan_ke') or '—'} • "
           f"{_teks_nilai(pertemuan.get('tanggal'))}")
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    for heading in ("NIS", "Nama siswa", "Status", "Keterangan"):
        table.add_column(heading, overflow="fold")
    for row in preview:
        table.add_row(*(Text(str(row[key]), overflow="fold") for key in
                        ("nis", "nama", "status", "keterangan")))
    console.print(Panel(table, title=f"RINGKASAN ABSENSI • {total} SISWA", border_style="cyan", expand=True))
    decision = questionary.confirm(
        f"Simpan absensi {total} siswa untuk pertemuan #{pertemuan.get('pertemuan_ke') or '—'}?",
        default=False, style=_GAYA,
    ).ask()
    if decision:
        ok, message = _run_service(academic_service.simpan_absensi, session_id, records)
        if ok:
            _hasil(message, True, "ABSENSI TERSIMPAN")
    else:
        peringatan("Perubahan absensi dibatalkan; tidak ada data yang disimpan.")
    _pause()


def _absensi():
    while True:
        choice = _pilih("Absensi", [
            Choice("Kelola pertemuan hari ini (sesuai jadwal)", value="baru"),
            Choice("Kelola pertemuan yang sudah tercatat", value="kelola"),
            Choice("Isi / ubah absensi pertemuan", value="isi"),
            Choice("Rekap absensi per siswa", value="rekap"),
            Choice("Kembali", value="back"),
        ])
        if choice in (None, "back"):
            return
        if choice == "baru":
            _kelola_pertemuan_hari_ini()
        elif choice == "kelola":
            selected = _pilih_pertemuan(dengan_detail=True)
            if selected:
                _kelola_detail_pertemuan(selected["session_id"])
        elif choice == "isi":
            pertemuan = _pilih_pertemuan(dengan_detail=True)
            if pertemuan is not None:
                _isi_absensi(pertemuan["session_id"], pertemuan=pertemuan)
        elif choice == "rekap":
            program_id = _pilih_program()
            if program_id is None:
                continue
            ok, rows = _run_service(academic_service.rekap_absensi, program_id)
            if ok:
                _tabel("Rekap Absensi Siswa", rows, [
                    ("nis", "NIS"), ("nama_lengkap", "Nama"), ("enrollment_id", "Pendaftaran"),
                    ("total_pertemuan", "Sesi selesai"), ("hadir", "Hadir"), ("izin", "Izin"), ("sakit", "Sakit"),
                    ("alpa", "Alpa"), ("persen_hadir", "% Hadir"),
                ])
            _pause()


def _nilai():
    while True:
        choice = _pilih("Nilai", [
            Choice("Input nilai", value="input"),
            Choice("Ubah nilai yang saya input", value="ubah"),
            Choice("Lihat nilai kelas dan nilai akhir berbobot", value="kelas"),
            Choice("Kembali", value="back"),
        ])
        if choice in (None, "back"):
            return
        program_id = _pilih_program()
        if program_id is None:
            continue
        if choice == "kelas":
            ok, rows = _run_service(academic_service.nilai_kelas, program_id)
            if ok:
                _tabel("Nilai Kelas (nilai akhir berbobot)", rows, [
                    ("nis", "NIS"), ("nama_lengkap", "Nama"), ("enrollment_id", "Pendaftaran"), ("tugas", "Tugas"),
                    ("kuis", "Kuis"), ("uts", "UTS"), ("uas", "UAS"),
                    ("nilai_akhir", "Nilai Akhir"),
                ])
            _pause()
        elif choice == "input":
            student_id = _pilih_siswa(program_id)
            if student_id is None:
                continue
            jenis = _pilih("Jenis nilai", [Choice(_LABEL_JENIS[k], value=k) for k in _LABEL_JENIS])
            if jenis is None:
                continue
            judul = _form_teks("Judul nilai (opsional):", bagian="NILAI • INPUT BARU")
            if judul is None:
                continue
            nilai = _form_teks("Nilai 0-100 (boleh desimal, contoh 87,5):", bagian="NILAI • INPUT BARU")
            if nilai is None:
                continue
            tanggal = _form_teks("Tanggal YYYY-MM-DD (kosong = hari ini):", default="", bagian="NILAI • INPUT BARU")
            if tanggal is None:
                continue
            ok, message = _run_service(academic_service.input_nilai, program_id, student_id, jenis, nilai, judul, tanggal or None)
            if ok:
                _hasil(message, True, "NILAI TERSIMPAN")
            _pause()
        else:
            ok, grades = _run_service(academic_service.daftar_nilai, program_id, hanya_milik_tutor=True)
            if not ok:
                _pause(); continue
            if not grades:
                peringatan("Belum ada nilai yang dapat diubah pada kelas ini.")
                _pause(); continue
            grade_id = _pilih("Pilih nilai yang akan diubah:", [Choice(
                f"ID {g['grade_id']} | {g['nis'] or '-'} {g['nama_lengkap']} | "
                f"{g['jenis']} | {g['judul'] or '-'} | {g['nilai']} | {_teks_nilai(g['tanggal'])}",
                value=g["grade_id"],
            ) for g in grades])
            if grade_id is None:
                continue
            old = next(g for g in grades if g["grade_id"] == grade_id)
            # Tutor dapat mengubah jenis nilai jika salah input.
            jenis = _pilih("Jenis nilai", [Choice(_LABEL_JENIS[k], value=k) for k in _LABEL_JENIS])
            if jenis is None:
                continue
            judul = _form_teks("Judul nilai:", default=old.get("judul") or "", bagian="NILAI • UBAH DATA")
            nilai = _form_teks("Nilai baru 0-100:", default=str(old["nilai"]), bagian="NILAI • UBAH DATA") if judul is not None else None
            tanggal = _form_teks("Tanggal YYYY-MM-DD:", default=str(old["tanggal"]), bagian="NILAI • UBAH DATA") if nilai is not None else None
            if judul is None or nilai is None or tanggal is None:
                continue
            ok, message = _run_service(academic_service.ubah_nilai, grade_id, jenis, nilai, judul, tanggal or None)
            if ok:
                _hasil(message, True, "NILAI DIPERBARUI")
            _pause()


def _materi():
    while True:
        choice = _pilih("Catatan Materi", [
            Choice("Tulis / ubah topik dan ringkasan pertemuan", value="tulis"),
            Choice("Daftar catatan sebelumnya", value="daftar"),
            Choice("Kembali", value="back"),
        ])
        if choice in (None, "back"):
            return
        program_id = _pilih_program() if choice == "tulis" else None
        if choice == "tulis" and program_id is None:
            continue
        ok, sessions = _run_service(academic_service.daftar_pertemuan, program_id)
        if not ok:
            _pause(); continue
        if not sessions:
            peringatan("Belum ada laporan pertemuan. Kelola pertemuan hari ini lewat menu Absensi dahulu.")
            _pause(); continue
        if choice == "tulis":
            session_id = _pilih("Pilih pertemuan untuk catatan:", [Choice(
                f"{_teks_nilai(s['tanggal'])} | Pertemuan {s['pertemuan_ke']} | {s['nama_program']} | {s.get('topik') or 'Belum ada topik'}",
                value=s["session_id"],
            ) for s in sessions])
            if session_id is None:
                continue
            old = next(s for s in sessions if s["session_id"] == session_id)
            topik = _form_teks("Topik pertemuan:", default=old.get("topik") or "", bagian="CATATAN MATERI • TOPIK")
            ringkasan = _form_teks("Ringkasan materi:", default=old.get("ringkasan") or "", bagian="CATATAN MATERI • RINGKASAN") if topik is not None else None
            if topik is None or ringkasan is None:
                continue
            ok, message = _run_service(academic_service.simpan_catatan, session_id, topik, ringkasan)
            if ok:
                _hasil(message, True, "CATATAN MATERI TERSIMPAN")
            _pause()
        else:
            ok, notes = _run_service(academic_service.daftar_catatan, None)
            if ok:
                _tabel("Catatan Materi Sebelumnya", notes, [
                    ("tanggal", "Tanggal"), ("kode_program", "Kode"), ("nama_program", "Program"),
                    ("pertemuan_ke", "Pertemuan"), ("topik", "Topik"), ("ringkasan", "Ringkasan"),
                ])
            _pause()


def _profil():
    while True:
        choice = _pilih("Profil Tutor", [
            Choice("Lihat profil", value="lihat"),
            Choice("Ubah keahlian dan nomor HP", value="ubah"),
            Choice("Ganti password", value="password"),
            Choice("Kembali", value="back"),
        ])
        if choice in (None, "back"):
            return
        if choice == "password":
            lama = _form_teks("Password lama:", bagian="PROFIL • GANTI PASSWORD", password=True)
            baru = _form_teks("Password baru:", bagian="PROFIL • GANTI PASSWORD", password=True) if lama is not None else None
            konfirmasi = _form_teks("Ulangi password baru:", bagian="PROFIL • GANTI PASSWORD", password=True) if baru is not None else None
            if lama is None or baru is None or konfirmasi is None:
                continue
            ok, message = _run_service(tutor_service.ganti_password, lama, baru, konfirmasi)
            if ok:
                _hasil(message, True, "PASSWORD DIPERBARUI")
            _pause()
            continue
        ok, profile = _run_service(tutor_service.profil)
        if not ok:
            _pause(); continue
        if choice == "lihat":
            _layar("PROFIL TUTOR", "Informasi akun dan data profesional")
            console.print(Panel(
                f"[bold cyan]{profile['nama_lengkap']}[/]\nUsername: {profile['username']}\n"
                f"Email: {profile['email']}\nKode tutor: {profile.get('kode_tutor') or '-'}\n"
                f"Keahlian: {profile.get('keahlian') or '-'}\nNomor HP: {profile.get('no_hp') or '-'}\n"
                f"Status akun: {profile['status_akun']}",
                title="Profil Tutor", border_style="cyan", padding=(1, 2),
            ))
            _pause()
        else:
            keahlian = _form_teks("Keahlian:", default=profile.get("keahlian") or "", bagian="PROFIL • UBAH DATA")
            no_hp = _form_teks("Nomor HP:", default=profile.get("no_hp") or "", bagian="PROFIL • UBAH DATA") if keahlian is not None else None
            if keahlian is None or no_hp is None:
                continue
            ok, message = _run_service(tutor_service.ubah_profil, keahlian, no_hp)
            if ok:
                _hasil(message, True, "PROFIL DIPERBARUI")
            _pause()


def jalankan_modul(modul: str):
    if modul == "jadwal":
        while True:
            choice = _pilih("Jadwal Mengajar", [Choice("Jadwal hari ini", value="hari"), Choice("Jadwal mingguan", value="minggu"), Choice("Kembali", value="back")])
            if choice in (None, "back"):
                return
            _jadwal_hari_ini() if choice == "hari" else _jadwal_mingguan()
    elif modul == "kelas":
        _kelas_dan_siswa()
    elif modul == "absensi":
        _absensi()
    elif modul == "nilai":
        _nilai()
    elif modul == "materi":
        _materi()
    elif modul == "profil":
        _profil()
