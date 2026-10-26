"""Submenu pembayaran untuk admin dan siswa.

VA pada tahap ini berupa nomor referensi internal. Tidak ada koneksi bank/payment gateway.
"""

from datetime import date, datetime

import psycopg
import questionary
from questionary import Choice, Separator, Style
from rich.panel import Panel
from rich.table import Table

from app import session
from app.repositories import billing_repo
from app.services import billing_service
from app.ui.console import bersihkan_layar, console, gagal, info, peringatan, sukses
from app.utils.formatters import rupiah


GAYA_BAYAR = Style([
    ("qmark", "fg:#00ffff bold"),
    ("question", "fg:#ffffff bold"),
    ("answer", "fg:#00ffff bold"),
    ("pointer", "fg:#00ffff bold"),
    ("highlighted", "fg:#00ffff bold"),
    ("selected", "fg:#00ffff"),
    ("separator", "fg:#444444"),
    ("instruction", "fg:#888888 italic"),
])

_LABEL_TAGIHAN = {
    "belum_dibayar": "BELUM DIBAYAR",
    "lunas": "LUNAS",
    "batal": "DIBATALKAN",
}
_LABEL_BAYAR = {
    "menunggu_pembayaran": "MENUNGGU PEMBAYARAN",
    "menunggu_konfirmasi": "MENUNGGU KONFIRMASI ADMIN",
    "lunas": "LUNAS",
    "ditolak": "DITOLAK",
}


def _jeda(pesan="Tekan Enter untuk kembali..."):
    try:
        input(pesan)
    except (EOFError, KeyboardInterrupt):
        pass


def _waktu(value):
    if value is None:
        return "-"
    if isinstance(value, (date, datetime)):
        return value.strftime("%d-%m-%Y %H:%M" if isinstance(value, datetime) else "%d-%m-%Y")
    return str(value)


def _header(judul, subjudul):
    console.print(Panel(
        f"[bold cyan]S I B I M A[/bold cyan]\n[bold white]{judul.upper()}[/bold white]\n[dim]{subjudul}[/dim]",
        border_style="cyan", padding=(1, 3), expand=True,
    ))


def _tabel_tagihan(data, judul="Daftar Tagihan"):
    tabel = Table(title=judul, header_style="bold cyan", expand=True)
    for label, kw in [
        ("ID", {"width": 6}), ("No. Invoice", {"min_width": 20}),
        ("NIS", {"width": 10}), ("Siswa", {"min_width": 18}),
        ("Program", {"min_width": 18}), ("Periode", {"width": 12}),
        ("Jumlah", {"justify": "right", "min_width": 15}),
        ("Jatuh tempo", {"width": 12}), ("Status", {"min_width": 18}),
        ("Status pembayaran", {"min_width": 20}),
    ]:
        tabel.add_column(label, **kw)
    for item in data:
        status_i = item.get("invoice_status", "-")
        status_p = item.get("payment_status") or "belum_dibuat"
        if status_i == "belum_dibayar" and item.get("jatuh_tempo") and item["jatuh_tempo"] < date.today():
            status_i = "menunggak"
        tabel.add_row(
            str(item.get("invoice_id", "-")), str(item.get("no_invoice", "-")),
            str(item.get("nis") or "-"), str(item.get("nama_siswa") or "-"),
            str(item.get("nama_program") or "-"), _waktu(item.get("periode")),
            rupiah(item.get("jumlah") or 0), _waktu(item.get("jatuh_tempo")),
            _LABEL_TAGIHAN.get(status_i, status_i.replace("_", " ").upper()),
            _LABEL_BAYAR.get(status_p, "BELUM ADA PEMBAYARAN" if status_p == "belum_dibuat" else status_p),
        )
    if not data:
        tabel.add_row("-", "Tidak ada tagihan", "-", "-", "-", "-", "-", "-", "-", "-")
    console.print(tabel)


