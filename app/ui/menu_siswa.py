"""Dashboard siswa SIBIMA dengan tampilan menyesuaikan status kelas."""

import psycopg
import questionary
from questionary import Choice, Separator, Style
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app import session
from app.repositories import enrollment_repo, program_repo, user_repo
from app.services import billing_service, enrollment_service, engagement_service, student_service
from app.ui import menu_pembayaran, menu_siswa_academic, menu_notifikasi
from app.ui.console import (
    bersihkan_layar,
    console,
    gagal,
    info,
    peringatan,
    sukses,
)
from app.utils.formatters import rupiah


GAYA_SIBIMA = Style([
    ("qmark", "fg:#00ffff bold"),
    ("question", "fg:#ffffff bold"),
    ("answer", "fg:#00ffff bold"),
    ("pointer", "fg:#00ffff bold"),
    ("highlighted", "fg:#00ffff bold"),
    ("selected", "fg:#00ffff"),
    ("separator", "fg:#444444"),
    ("instruction", "fg:#888888 italic"),
])


STATUS_LABEL = {
    "menunggu": "MENUNGGU PERSETUJUAN",
    "aktif": "AKTIF",
    "ditolak": "DITOLAK",
    "batal": "DIBATALKAN",
    "selesai": "SELESAI",
}


def _jeda(pesan="Tekan Enter untuk melanjutkan..."):
    try:
        input(f"\n{pesan}")
    except (EOFError, KeyboardInterrupt):
        pass


def _pengguna_siswa():
    pengguna = session.get_user()
    if not pengguna:
        return None
    if pengguna.get("role") != "siswa":
        return None
    if type(pengguna.get("id")) is not int:
        return None
    return pengguna


def _ambil_pendaftaran(student_id):
    """Mengambil riwayat enrollment siswa yang sedang login."""
    return enrollment_repo.enrollment_siswa(student_id)


def _kartu_ringkas(enrollments):
    aktif = [item for item in enrollments if item["status"] == "aktif"]
    menunggu = [item for item in enrollments if item["status"] == "menunggu"]
    riwayat = [
        item for item in enrollments
        if item["status"] in {"ditolak", "batal", "selesai"}
    ]

    kartu = [
        Panel(
            f"[bold green]{len(aktif)}[/bold green]\n[white]Kelas aktif[/white]",
            title="[bold]KELAS[/bold]",
            border_style="green" if aktif else "dim",
            expand=True,
        ),
        Panel(
            f"[bold yellow]{len(menunggu)}[/bold yellow]\n[white]Menunggu admin[/white]",
            title="[bold]ANTREAN[/bold]",
            border_style="yellow" if menunggu else "dim",
            expand=True,
        ),
        Panel(
            f"[bold cyan]{len(riwayat)}[/bold cyan]\n[white]Riwayat lain[/white]",
            title="[bold]RIWAYAT[/bold]",
            border_style="cyan" if riwayat else "dim",
            expand=True,
        ),
    ]
    console.print(Columns(kartu, equal=True, expand=True))


def _tabel_pendaftaran(enrollments, judul="Kelas dan Status Pendaftaran"):
    tabel = Table(title=judul, header_style="bold cyan", expand=True)
    tabel.add_column("Program", min_width=22)
    tabel.add_column("Jenjang", min_width=10)
    tabel.add_column("Status", min_width=24)
    tabel.add_column("Tanggal daftar", min_width=18)

    for item in enrollments:
        dibuat = item.get("created_at")
        tanggal = dibuat.strftime("%d %b %Y") if dibuat else "-"
        status = item.get("status", "-")
        if status == "aktif":
            gaya = "green"
        elif status == "menunggu":
            gaya = "yellow"
        elif status == "ditolak":
            gaya = "red"
        else:
            gaya = "cyan"
        tabel.add_row(
            str(item.get("nama_program") or "-"),
            str(item.get("jenjang") or "-"),
            f"[{gaya}]{STATUS_LABEL.get(status, status.upper())}[/{gaya}]",
            tanggal,
        )

    if not enrollments:
        tabel.add_row("Belum ada pendaftaran", "-", "-", "-")

    console.print(tabel)


