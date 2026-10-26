
import questionary
from questionary import Style, Choice, Separator
from rich.console import Console
from rich.panel import Panel
from rich.align import Align

# Mengimpor modul layanan dan utilitas UI (Pastikan gagal dan sukses ada di console.py)
from app import session
from app.services import auth_service
from app.ui.console import info, peringatan, bersihkan_layar, sukses, gagal

console = Console()

tema_sibima = Style([
    ('qmark', 'fg:#00ffff bold'),
    ('question', 'fg:#ffffff bold'),
    ('answer', 'fg:#00ffff bold'),
    ('pointer', 'fg:#00ffff bold'),
    ('highlighted', 'fg:#00ffff bold'),
    ('selected', 'fg:#00ffff'),
    ('separator', 'fg:#444444'),
    ('instruction', 'fg:#888888 italic')
])

def tampilkan_header(halaman="Utama"):
    """Tampilkan header untuk semua halaman, termasuk halaman baru."""
    header = {
        "Utama": (
            "S I B I M A",
            "S I S T E M   I N F O R M A S I   B I M B E L",
        ),
        "Login": (
            "L O G I N",
            "O T E N T I K A S I   P E N G G U N A",
        ),
        "Register": (
            "R E G I S T E R",
            "P E N D A F T A R A N   A K U N",
        ),
        "Verifikasi OTP": (
            "S I B I M A   K E C E",
            "V E R I F I K A S I   E M A I L",
        ),
        "Ganti Password Sementara": (
            "G A N T I   P A S S W O R D",
            "P E R G A N T I A N   P A S S W O R D   W A J I B",
        ),
    }
    judul, sub = header.get(
        halaman,
        (str(halaman).upper(), "S I S T E M   I N F O R M A S I   B I M B E L"),
    )

    isi_teks = f"[bold cyan]{judul}[/bold cyan]\n[bold white]{sub}[/bold white]"
    
    panel = Panel(
        Align.center(isi_teks), 
        border_style="cyan",
        padding=(1, 6)
    )
    console.print(panel)
    print()