def _tabel_pembayaran(data, judul="Riwayat Pembayaran"):
    tabel = Table(title=judul, header_style="bold cyan", expand=True)
    tabel.add_column("ID", width=6)
    tabel.add_column("Kode VA", min_width=20)
    tabel.add_column("Invoice", min_width=20)
    tabel.add_column("NIS", width=10)
    tabel.add_column("Siswa", min_width=18)
    tabel.add_column("Program", min_width=18)
    tabel.add_column("Nominal", justify="right", min_width=15)
    tabel.add_column("Status", min_width=22)
    tabel.add_column("Waktu bayar", min_width=18)
    for item in data:
        tabel.add_row(
            str(item.get("payment_id", "-")), str(item.get("kode_bayar", "-")),
            str(item.get("no_invoice", "-")), str(item.get("nis") or "-"),
            str(item.get("nama_siswa") or "-"), str(item.get("nama_program") or "-"),
            rupiah(item.get("payment_jumlah") or 0),
            _LABEL_BAYAR.get(item.get("payment_status"), str(item.get("payment_status") or "-").upper()),
            _waktu(item.get("paid_at")),
        )
    if not data:
        tabel.add_row("-", "Belum ada riwayat pembayaran", "-", "-", "-", "-", "-", "-", "-")
    console.print(tabel)


def _aksi_buat_bukti_pdf(payment_id):
    try:
        path = billing_service.buat_bukti_pembayaran_pdf(payment_id)
        sukses(f"Bukti PDF berhasil dibuat: {path}")
    except (ValueError, PermissionError, LookupError) as exc:
        gagal(str(exc))
    except ImportError:
        gagal("Modul PDF belum terpasang. Jalankan: python -m pip install -r requirements.txt")
    except (OSError, psycopg.Error) as exc:
        gagal(f"Gagal membuat bukti PDF ({type(exc).__name__}).")
    _jeda()


def _aksi_kirim_bukti_email(payment_id, siswa=False):
    try:
        detail = (
            billing_service.bukti_pembayaran_saya(payment_id)
            if siswa else billing_service.bukti_pembayaran_admin(payment_id)
        )
        if not detail:
            peringatan("Bukti hanya tersedia untuk pembayaran berstatus LUNAS.")
            _jeda()
            return
        email = str(detail.get("email_siswa") or "").strip()
        if not email:
            gagal("Akun siswa belum memiliki alamat email. Periksa data akun siswa terlebih dahulu.")
            _jeda()
            return
        yakin = questionary.confirm(
            f"Kirim bukti PDF pembayaran ke email terdaftar {email}?",
            default=False, style=GAYA_BAYAR,
        ).ask()
        if yakin is not True:
            info("Pengiriman email dibatalkan.")
            _jeda()
            return
        hasil = billing_service.kirim_bukti_pembayaran_email(payment_id)
        if hasil.get("sent"):
            sukses(hasil.get("message", "Bukti PDF berhasil dikirim melalui email."))
        else:
            gagal(hasil.get("message", "Email tidak berhasil dikirim."))
            if hasil.get("path"):
                info(f"PDF tetap tersimpan: {hasil['path']}")
    except (ValueError, PermissionError, LookupError) as exc:
        gagal(str(exc))
    except ImportError:
        gagal("Modul PDF belum terpasang. Jalankan: python -m pip install -r requirements.txt")
    except (OSError, psycopg.Error) as exc:
        gagal(f"Gagal memproses bukti/email ({type(exc).__name__}).")
    _jeda()


def _pilih_payment(data, prompt="Pilih pembayaran:"):
    if not data:
        peringatan("Tidak ada data pembayaran yang dapat dipilih.")
        _jeda()
        return None
    choices = [
        Choice(
            f"#{x['payment_id']} • {x.get('kode_bayar', '-')} • {x.get('no_invoice', '-')} • "
            f"{rupiah(x.get('payment_jumlah') or 0)} • {_LABEL_BAYAR.get(x.get('payment_status'), x.get('payment_status', '-'))}",
            value=x["payment_id"],
        )
        for x in data
    ]
    choices.extend([Separator("────────────────────────"), Choice("Kembali", value="kembali")])
    selected = questionary.select(prompt, choices=choices, style=GAYA_BAYAR, qmark="💳", pointer="▶").ask()
    return None if selected in (None, "kembali") else selected



