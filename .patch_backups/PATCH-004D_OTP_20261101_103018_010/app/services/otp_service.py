"""Pembuatan, pengiriman, dan verifikasi OTP.

Fungsi yang direncanakan:
    - kirim_otp(user_id, tujuan)
    - verifikasi_otp(user_id, kode, tujuan)
"""


"""Service untuk pembuatan, pengiriman, dan verifikasi OTP SIBIMA."""

from datetime import datetime, timedelta, timezone

from app.config import (
    OTP_EXPIRE_MINUTES,
    OTP_MAX_ATTEMPTS,
    OTP_MODE,
)
from app.repositories import otp_repo, user_repo
from app.services import email_service
from app.utils import security


TUJUAN_OTP_VALID = {"register", "reset_password", "login"}

BATAS_KIRIM_OTP = 3
JENDELA_KIRIM_DETIK = 60


def kirim_otp(user_id: int, tujuan: str):
    """Membuat OTP, menyimpan hash, dan mengirimkan kode."""
    if tujuan not in TUJUAN_OTP_VALID:
        return False, "Tujuan OTP tidak valid."

    if OTP_EXPIRE_MINUTES < 1 or OTP_MAX_ATTEMPTS < 1:
        return False, "Konfigurasi OTP tidak valid."

    user = user_repo.cari_by_id(user_id)

    if user is None:
        return False, "Pengguna tidak ditemukan."

    if tujuan == "register" and user["email_verified"]:
        return False, "Email sudah terverifikasi."

    if tujuan == "reset_password" and not user["email_verified"]:
        return False, "Email harus diverifikasi terlebih dahulu."

    email = user.get("email")
    if not email:
        return False, "Alamat email pengguna belum tersedia."

    # Batasi jumlah penerbitan OTP.
    jumlah_kirim = otp_repo.hitung_kirim_terakhir(
        user_id,
        tujuan,
        JENDELA_KIRIM_DETIK,
    )

    if jumlah_kirim >= BATAS_KIRIM_OTP:
        return False, (
            "Batas pengiriman OTP tercapai. "
            "Tunggu sebelum meminta kode baru."
        )

    # Buat OTP asli dan hash untuk database.
    kode = security.buat_otp()
    kode_hash = security.hash_otp(kode)

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=OTP_EXPIRE_MINUTES
    )

    otp_id = otp_repo.simpan_otp(
        user_id=user_id,
        code_hash=kode_hash,
        tujuan=tujuan,
        expires_at=expires_at,
    )

    # Kirim melalui mode yang dipilih di konfigurasi.
    if OTP_MODE == "simulasi":
        email_service.tampilkan_otp_simulasi(kode)

    elif OTP_MODE == "email":
        berhasil = email_service.kirim_otp_email(email, kode)

        if not berhasil:
            otp_repo.tandai_terpakai(otp_id)
            return False, "Pengiriman OTP gagal. Periksa konfigurasi email."

    else:
        otp_repo.tandai_terpakai(otp_id)
        return False, "OTP_MODE harus 'simulasi' atau 'email'."

    return True, (
        f"OTP berhasil dikirim. Masa berlaku: "
        f"{OTP_EXPIRE_MINUTES} menit."
    )


def verifikasi_otp(user_id: int, kode: str, tujuan: str):
    """Verifikasi OTP dan jalankan tindakan sesuai tujuannya."""
    if tujuan not in TUJUAN_OTP_VALID:
        return False, "Tujuan OTP tidak valid."

    if not isinstance(kode, str) or not kode.isdigit():
        return False, "Kode OTP harus berupa angka."

    user = user_repo.cari_by_id(user_id)

    if user is None:
        return False, "Pengguna tidak ditemukan."

    otp = otp_repo.ambil_otp_aktif(user_id, tujuan)

    if otp is None:
        return False, "OTP tidak ditemukan atau sudah digunakan."

    sekarang = datetime.now(timezone.utc)
    expires_at = otp["expires_at"]

    # Antisipasi timestamp tanpa informasi zona waktu.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= sekarang:
        otp_repo.tandai_terpakai(otp["id"])
        return False, "OTP kedaluwarsa. Silakan minta kode baru."

    if otp["attempts"] >= OTP_MAX_ATTEMPTS:
        otp_repo.tandai_terpakai(otp["id"])
        return False, "Batas percobaan tercapai. Minta OTP baru."

    # Bandingkan OTP masukan dengan hash di database.
    if not security.verifikasi_otp(kode, otp["code_hash"]):
        hasil = otp_repo.tambah_percobaan(
            otp["id"],
            OTP_MAX_ATTEMPTS,
        )

        if hasil is None:
            return False, "OTP sudah digunakan atau tidak aktif."

        sisa = max(0, OTP_MAX_ATTEMPTS - hasil["attempts"])

        if sisa == 0:
            return False, "Batas percobaan tercapai. Minta OTP baru."

        return False, f"OTP salah. Sisa percobaan: {sisa}."

    # Pastikan kode tidak digunakan lebih dari sekali.
    if not otp_repo.tandai_terpakai(otp["id"]):
        return False, "OTP sudah digunakan. Minta kode baru."

    if tujuan == "register":
        # Periksa kembali status terbaru agar tidak memproses
        # verifikasi yang sebenarnya sudah selesai.
        if user["email_verified"]:
            return False, "Email sudah terverifikasi."

        user_repo.set_terverifikasi(user_id)

        return True, (
            "Email berhasil diverifikasi. "
            "Akun menunggu persetujuan admin."
        )

    if tujuan == "reset_password":
        # Password belum diubah pada tahap ini.
        # Pemanggil harus melanjutkan proses reset password.
        return True, "OTP valid. Silakan lanjutkan reset password."

    if tujuan == "login":
        return True, "Verifikasi OTP berhasil."

    return False, "Tujuan OTP tidak dikenali."
