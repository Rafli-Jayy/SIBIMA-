"""Logika bisnis autentikasi SIBIMA."""

from datetime import datetime, timezone

from app.config import MAX_LOGIN_ATTEMPTS, LOCK_MINUTES
from app.repositories import user_repo
from app.utils import security, validators
from app.utils.exceptions import DataTidakValid
from app.services import otp_service


ROLE_REGISTRASI = {"siswa", "tutor"}


def register(role: str, data: dict):
    """Membuat akun siswa/tutor dan memulai verifikasi OTP."""
    if role not in ROLE_REGISTRASI:
        return False, "Pendaftaran hanya tersedia untuk siswa dan tutor."

    try:
        username = validators.validasi_username(data.get("username", ""))
        email = validators.validasi_email(data.get("email", ""))
        password = validators.validasi_password(data.get("password", ""))

        nama_lengkap = data.get("nama_lengkap", "")
        if not isinstance(nama_lengkap, str):
            raise DataTidakValid("Nama lengkap harus berupa teks.")

        nama_lengkap = nama_lengkap.strip()
        if not nama_lengkap:
            raise DataTidakValid("Nama lengkap wajib diisi.")
        if len(nama_lengkap) > 100:
            raise DataTidakValid("Nama lengkap maksimal 100 karakter.")
        if len(email) > 120:
            raise DataTidakValid("Email maksimal 120 karakter.")

        password_hash = security.hash_password(password)
    except (DataTidakValid, ValueError) as exc:
        return False, str(exc)

    user_id = user_repo.buat_user(
        username=username,
        email=email,
        nama_lengkap=nama_lengkap,
        password_hash=password_hash,
        role=role,
    )
    if user_id is None:
        return False, "Username atau email sudah terdaftar."

    try:
        otp_berhasil, pesan_otp = otp_service.kirim_otp(user_id, "register")
    except Exception as exc:
        otp_berhasil = False
        pesan_otp = f"OTP belum dapat diproses. Jenis error: {type(exc).__name__}."

    if otp_berhasil:
        return True, f"Akun berhasil dibuat. {pesan_otp}"

    return True, (
        "Akun berhasil dibuat, tetapi OTP belum berhasil dikirim. "
        f"{pesan_otp} Pilih menu kirim ulang OTP untuk mencoba lagi."
    )


def kirim_ulang_otp_registrasi(username: str):
    """Mengirim ulang OTP untuk akun yang belum diverifikasi."""
    try:
        username = validators.validasi_username(username)
    except DataTidakValid as exc:
        return False, str(exc)

    user = user_repo.cari_by_username(username)
    if user is None:
        return False, "Akun tidak ditemukan."
    if user["email_verified"]:
        return False, "Email akun ini sudah terverifikasi."
    if user["status"] in {"ditolak", "nonaktif"}:
        return False, "Akun ini tidak dapat melanjutkan verifikasi."

    return otp_service.kirim_otp(user["id"], "register")


def verifikasi_otp_registrasi(username: str, kode: str):
    """Memverifikasi OTP registrasi berdasarkan username."""
    try:
        username = validators.validasi_username(username)
    except DataTidakValid as exc:
        return False, str(exc)

    user = user_repo.cari_by_username(username)
    if user is None:
        return False, "Akun tidak ditemukan."
    if user["email_verified"]:
        return False, "Email akun ini sudah terverifikasi."
    if user["status"] in {"ditolak", "nonaktif"}:
        return False, "Akun ini tidak dapat melanjutkan verifikasi."

    return otp_service.verifikasi_otp(user["id"], kode, "register")


def _waktu_sisa_kunci(locked_until) -> str:
    """Membuat label waktu penguncian yang aman untuk ditampilkan."""
    waktu = locked_until
    if waktu.tzinfo is None:
        waktu = waktu.replace(tzinfo=timezone.utc)
    return waktu.strftime("%H:%M:%S %Z") or waktu.isoformat()