def _admin_daftar_tagihan():
    filter_status = questionary.select(
        "Filter status tagihan:",
        choices=[
            Choice("Semua status", value="semua"),
            Choice("Belum dibayar", value="belum_dibayar"),
            Choice("Lunas", value="lunas"),
            Choice("Dibatalkan", value="batal"),
            Separator("────────────────────────"), Choice("Kembali", value="kembali"),
        ], style=GAYA_BAYAR, qmark="🔎", pointer="▶",
    ).ask()
    if filter_status in (None, "kembali"):
        return
    try:
        data = billing_service.daftar_tagihan_admin(status=None if filter_status == "semua" else filter_status)
        bersihkan_layar()
        _header("Pembayaran", "DAFTAR TAGIHAN")
        _tabel_tagihan(data)
    except (ValueError, PermissionError) as exc:
        gagal(str(exc))
    except psycopg.Error as exc:
        gagal(f"Gagal memuat tagihan ({type(exc).__name__}).")
    _jeda()


def _admin_daftar_tunggakan():
    try:
        data = billing_service.daftar_tagihan_admin(tunggakan=True)
        bersihkan_layar()
        _header("Pembayaran", "DAFTAR TUNGGAKAN")
        _tabel_tagihan(data, "Tagihan Belum Lunas yang Melewati Jatuh Tempo")
    except (ValueError, PermissionError) as exc:
        gagal(str(exc))
    except psycopg.Error as exc:
        gagal(f"Gagal memuat tunggakan ({type(exc).__name__}).")
    _jeda()


def _admin_riwayat():
    try:
        data = billing_service.riwayat_pembayaran_admin()
        bersihkan_layar()
        _header("Pembayaran", "RIWAYAT PEMBAYARAN")
        _tabel_pembayaran(data)
    except (ValueError, PermissionError) as exc:
        gagal(str(exc))
    except psycopg.Error as exc:
        gagal(f"Gagal memuat riwayat ({type(exc).__name__}).")
    _jeda()


def _admin_pilih_bukti(mode="pdf"):
    try:
        data = [x for x in billing_service.riwayat_pembayaran_admin() if x.get("payment_status") == "lunas"]
        judul = "Pilih Pembayaran Lunas untuk Bukti PDF" if mode == "pdf" else "Pilih Pembayaran Lunas untuk Email"
        _tabel_pembayaran(data, judul)
        payment_id = _pilih_payment(data, "Pilih pembayaran lunas:")
        if payment_id is not None:
            if mode == "pdf":
                _aksi_buat_bukti_pdf(payment_id)
            else:
                _aksi_kirim_bukti_email(payment_id, siswa=False)
    except (ValueError, PermissionError, LookupError) as exc:
        gagal(str(exc))
        _jeda()
    except psycopg.Error as exc:
        gagal(f"Gagal mengambil riwayat ({type(exc).__name__}).")
        _jeda()


def menu_pembayaran_admin():
    """Submenu tagihan, tunggakan, riwayat, dan bukti pembayaran admin."""
    if not session.punya_role("admin"):
        peringatan("Akses ditolak. Menu ini khusus admin.")
        return
    while session.punya_role("admin"):
        bersihkan_layar()
        _header("Pembayaran", "TAGIHAN DAN PEMBAYARAN")
        selected = questionary.select(
            "Pilih tindakan:",
            choices=[
                Choice("Buat tagihan bulanan", "tagihan_bulanan"),
                Choice("Daftar tagihan (filter status)", "daftar"),
                Choice("Daftar tunggakan", "tunggakan"),
                Choice("Riwayat pembayaran", "riwayat"),
                Choice("Unduh bukti pembayaran (PDF)", "bukti_pdf"),
                Choice("Kirim bukti pembayaran via email", "bukti_email"),
                Separator("────────────────────────"),
                Choice("Kembali ke dashboard", "kembali"),
            ], style=GAYA_BAYAR, qmark="💳", pointer="▶",
        ).ask()
        if selected in (None, "kembali"):
            return
        if selected == "tagihan_bulanan":
            yakin = questionary.confirm(
                "Buat tagihan bulan berjalan untuk semua enrollment aktif yang belum memiliki invoice?",
                default=False, style=GAYA_BAYAR,
            ).ask()
            if yakin is True:
                try:
                    jumlah = billing_service.buat_tagihan_bulanan()
                    sukses(f"Pembuatan selesai. Tagihan baru dibuat: {jumlah}.")
                except (ValueError, PermissionError) as exc:
                    gagal(str(exc))
                except psycopg.Error as exc:
                    gagal(f"Gagal membuat tagihan ({type(exc).__name__}).")
                _jeda()
        elif selected == "daftar":
            _admin_daftar_tagihan()
        elif selected == "tunggakan":
            _admin_daftar_tunggakan()
        elif selected == "riwayat":
            _admin_riwayat()
        elif selected == "bukti_pdf":
            _admin_pilih_bukti("pdf")
        elif selected == "bukti_email":
            _admin_pilih_bukti("email")