def _dashboard(pengguna, enrollments):
    bersihkan_layar()
    console.print(
        Panel(
            "[bold cyan]S I B I M A[/bold cyan]\n"
            "[bold white]DASHBOARD SISWA[/bold white]",
            border_style="cyan",
            padding=(1, 4),
            expand=True,
        )
    )
    console.print(
        Panel(
            f"[bold white]Halo, [cyan]{pengguna.get('nama_lengkap', pengguna.get('username', 'Siswa'))}[/cyan]![/bold white]\n"
            "[dim]PANTAU PROGRAM, PENDAFTARAN, DAN KEGIATAN BELAJARMU[/dim]",
            title="[bold cyan]SELAMAT DATANG[/bold cyan]",
            border_style="bright_blue",
            padding=(1, 2),
            expand=True,
        )
    )

    aktif = [item for item in enrollments if item["status"] == "aktif"]
    menunggu = [item for item in enrollments if item["status"] == "menunggu"]

    _kartu_ringkas(enrollments)

    if not enrollments:
        console.print(
            Panel(
                "[bold white]Kamu belum punya kelas bimbel.[/bold white]\n\n"
                "Mulai dari [bold cyan]Katalog Program[/bold cyan] untuk melihat pilihan kelas, "
                "jenjang, biaya bulanan, dan sisa kuota. Setelah mendaftar, statusnya akan "
                "ditampilkan di dashboard sambil menunggu persetujuan admin.",
                title="[bold cyan]MULAI BELAJAR[/bold cyan]",
                border_style="cyan",
                padding=(1, 3),
                expand=True,
            )
        )
    else:
        if aktif:
            console.print(
                Panel(
                    "\n".join(
                        f"[bold green]•[/bold green] {item['nama_program']} — {item.get('jenjang') or 'Jenjang belum diisi'}"
                        for item in aktif[:5]
                    ),
                    title="[bold green]KELAS AKTIF KAMU[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                    expand=True,
                )
            )
        if menunggu:
            console.print(
                Panel(
                    "\n".join(
                        f"[yellow]•[/yellow] {item['nama_program']} — masih menunggu persetujuan admin"
                        for item in menunggu[:5]
                    ),
                    title="[bold yellow]PENDAFTARAN DIPROSES[/bold yellow]",
                    border_style="yellow",
                    padding=(1, 2),
                    expand=True,
                )
            )

    # Ringkasan jadwal dan tagihan di dashboard mengikuti data akun aktif.
    try:
        from datetime import date
        hari_ini = ["senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu"][date.today().weekday()]
        ok_jadwal, jadwal_hari_ini = student_service.jadwal_saya(hari=hari_ini)
        if ok_jadwal:
            if jadwal_hari_ini:
                isi_jadwal = "\n".join(
                    f"[bold cyan]{item['jam_mulai'].strftime('%H:%M') if hasattr(item.get('jam_mulai'), 'strftime') else str(item.get('jam_mulai', '—'))[:5]}[/bold cyan] "
                    f"{item.get('nama_program', '—')} • {item.get('nama_ruang', '—')}"
                    for item in jadwal_hari_ini[:4]
                )
            else:
                isi_jadwal = "Tidak ada jadwal kelas hari ini."
            console.print(Panel(isi_jadwal, title="[bold cyan]JADWAL HARI INI[/bold cyan]", border_style="bright_blue", padding=(1, 2), expand=True))
    except Exception:
        # Ringkasan dashboard tidak boleh menggagalkan akses ke menu utama.
        pass

    try:
        tagihan = billing_service.daftar_tagihan_saya(status="belum_dibayar")
        if tagihan:
            total_tagihan = sum(float(item.get("jumlah") or 0) for item in tagihan)
            info(f"Tagihan belum lunas: {len(tagihan)} invoice • {rupiah(total_tagihan)}")
        else:
            info("Tagihan belum lunas: tidak ada.")
    except Exception:
        peringatan("Ringkasan tagihan sementara tidak dapat dimuat.")