def login(username: str, password: str):
    """Login dan batasi akses akun siswa yang belum disetujui.

    Siswa yang emailnya sudah diverifikasi tetapi akun masih menunggu admin
    boleh login hanya agar bisa memilih paket. menu_siswa.jalankan() membatasi
    akun tersebut ke alur onboarding sampai admin menyetujui akun + program.
    Tutor yang menunggu persetujuan tetap tidak dapat login.
    """
    try:
        username = validators.validasi_username(username)
    except DataTidakValid as exc:
        return False, str(exc)

    if not isinstance(password, str) or not password:
        return False, "Username dan password wajib diisi."

    user = user_repo.cari_by_username(username)
    if user is None:
        return False, "Username atau password salah."

    # Periksa lockout dan password sebelum memberikan pesan status akun.
    locked_until = user.get("locked_until")
    sekarang = datetime.now(timezone.utc)
    if locked_until is not None:
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > sekarang:
            return False, (
                "Akun dikunci sementara karena terlalu banyak percobaan "
                f"login gagal. Coba lagi setelah {_waktu_sisa_kunci(locked_until)}."
            )
        user_repo.reset_lock_kedaluwarsa(user["id"])
        user = user_repo.cari_by_id(user["id"])
        if user is None:
            return False, "Data pengguna tidak dapat dimuat kembali."

    if not security.verifikasi_password(password, user["password_hash"]):
        hasil = user_repo.catat_gagal_login(
            user["id"],
            max_attempts=MAX_LOGIN_ATTEMPTS,
            lock_minutes=LOCK_MINUTES,
        )
        if hasil is None:
            return False, "Gagal memperbarui status percobaan login."

        locked = hasil.get("locked_until")
        if locked is not None:
            if locked.tzinfo is None:
                locked = locked.replace(tzinfo=timezone.utc)
            if locked > datetime.now(timezone.utc):
                return False, (
                    "Terlalu banyak percobaan login gagal. "
                    f"Akun dikunci selama {LOCK_MINUTES} menit."
                )

        sisa = max(0, MAX_LOGIN_ATTEMPTS - hasil["failed_attempts"])
        return False, (
            "Username atau password salah. "
            f"Sisa percobaan sebelum penguncian: {sisa}."
        )

    # Password benar. Status diperiksa sesudah kredensial supaya akun yang
    # menunggu tidak bisa memakai login tanpa password yang benar.
    if not user.get("email_verified") or user.get("status") == "belum_verifikasi":
        return False, "Email belum diverifikasi. Selesaikan verifikasi terlebih dahulu."
    if user.get("status") == "ditolak":
        alasan = user.get("reject_reason") or "-"
        return False, f"Pendaftaran ditolak. Alasan: {alasan}"
    if user.get("status") == "nonaktif":
        return False, "Akun Anda telah dinonaktifkan."

    if user.get("status") == "menunggu_konfirmasi":
        if user.get("role") == "siswa":
            # Login terbatas; menu siswa wajib memaksa pemilihan paket.
            user_repo.reset_gagal_login(user["id"])
            terbaru = user_repo.cari_by_id(user["id"])
            if terbaru is None:
                return False, "Data pengguna tidak dapat dimuat kembali."
            return True, terbaru
        return False, "Email terverifikasi. Akun tutor masih menunggu persetujuan admin."

    if user.get("status") != "aktif":
        return False, "Akun belum dapat digunakan. Hubungi administrator."

    user_repo.reset_gagal_login(user["id"])
    terbaru = user_repo.cari_by_id(user["id"])
    if terbaru is None:
        return False, "Data pengguna tidak dapat dimuat kembali."

    return True, terbaru


def ganti_password(
    user_id: int,
    password_lama: str,
    password_baru: str,
):
    """Mengganti password setelah password lama diverifikasi."""
    user = user_repo.cari_by_id(user_id)
    if user is None:
        return False, "Pengguna tidak ditemukan."
    if not security.verifikasi_password(password_lama, user["password_hash"]):
        return False, "Password lama tidak sesuai."

    try:
        password_baru = validators.validasi_password(password_baru)
        hash_baru = security.hash_password(password_baru)
    except (DataTidakValid, ValueError) as exc:
        return False, str(exc)

    user_repo.set_password(user_id, hash_baru)
    return True, "Password berhasil diperbarui."


def minta_otp_reset_password(email: str):
    """Kirim OTP tanpa membocorkan apakah email tersebut terdaftar."""
    try:
        email = validators.validasi_email(email)
    except DataTidakValid as exc:
        return False, str(exc)

    pesan_umum = (
        "Jika email terdaftar dan memenuhi syarat, kode OTP akan dikirim. "
        "Periksa Inbox/Spam, lalu masukkan kode yang diterima."
    )
    user = user_repo.cari_by_email(email)
    if user is None or not user.get("email_verified") or user.get("status") in {
        "nonaktif", "ditolak", "belum_verifikasi",
    }:
        return True, pesan_umum

    # Hasil pengiriman, termasuk batas permintaan OTP, tidak dibocorkan
    # melalui status UI untuk mencegah enumerasi akun.
    try:
        otp_service.kirim_otp(user["id"], "reset_password")
    except Exception:
        # Error teknis tidak boleh mengungkap keberadaan email.
        pass
    return True, pesan_umum


def reset_password(email: str, kode: str, password_baru: str):
    """Reset aman: kode OTP diverifikasi dan dihabiskan dalam 1 transaksi.

    Tidak menerima user_id tanpa OTP. Fungsi lama sengaja digantikan
    karena dapat dipanggil tanpa bukti verifikasi.
    """
    from app.config import OTP_MAX_ATTEMPTS
    from app.repositories import otp_repo

    try:
        email = validators.validasi_email(email)
        password_baru = validators.validasi_password(password_baru)
    except DataTidakValid as exc:
        return False, str(exc)

    if (
        not isinstance(kode, str)
        or len(kode) != 6
        or not kode.isascii()
        or not kode.isdigit()
    ):
        return False, "Kode OTP harus terdiri dari 6 angka."

    user = user_repo.cari_by_email(email)
    if user is None or not user.get("email_verified") or user.get("status") in {
        "nonaktif", "ditolak", "belum_verifikasi",
    }:
        return False, "Kode OTP tidak valid atau tidak tersedia."

    if security.verifikasi_password(password_baru, user["password_hash"]):
        return False, "Password baru harus berbeda dari password sebelumnya."

    hash_baru = security.hash_password(password_baru)
    return otp_repo.reset_password_dengan_otp(
        user_id=user["id"],
        kode=kode,
        password_hash=hash_baru,
        batas_percobaan=OTP_MAX_ATTEMPTS,
    )