def menu_verifikasi_registrasi(username):
    """Halaman verifikasi OTP yang digambar ulang agar tidak menumpuk."""
    pesan_status = (
        "Masukkan kode dari email pendaftaran. "
        "Jika belum menerima kode, gunakan menu kirim ulang."
    )
    warna_status = "cyan"

    while True:
        # Satu halaman aktif pada satu waktu.
        bersihkan_layar()
        tampilkan_header("Verifikasi OTP")

        console.print(
            Panel(
                f"[bold white]Akun:[/] [cyan]{username}[/cyan]\n\n"
                "[white]Masukkan kode OTP yang dikirim ke email "
                "pendaftaran.[/white]\n\n"
                "[dim]Periksa Inbox dan Spam. Kode hanya berlaku "
                "selama waktu yang ditentukan dan tidak boleh "
                "dibagikan kepada siapa pun.[/dim]",
                title="[bold cyan]VERIFIKASI EMAIL[/bold cyan]",
                border_style="cyan",
                padding=(1, 3),
                expand=True,
            )
        )

        console.print(
            Panel(
                pesan_status,
                title="[bold]STATUS[/bold]",
                border_style=warna_status,
                padding=(0, 2),
                expand=True,
            )
        )

        pilihan = questionary.select(
            "Pilih tindakan:",
            choices=[
                Choice(
                    "🔐  Masukkan kode OTP",
                    value="verifikasi",
                ),
                Choice(
                    "📨  Kirim ulang OTP",
                    value="kirim_ulang",
                ),
                Separator("────────────────────────"),
                Choice(
                    "↩  Selesai / kembali",
                    value="selesai",
                ),
            ],
            style=tema_sibima,
            qmark="⚡",
            pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()

        if pilihan is None or pilihan == "selesai":
            return

        if pilihan == "kirim_ulang":
            berhasil, pesan = (
                auth_service.kirim_ulang_otp_registrasi(username)
            )

            pesan_status = pesan
            warna_status = "green" if berhasil else "red"
            continue

        kode = questionary.text(
            "Masukkan 6 digit OTP:",
            style=tema_sibima,
            qmark="🔐",
        ).ask()

        if kode is None:
            pesan_status = "Proses dibatalkan. Pilih tindakan berikutnya."
            warna_status = "yellow"
            continue

        kode = kode.strip()

        if not kode:
            pesan_status = "Kode OTP wajib diisi."
            warna_status = "red"
            continue

        berhasil, pesan = (
            auth_service.verifikasi_otp_registrasi(
                username,
                kode,
            )
        )

        pesan_status = pesan
        warna_status = "green" if berhasil else "red"

        if berhasil:
            # Tampilkan hasil akhir pada satu layar yang bersih.
            bersihkan_layar()
            tampilkan_header("Verifikasi OTP")

            console.print(
                Panel(
                    f"[bold green]✓ {pesan}[/bold green]\n\n"
                    "[white]Selanjutnya, tunggu persetujuan admin "
                    "untuk mengaktifkan akun.[/white]",
                    title="[bold green]VERIFIKASI BERHASIL[/bold green]",
                    border_style="green",
                    padding=(1, 3),
                    expand=True,
                )
            )

            input("\nTekan Enter untuk kembali...")
            return


def _proses_password_sementara(user, password_lama):
    """Memaksa pemilik akun mengganti password sementara sebelum masuk dashboard."""
    bersihkan_layar()
    tampilkan_header("Ganti Password Sementara")
    console.print(Panel(
        "Admin telah mereset password akun ini. Demi keamanan, buat password pribadi baru sebelum masuk dashboard.",
        title="PERGANTIAN PASSWORD WAJIB", border_style="yellow", padding=(1, 2),
    ))
    for percobaan in range(3):
        baru = questionary.password("Password baru (8-64 karakter, minimal satu huruf dan satu angka):", style=tema_sibima, qmark="🔐").ask()
        if baru is None:
            info("Login dibatalkan; password sementara masih berlaku.")
            return None
        konfirmasi = questionary.password("Ulangi password baru:", style=tema_sibima, qmark="🔁").ask()
        if konfirmasi is None:
            info("Login dibatalkan; password sementara masih berlaku.")
            return None
        if baru != konfirmasi:
            gagal("Konfirmasi password tidak sama. Coba kembali.")
            continue
        if baru == password_lama:
            gagal("Password baru harus berbeda dari password sementara.")
            continue
        berhasil, pesan = auth_service.ganti_password(user["id"], password_lama, baru)
        if not berhasil:
            gagal(pesan)
            continue
        from app.repositories import user_repo
        terbaru = user_repo.cari_by_id(user["id"])
        if not terbaru or terbaru.get("must_change_password"):
            gagal("Password belum dapat dikonfirmasi tersimpan. Silakan coba login kembali.")
            return None
        sukses("Password berhasil diganti.")
        return terbaru
    gagal("Batas percobaan pergantian password tercapai. Silakan login kembali.")
    return None


def menu_login():
    bersihkan_layar()
    tampilkan_header("Login")
    
    # Menangkap input. Menggunakan qmark kustom agar form terlihat konsisten
    username = questionary.text("Username:", style=tema_sibima, qmark="👤").ask()
    if not username: return  # Batal jika pengguna menekan Ctrl+C
    
    password = questionary.password("Password:", style=tema_sibima, qmark="🔑").ask()
    if not password: return

    info("Memverifikasi kredensial...")
    
    # Eksekusi logika bisnis
    berhasil, hasil = auth_service.login(username, password)
    
    if berhasil:
        if hasil.get("must_change_password"):
            hasil = _proses_password_sementara(hasil, password)
            if hasil is None:
                return

        session.set_user(hasil)

        nama = hasil["nama_lengkap"]
        status = hasil["status"]
        role = hasil["role"]

        sukses(
            f"Login berhasil! Selamat datang, {nama} "
            f"(Status: {status})."
        )

        if role == "admin":
            from app.ui import menu_admin
            menu_admin.jalankan()

        elif role == "siswa":
            from app.ui import menu_siswa
            menu_siswa.jalankan()

        elif role == "tutor":
            from app.ui import menu_tutor
            menu_tutor.jalankan()

        else:
            session.logout()
            gagal("Role akun tidak dikenali.")
    else:
        gagal(f"Login Gagal: {hasil}")



def menu_register():
    bersihkan_layar()
    tampilkan_header("Register")
    
    info("Silakan lengkapi data pendaftaran berikut.")
    print()
    
    role = questionary.select(
        "Mendaftar sebagai:",
        choices=[
            Choice("Siswa", value="siswa"),
            Choice("Tutor", value="tutor")
        ],
        style=tema_sibima,
        qmark="🎯",
        pointer="▶"
    ).ask()
    
    if not role: return

    username = questionary.text("Username (tanpa spasi, min 4 karakter):", style=tema_sibima, qmark="👤").ask()
    email = questionary.text("Email Aktif:", style=tema_sibima, qmark="📧").ask()
    nama_lengkap = questionary.text("Nama Lengkap:", style=tema_sibima, qmark="📝").ask()
    password = questionary.password("Password:", style=tema_sibima, qmark="🔑").ask()
    konfirmasi = questionary.password("Konfirmasi Password:", style=tema_sibima, qmark="🔑").ask()

    # Validasi awal sebelum membebani database
    if password != konfirmasi:
        gagal("Konfirmasi password tidak cocok dengan password utama.")
        return
        
    if not all([username, email, nama_lengkap, password]):
        gagal("Semua kolom wajib diisi.")
        return

    data_register = {
        "username": username.strip(),
        "email": email.strip(),
        "nama_lengkap": nama_lengkap.strip(),
        "password": password
    }

    info("Memproses pendaftaran ke database...")
    berhasil, pesan = auth_service.register(role, data_register)

    if berhasil:
        sukses(pesan)
        menu_verifikasi_registrasi(data_register["username"])
    else:
        gagal(f"Registrasi Gagal: {pesan}")

def jalankan():
    while True:
        bersihkan_layar()
        tampilkan_header("Utama")
        
        pilihan = questionary.select(
            "Tentukan rute akses Anda:",
            choices=[
                Choice(title=" 🔓  Masuk ke Akun (Login)", value="Login"),
                Choice(title=" 📝  Pendaftaran Baru (Register)", value="Register"),
                Choice(title=" 🔑  Lupa Kata Sandi", value="Lupa Password"),
                Separator(" ────────────────────────── "),
                Choice(title=" 🚪  Keluar dari Aplikasi", value="Keluar")
            ],
            style=tema_sibima,
            qmark="⚡",
            pointer="▶",
            instruction=" (Gunakan panah ↑/↓ lalu tekan Enter)"
        ).ask()
        
        if pilihan is None or pilihan == "Keluar":
            info("Sampai jumpa di SIBIMA!")
            break
            
        elif pilihan == "Login":
            menu_login()
        elif pilihan == "Register":
            menu_register()
        else:
            peringatan(f"Fitur '{pilihan}' sedang dalam pengembangan.")
        
        console.print("\n[dim]Tekan Enter untuk kembali...[/dim]")
        input()

if __name__ == "__main__":
    jalankan()