def menu_katalog(pengguna):
    """Menampilkan program yang tersedia dan mengajukan enrollment."""
    while True:
        bersihkan_layar()
        console.print(
            Panel(
                "[bold cyan]KATALOG PROGRAM[/bold cyan]\n"
                "[white]Pilih program yang sesuai dengan kebutuhan belajarmu.[/white]",
                border_style="cyan",
                padding=(1, 3),
                expand=True,
            )
        )

        try:
            semua_program = program_repo.daftar_program_buka_dengan_kuota()
            enrollments = _ambil_pendaftaran(pengguna["id"])
        except psycopg.Error as exc:
            gagal(f"Gagal memuat katalog dari database ({type(exc).__name__}).")
            _jeda()
            return

        # Schema saat ini memiliki UNIQUE(student_id, program_id), sehingga
        # satu program yang sudah pernah didaftarkan tidak dapat didaftarkan ulang.
        pernah_didaftarkan = {item["program_id"] for item in enrollments}
        program_tersedia = [
            p for p in semua_program
            if p["id"] not in pernah_didaftarkan
        ]

        if program_tersedia:
            menu_siswa_academic.tampilkan_katalog_paginasi(program_tersedia)
        else:
            tabel = Table(title="Program Buka dengan Kuota", header_style="bold cyan", expand=True)
            tabel.add_column("Kode", width=8)
            tabel.add_column("Nama program", min_width=24)
            tabel.add_column("Jenjang", width=12)
            tabel.add_column("Biaya/bulan", justify="right", min_width=16)
            tabel.add_column("Kuota", justify="center", width=12)
            tabel.add_column("Deskripsi", min_width=24, overflow="fold")
            tabel.add_row("—", "Tidak ada program baru yang tersedia", "—", "—", "—", "—")
            console.print(tabel)

        if semua_program and not program_tersedia:
            info(
                "Semua program yang tersedia mungkin sudah pernah kamu daftarkan. "
                "Pendaftaran ulang ke program yang sama belum didukung oleh constraint database saat ini."
            )

        dipilih = menu_siswa_academic.pilih_data_paginasi(
            "Pilih program untuk didaftarkan",
            program_tersedia,
            lambda p: f"Daftar: {p['nama']} | {p['jenjang']} | {rupiah(p.get('harga_bulanan') or 0)} | sisa {p.get('sisa', 0)}",
            "id",
        )
        if dipilih is None:
            return

        program = next((p for p in program_tersedia if p["id"] == dipilih), None)
        if program is None:
            peringatan("Program pilihan tidak ditemukan. Muat ulang katalog.")
            _jeda()
            continue

        console.print(
            Panel(
                f"[bold]{program['nama']}[/bold]\n"
                f"Kode: {program['kode']}\n"
                f"Jenjang: {program['jenjang']}\n"
                f"Biaya per bulan: [cyan]{rupiah(program.get('harga_bulanan') or 0)}[/cyan]\n"
                f"Sisa kuota: {program.get('sisa', 0)}\n\n"
                f"{program.get('deskripsi') or 'Belum ada deskripsi.'}",
                title="DETAIL PROGRAM",
                border_style="cyan",
                padding=(1, 2),
                expand=True,
            )
        )

        konfirmasi = questionary.confirm(
            "Kirim pendaftaran program ini ke admin?",
            default=False,
            style=GAYA_SIBIMA,
        ).ask()

        if not konfirmasi:
            continue

        berhasil, pesan = enrollment_service.daftar_program(
            student_id=pengguna["id"],
            program_id=dipilih,
        )
        if berhasil:
            sukses(pesan)
            _jeda("Tekan Enter untuk kembali ke dashboard...")
            return

        gagal(pesan)
        _jeda()


def menu_status_pendaftaran(pengguna, enrollments):
    bersihkan_layar()
    console.print(
        Panel(
            "[bold cyan]KELAS & STATUS PENDAFTARAN[/bold cyan]",
            border_style="cyan",
            padding=(1, 3),
            expand=True,
        )
    )
    _tabel_pendaftaran(enrollments)

    if any(item["status"] in {"ditolak", "batal"} for item in enrollments):
        peringatan(
            "Riwayat yang ditolak/dibatalkan tetap disimpan. Pendaftaran ulang "
            "ke program yang sama belum didukung oleh aturan unik database saat ini."
        )

    _jeda()


def _menu_fitur_belum_terhubung(nama, enrollments):
    bersihkan_layar()
    aktif = [item for item in enrollments if item["status"] == "aktif"]
    menunggu = [item for item in enrollments if item["status"] == "menunggu"]

    if not aktif and nama in {"Jadwal Saya", "Absensi", "Nilai dan Rapor", "Tagihan dan Pembayaran", "Catatan Materi"}:
        if menunggu:
            isi = (
                "Pendaftaran programmu masih menunggu persetujuan admin. "
                "Fitur kelas akan relevan setelah pendaftaran disetujui. "
                "Kamu bisa memantau statusnya melalui menu Kelas & Status Pendaftaran."
            )
        else:
            isi = (
                "Kamu belum memiliki kelas aktif. Buka Katalog Program untuk "
                "memilih dan mendaftarkan diri ke kelas bimbel terlebih dahulu."
            )
        judul_panel = "BELUM ADA KELAS AKTIF"
        warna = "yellow"
    else:
        isi = (
            f"{nama} sudah tersedia sebagai bagian dari rancangan SIBIMA, "
            "tetapi service dan repository untuk fitur ini belum selesai diimplementasikan. "
            "Menu ini belum mengubah data apa pun."
        )
        judul_panel = "FITUR DALAM PENGEMBANGAN"
        warna = "cyan"

    console.print(
        Panel(
            f"[white]{isi}[/white]",
            title=f"[bold {warna}]{judul_panel}[/bold {warna}]",
            border_style=warna,
            padding=(1, 3),
            expand=True,
        )
    )
    _jeda()


