"""Register, login, ganti dan reset password.

Fungsi yang direncanakan:
    - register(role, data)
    - login(username, password)
    - ganti_password
    - reset_password
"""

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
    if role not in {"siswa", "tutor"}:
        return False, "Pendaftaran hanya tersedia untuk siswa dan tutor."

    try:
        username = validators.validasi_username(
            data.get("username", "")
        )
        email = validators.validasi_email(
            data.get("email", "")
        )
        password = validators.validasi_password(
            data.get("password", "")
        )

        nama_lengkap = data.get("nama_lengkap", "")

        if not isinstance(nama_lengkap, str):
            raise DataTidakValid("Nama lengkap harus berupa teks.")

        nama_lengkap = nama_lengkap.strip()

        if not nama_lengkap:
            raise DataTidakValid("Nama lengkap wajib diisi.")

        if len(nama_lengkap) > 100:
            raise DataTidakValid(
                "Nama lengkap maksimal 100 karakter."
            )

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

    # Akun sudah dibuat. Sekarang coba kirim OTP.
    try:
        otp_berhasil, pesan_otp = otp_service.kirim_otp(
            user_id,
            "register",
        )
    except Exception as exc:
        # Akun sudah tersimpan, jadi jangan menganggap
        # seluruh proses pendaftaran gagal.
        otp_berhasil = False
        pesan_otp = (
            "OTP belum dapat diproses. "
            f"Jenis error: {type(exc).__name__}."
        )

    if otp_berhasil:
        return True, (
            "Akun berhasil dibuat. "
            f"{pesan_otp}"
        )

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

    return otp_service.verifikasi_otp(
        user["id"],
        kode,
        "register",
    )

def login(username: str, password: str):
    """Memvalidasi login, status akun, dan batas percobaan login."""
    try:
        username = validators.validasi_username(username)
    except DataTidakValid as exc:
        return False, str(exc)

    if not isinstance(password, str) or not password:
        return False, "Username dan password wajib diisi."

    user = user_repo.cari_by_username(username)

    if user is None:
        return False, "Username atau password salah."

    # 1. Periksa status akun.
    if user["status"] == "nonaktif":
        return False, "Akun Anda telah dinonaktifkan."

    if user["status"] == "ditolak":
        alasan = user.get("reject_reason") or "-"
        return False, f"Pendaftaran ditolak. Alasan: {alasan}"

    if not user["email_verified"] or user["status"] == "belum_verifikasi":
        return False, "Email belum diverifikasi. Selesaikan verifikasi terlebih dahulu."

    if user["status"] == "menunggu_konfirmasi":
        return False, "Email terverifikasi. Akun masih menunggu persetujuan admin."

    if user["status"] != "aktif":
        return False, "Akun belum dapat digunakan. Hubungi administrator."

    # 2. Periksa apakah akun sedang dikunci.
    locked_until = user.get("locked_until")
    sekarang = datetime.now(timezone.utc)

    if locked_until is not None:
        if locked_until > sekarang:
            waktu = locked_until.strftime("%H:%M:%S UTC")
            return False, (
                "Akun dikunci sementara karena terlalu banyak "
                f"percobaan login gagal. Coba lagi setelah {waktu}."
            )

        # Masa penguncian sudah berakhir.
        user_repo.reset_lock_kedaluwarsa(user["id"])

    # 3. Periksa password.
    if not security.verifikasi_password(
        password,
        user["password_hash"],
    ):
        hasil = user_repo.catat_gagal_login(
            user["id"],
            max_attempts=MAX_LOGIN_ATTEMPTS,
            lock_minutes=LOCK_MINUTES,
        )

        if hasil is None:
            return False, "Gagal memperbarui status percobaan login."

        if hasil["locked_until"] is not None:
            if hasil["locked_until"] > datetime.now(timezone.utc):
                return False, (
                    "Terlalu banyak percobaan login gagal. "
                    f"Akun dikunci selama {LOCK_MINUTES} menit."
                )

        sisa = max(
            0,
            MAX_LOGIN_ATTEMPTS - hasil["failed_attempts"],
        )

        return False, (
            "Username atau password salah. "
            f"Sisa percobaan sebelum penguncian: {sisa}."
        )

    # 4. Reset kegagalan dan catat login berhasil.
    user_repo.reset_gagal_login(user["id"])

    # Ambil data terbaru dari database agar last_login dan
    # failed_attempts yang dikembalikan tidak kedaluwarsa.
    user = user_repo.cari_by_id(user["id"])

    if user is None:
        return False, "Data pengguna tidak dapat dimuat kembali."

    return True, user


def ganti_password(
    user_id: int,
    password_lama: str,
    password_baru: str,
):
    """Mengganti password setelah password lama diverifikasi."""
    user = user_repo.cari_by_id(user_id)

    if user is None:
        return False, "Pengguna tidak ditemukan."

    if not security.verifikasi_password(
        password_lama,
        user["password_hash"],
    ):
        return False, "Password lama tidak sesuai."

    try:
        password_baru = validators.validasi_password(password_baru)
        hash_baru = security.hash_password(password_baru)
    except (DataTidakValid, ValueError) as exc:
        return False, str(exc)

    user_repo.set_password(user_id, hash_baru)

    return True, "Password berhasil diperbarui."


def reset_password(user_id: int, password_baru: str):
    """
    Mengatur ulang password.

    Panggil fungsi ini hanya setelah proses OTP berhasil diverifikasi.
    Fungsi ini sendiri tidak memverifikasi OTP.
    """
    user = user_repo.cari_by_id(user_id)

    if user is None:
        return False, "Pengguna tidak ditemukan."

    try:
        password_baru = validators.validasi_password(password_baru)
        hash_baru = security.hash_password(password_baru)
    except (DataTidakValid, ValueError) as exc:
        return False, str(exc)

    user_repo.set_password(user_id, hash_baru)

    return True, "Password berhasil di-reset."