def _admin_proses_satu_pembayaran(payment_id, data):
    item = next((x for x in data if x.get("payment_id") == payment_id), None)
    if item is None:
        peringatan("Pembayaran tidak ditemukan pada antrean terbaru.")
        _jeda()
        return

    tabel = Table(show_header=False, box=None, expand=True)
    tabel.add_column("Data", style="cyan", width=24)
    tabel.add_column("Nilai", overflow="fold")
    for k, v in [
        ("ID pembayaran", item.get("payment_id")), ("Kode VA", item.get("kode_bayar")),
        ("Nomor invoice", item.get("no_invoice")), ("Siswa", item.get("nama_siswa")),
        ("NIS", item.get("nis") or "-"), ("Program", item.get("nama_program")),
        ("Nominal VA", rupiah(item.get("payment_jumlah") or 0)),
        ("Total tagihan", rupiah(item.get("invoice_jumlah") or 0)),
        ("Waktu siswa melapor", _waktu(item.get("paid_at"))),
    ]:
        tabel.add_row(str(k), str(v if v is not None else "-"))
    console.print(Panel(tabel, title="[bold cyan]DETAIL KONFIRMASI PEMBAYARAN[/bold cyan]", border_style="cyan"))
    keputusan = questionary.select(
        "Tindakan:",
        choices=[Choice("Setujui — tandai lunas", "lunas"), Choice("Tolak pembayaran", "ditolak"), Choice("Kembali", "kembali")],
        style=GAYA_BAYAR, qmark="⚡", pointer="▶",
    ).ask()
    if keputusan in (None, "kembali"):
        return
    alasan = None
    if keputusan == "ditolak":
        alasan = questionary.text("Alasan penolakan (wajib):", style=GAYA_BAYAR).ask()
        if alasan is None or not alasan.strip():
            peringatan("Penolakan dibatalkan karena alasan wajib diisi.")
            _jeda()
            return
    yakin = questionary.confirm(
        "Konfirmasi keputusan ini? Status tagihan akan ikut menjadi LUNAS jika disetujui.",
        default=False, style=GAYA_BAYAR,
    ).ask()
    if yakin is not True:
        info("Keputusan tidak disimpan.")
        _jeda()
        return
    try:
        billing_service.proses_konfirmasi_admin(payment_id, keputusan, alasan)
        sukses("Pembayaran disetujui dan tagihan lunas." if keputusan == "lunas" else "Pembayaran ditolak; tagihan tetap belum dibayar.")
    except (ValueError, PermissionError, LookupError) as exc:
        gagal(str(exc))
    except psycopg.Error as exc:
        gagal(f"Gagal memproses pembayaran ({type(exc).__name__}).")
    _jeda()