def _jalankan_onboarding(pengguna):
    """Alur terbatas untuk siswa terverifikasi yang belum disetujui admin."""
    student_id = pengguna["id"]

    while True:
        # Segarkan status dari database supaya sesi yang sedang menunggu bisa
        # langsung melanjutkan ke dashboard normal setelah admin menyetujui.
        try:
            terbaru = user_repo.cari_by_id(student_id)
            if terbaru is None or terbaru.get("role") != "siswa":
                session.logout()
                gagal("Akun siswa tidak ditemukan. Sesi telah ditutup.")
                _jeda()
                return False
            session.set_user(terbaru)
            pengguna = terbaru

            if terbaru.get("status") == "aktif":
                return True
            if terbaru.get("status") in {"ditolak", "nonaktif"}:
                alasan = terbaru.get("reject_reason") or "Tidak ada keterangan tambahan."
                bersihkan_layar()
                console.print(
                    Panel(
                        f"[bold red]Akun tidak dapat digunakan.[/bold red]\n\n{alasan}",
                        title="STATUS AKUN",
                        border_style="red",
                        padding=(1, 3),
                        expand=True,
                    )
                )
                session.logout()
                _jeda("Tekan Enter untuk kembali ke menu utama...")
                return False
            if not terbaru.get("email_verified"):
                session.logout()
                gagal("Email belum diverifikasi. Silakan verifikasi terlebih dahulu.")
                _jeda()
                return False

            enrollments = enrollment_repo.enrollment_siswa(student_id)
        except psycopg.Error as exc:
            bersihkan_layar()
            gagal(f"Gagal memeriksa status onboarding ({type(exc).__name__}).")
            _jeda()
            return False

        menunggu = [item for item in enrollments if item.get("status") == "menunggu"]
        aktif = [item for item in enrollments if item.get("status") == "aktif"]

        bersihkan_layar()
        console.print(
            Panel(
                "[bold cyan]S I B I M A[/bold cyan]\n"
                "[bold white]PENYELESAIAN PENDAFTARAN SISWA[/bold white]",
                border_style="cyan",
                padding=(1, 4),
                expand=True,
            )
        )
        console.print(
            Panel(
                f"[bold white]Halo, [cyan]{pengguna.get('nama_lengkap', pengguna.get('username', 'Siswa'))}[/cyan]![/bold white]\n\n"
                "Akunmu sedang menunggu persetujuan admin. Setelah akun disetujui, "
                "NIS akan diterbitkan dan kamu dapat mendaftar program secara terpisah.",
                title="STATUS AKUN",
                border_style="bright_blue",
                padding=(1, 2),
                expand=True,
            )
        )

        if menunggu:
            _tabel_pendaftaran(menunggu, judul="Paket yang Menunggu Persetujuan")
            console.print(
                Panel(
                    "[bold yellow]Pilihan paket sudah diterima.[/bold yellow]\n"
                    "Pendaftaran program yang tercatat tetap menunggu keputusan program. "
                    "Persetujuan akun dan penerbitan NIS tetap merupakan proses terpisah.\n"
                    "Gunakan Muat Ulang Status untuk memeriksa keputusan admin.",
                    border_style="yellow",
                    padding=(1, 2),
                    expand=True,
                )
            )
            pilihan = questionary.select(
                "Tindakan:",
                choices=[
                    Choice("↻  Muat ulang status", value="refresh"),
                    Choice("🚪  Logout", value="logout"),
                ],
                style=GAYA_SIBIMA,
                qmark="⚡",
                pointer="▶",
                instruction=" (Gunakan ↑/↓ lalu Enter)",
            ).ask()
            if pilihan is None or pilihan == "logout":
                session.logout()
                sukses("Logout siswa berhasil. Sesi telah ditutup.")
                _jeda("Tekan Enter untuk kembali ke menu utama...")
                return False
            continue

        if aktif:
            # Kondisi tak normal: akun masih menunggu, tetapi ada enrollment aktif.
            # Jangan izinkan memilih paket lagi; minta admin memeriksa konsistensi data.
            _tabel_pendaftaran(aktif, judul="Pendaftaran Aktif yang Perlu Diperiksa")
            peringatan(
                "Akun masih berstatus menunggu, tetapi sudah memiliki pendaftaran aktif. "
                "Hubungi admin untuk memeriksa konsistensi data."
            )
            pilihan = questionary.select(
                "Tindakan:",
                choices=[
                    Choice("↻  Muat ulang status", value="refresh"),
                    Choice("🚪  Logout", value="logout"),
                ],
                style=GAYA_SIBIMA,
                qmark="⚡",
                pointer="▶",
            ).ask()
            if pilihan is None or pilihan == "logout":
                session.logout()
                sukses("Logout siswa berhasil. Sesi telah ditutup.")
                _jeda("Tekan Enter untuk kembali ke menu utama...")
                return False
            continue

        console.print(
            Panel(
                "Belum ada pendaftaran program. Kamu dapat memilih program setelah "
                "akun disetujui admin. NIS diterbitkan saat akun disetujui; "
                "pendaftaran program dan tagihan diproses secara terpisah.",
                title="MENUNGGU PERSETUJUAN AKUN",
                border_style="cyan",
                padding=(1, 3),
                expand=True,
            )
        )
        pilihan = questionary.select(
            "Langkah berikutnya:",
            choices=[
                Choice("↻  Periksa status persetujuan akun", value="refresh"),
                Choice("🚪  Logout", value="logout"),
            ],
            style=GAYA_SIBIMA,
            qmark="⚡",
            pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()

        if pilihan is None or pilihan == "logout":
            session.logout()
            sukses("Logout siswa berhasil. Sesi telah ditutup.")
            _jeda("Tekan Enter untuk kembali ke menu utama...")
            return False

        if pilihan == "refresh":
            continue

        # Akun belum aktif: hanya izinkan memeriksa status atau logout.


def jalankan():
    """Dashboard siswa; akun pending hanya dapat memeriksa status atau logout."""
    while True:
        pengguna = _pengguna_siswa()
        if pengguna is None:
            gagal("Sesi siswa tidak valid. Silakan login kembali.")
            session.logout()
            _jeda()
            return

        # Siswa boleh login sebelum approval hanya untuk memeriksa status akun.
        # Pendaftaran program baru tersedia setelah akun berstatus aktif.
        if pengguna.get("status") == "menunggu_konfirmasi":
            lanjut_dashboard = _jalankan_onboarding(pengguna)
            if not lanjut_dashboard:
                return
            continue

        if pengguna.get("status") != "aktif":
            gagal("Akun siswa belum aktif. Silakan periksa status pendaftaran.")
            session.logout()
            _jeda()
            return

        try:
            enrollments = _ambil_pendaftaran(pengguna["id"])
        except psycopg.Error as exc:
            bersihkan_layar()
            gagal(f"Gagal memuat data kelas ({type(exc).__name__}).")
            _jeda()
            return

        _dashboard(pengguna, enrollments)
        pilihan = questionary.select(
            "Apa yang ingin kamu lakukan?",
            choices=[
                Choice("🎓  Katalog Program — cari dan daftar kelas", value="katalog"),
                Choice("📚  Kelas Saya — status dan riwayat", value="pendaftaran"),
                Choice("🗓️  Jadwal Saya", value="jadwal"),
                Choice("📝  Absensi", value="absensi"),
                Choice("📊  Nilai dan Rapor", value="nilai"),
                Choice("💳  Tagihan dan Pembayaran", value="pembayaran"),
                Choice("📖  Catatan Materi", value="materi"),
                Choice("🔔  Notifikasi", value="notifikasi"),
                Choice("🤖  Tanya AI (opsional)", value="ai"),
                Choice("👤  Profil Saya", value="profil"),
                Separator("────────────────────────"),
                Choice("🚪  Logout", value="logout"),
            ],
            style=GAYA_SIBIMA,
            qmark="⚡",
            pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()

        if pilihan is None or pilihan == "logout":
            session.logout()
            sukses("Logout siswa berhasil. Sesi telah ditutup.")
            _jeda("Tekan Enter untuk kembali ke menu utama...")
            return

        if pilihan == "katalog":
            menu_katalog(pengguna)
        elif pilihan == "pendaftaran":
            menu_siswa_academic.menu_kelas_saya()
        elif pilihan == "jadwal":
            menu_siswa_academic.menu_jadwal_saya()
        elif pilihan == "absensi":
            menu_siswa_academic.menu_absensi_siswa()
        elif pilihan == "nilai":
            menu_siswa_academic.menu_nilai_rapor()
        elif pilihan == "pembayaran":
            menu_pembayaran.menu_pembayaran_siswa()
        elif pilihan == "materi":
            menu_siswa_academic.menu_catatan_materi()
        elif pilihan == "notifikasi":
            menu_notifikasi.jalankan("siswa")
        elif pilihan == "ai":
            menu_siswa_academic.menu_tanya_ai_info()
        elif pilihan == "profil":
            menu_siswa_academic.menu_profil_siswa()