def menu_konfirmasi_pembayaran():
    """Antrean pembayaran yang dilaporkan sudah dibayar oleh siswa."""
    if not session.punya_role("admin"):
        peringatan("Akses ditolak. Menu ini khusus admin.")
        return
    while session.punya_role("admin"):
        try:
            data = billing_service.daftar_konfirmasi_pembayaran()
        except (ValueError, PermissionError) as exc:
            gagal(str(exc))
            _jeda()
            return
        except psycopg.Error as exc:
            gagal(f"Gagal memuat antrean pembayaran ({type(exc).__name__}).")
            _jeda()
            return
        bersihkan_layar()
        _header("Pusat Konfirmasi", "KONFIRMASI PEMBAYARAN")
        _tabel_pembayaran(data, "Pembayaran Menunggu Konfirmasi")
        choices = [
            Choice(
                f"#{x['payment_id']} • {x.get('nama_siswa', '-')} • {x.get('no_invoice', '-')} • "
                f"{rupiah(x.get('payment_jumlah') or 0)}",
                value=x["payment_id"],
            ) for x in data
        ]
        if choices:
            choices.append(Separator("────────────────────────"))
        choices.extend([Choice("Muat ulang antrean", "refresh"), Choice("Kembali", "kembali")])
        selected = questionary.select("Pilih pembayaran untuk diproses:", choices=choices, style=GAYA_BAYAR, qmark="💳", pointer="▶").ask()
        if selected in (None, "kembali"):
            return
        if selected == "refresh":
            continue
        _admin_proses_satu_pembayaran(selected, data)


def _siswa_tagihan_saya():
    try:
        data = billing_service.daftar_tagihan_saya()
        bersihkan_layar()
        _header("Tagihan Saya", "STATUS TAGIHAN PROGRAM")
        _tabel_tagihan(data, "Tagihan Milik Akun Ini")
    except (ValueError, PermissionError) as exc:
        gagal(str(exc))
    except psycopg.Error as exc:
        gagal(f"Gagal memuat tagihan ({type(exc).__name__}).")
    _jeda()


def _siswa_bayar_tagihan():
    try:
        data = billing_service.daftar_tagihan_saya(status="belum_dibayar")
    except (ValueError, PermissionError) as exc:
        gagal(str(exc)); _jeda(); return
    except psycopg.Error as exc:
        gagal(f"Gagal memuat tagihan ({type(exc).__name__})."); _jeda(); return

    bersihkan_layar()
    _header("Pembayaran", "BAYAR TAGIHAN DENGAN VIRTUAL ACCOUNT")
    _tabel_tagihan(data, "Pilih Tagihan Belum Lunas")
    eligible = [x for x in data if (x.get("jumlah") or 0) > 0]
    if not eligible:
        info("Tidak ada tagihan belum lunas yang bisa dibayar saat ini.")
        _jeda()
        return
    choices = [
        Choice(
            f"{x.get('no_invoice', '-')} • {x.get('nama_program', '-')} • "
            f"{_waktu(x.get('periode'))} • {rupiah(x.get('jumlah') or 0)}",
            value=x["invoice_id"],
        ) for x in eligible
    ]
    choices.extend([Separator("────────────────────────"), Choice("Kembali", "kembali")])
    invoice_id = questionary.select("Pilih tagihan yang ingin dibayar:", choices=choices, style=GAYA_BAYAR, qmark="💳", pointer="▶").ask()
    if invoice_id in (None, "kembali"):
        return

    try:
        payment = billing_service.mulai_pembayaran_va(invoice_id)
        bersihkan_layar()
        _header("Pembayaran", "REFERENSI VIRTUAL ACCOUNT")
        console.print(Panel(
            f"[bold white]Nomor Virtual Account[/bold white]\n[bold cyan]{payment['kode_bayar']}[/bold cyan]\n\n"
            f"[bold white]Nominal penuh[/bold white]\n[bold green]{rupiah(payment['jumlah'])}[/bold green]\n\n"
            f"Status: {_LABEL_BAYAR.get(payment.get('payment_status'), payment.get('payment_status', '-'))}\n\n"
            "[yellow]Catatan:[/yellow] nomor VA ini merupakan referensi internal aplikasi. "
            "Belum ada integrasi otomatis ke bank. Setelah pembayaran dilakukan di luar aplikasi, "
            "pilih ‘Saya sudah membayar’ agar admin memeriksa dan mengonfirmasi secara manual.",
            title="[bold cyan]DETAIL PEMBAYARAN[/bold cyan]", border_style="cyan", padding=(1, 3), expand=True,
        ))
        if payment.get("payment_status") == "menunggu_pembayaran":
            sudah = questionary.confirm(
                "Kamu benar-benar sudah melakukan pembayaran penuh dan ingin mengirim konfirmasi ke admin?",
                default=False, style=GAYA_BAYAR,
            ).ask()
            if sudah is True:
                billing_service.konfirmasi_sudah_bayar(payment["payment_id"])
                sukses("Konfirmasi pembayaran terkirim. Tunggu pemeriksaan admin.")
            else:
                info("Pembayaran belum dikirim untuk konfirmasi. Kode VA tetap bisa dilihat dari proses Bayar Tagihan.")
        elif payment.get("payment_status") == "menunggu_konfirmasi":
            info("Pembayaran ini sudah menunggu pemeriksaan admin; tidak perlu mengirim ulang.")
    except (ValueError, PermissionError, LookupError) as exc:
        gagal(str(exc))
    except psycopg.Error as exc:
        gagal(f"Gagal memproses pembayaran ({type(exc).__name__}).")
    _jeda()


def _siswa_riwayat():
    try:
        data = billing_service.riwayat_pembayaran_saya()
        bersihkan_layar()
        _header("Pembayaran", "RIWAYAT PEMBAYARAN SAYA")
        _tabel_pembayaran(data)
        if data:
            tabel_alasan = Table(title="Catatan Penolakan (jika ada)", header_style="bold cyan", expand=True)
            tabel_alasan.add_column("Kode VA")
            tabel_alasan.add_column("Status")
            tabel_alasan.add_column("Alasan", overflow="fold")
            for item in data:
                if item.get("alasan_tolak"):
                    tabel_alasan.add_row(str(item.get("kode_bayar")), str(item.get("payment_status")), str(item["alasan_tolak"]))
            if tabel_alasan.row_count:
                console.print(tabel_alasan)
    except (ValueError, PermissionError) as exc:
        gagal(str(exc))
    except psycopg.Error as exc:
        gagal(f"Gagal memuat riwayat ({type(exc).__name__}).")
    _jeda()


def _siswa_pilih_bukti(mode="pdf"):
    try:
        data = [x for x in billing_service.riwayat_pembayaran_saya() if x.get("payment_status") == "lunas"]
        judul = "Bukti Pembayaran Lunas (PDF)" if mode == "pdf" else "Pilih Bukti untuk Dikirim via Email"
        _tabel_pembayaran(data, judul)
        payment_id = _pilih_payment(data, "Pilih pembayaran lunas:")
        if payment_id is not None:
            if mode == "pdf":
                _aksi_buat_bukti_pdf(payment_id)
            else:
                _aksi_kirim_bukti_email(payment_id, siswa=True)
    except (ValueError, PermissionError, LookupError) as exc:
        gagal(str(exc))
        _jeda()
    except psycopg.Error as exc:
        gagal(f"Gagal mengambil riwayat ({type(exc).__name__}).")
        _jeda()


def menu_pembayaran_siswa():
    """Submenu tagihan, VA, riwayat, dan bukti pembayaran untuk siswa."""
    if not session.punya_role("siswa"):
        peringatan("Akses ditolak. Menu ini khusus siswa.")
        return
    while session.punya_role("siswa"):
        bersihkan_layar()
        _header("Pembayaran", "TAGIHAN DAN PEMBAYARAN SAYA")
        selected = questionary.select(
            "Pilih tindakan:",
            choices=[
                Choice("Tagihan saya (status)", "tagihan"),
                Choice("Bayar tagihan — nomor Virtual Account", "bayar"),
                Choice("Riwayat pembayaran", "riwayat"),
                Choice("Unduh bukti pembayaran (PDF)", "bukti_pdf"),
                Choice("Kirim bukti pembayaran ke email terdaftar", "bukti_email"),
                Separator("────────────────────────"), Choice("Kembali ke dashboard", "kembali"),
            ], style=GAYA_BAYAR, qmark="💳", pointer="▶",
        ).ask()
        if selected in (None, "kembali"):
            return
        if selected == "tagihan":
            _siswa_tagihan_saya()
        elif selected == "bayar":
            _siswa_bayar_tagihan()
        elif selected == "riwayat":
            _siswa_riwayat()
        elif selected == "bukti_pdf":
            _siswa_pilih_bukti("pdf")
        elif selected == "bukti_email":
            _siswa_pilih_bukti("email")
