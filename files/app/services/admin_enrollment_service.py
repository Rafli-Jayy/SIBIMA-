"""Layanan admin untuk mengelola dan memindahkan pendaftaran siswa."""

import psycopg

from app import session
from app.repositories import enrollment_repo, user_repo


def _admin_aktif():
    pengguna = session.get_user()
    if not pengguna or pengguna.get("role") != "admin":
        return None
    user_id = pengguna.get("id")
    if type(user_id) is not int or user_id <= 0:
        return None
    try:
        admin = user_repo.cari_by_id(user_id)
    except psycopg.Error:
        return None
    if not admin or admin.get("role") != "admin" or admin.get("status") != "aktif":
        return None
    return admin


def daftar_pendaftaran(status: str | None = None, program_id: int | None = None):
    if _admin_aktif() is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat melihat pendaftaran."
    try:
        return True, enrollment_repo.daftar_admin(status=status, program_id=program_id)
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Gagal membaca pendaftaran ({type(exc).__name__})."


def detail_pendaftaran(enrollment_id: int):
    if _admin_aktif() is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat melihat pendaftaran."
    if type(enrollment_id) is not int or enrollment_id <= 0:
        return False, "ID pendaftaran tidak valid."
    try:
        hasil = enrollment_repo.detail_admin(enrollment_id)
        if hasil is None:
            return False, "Pendaftaran tidak ditemukan."
        return True, hasil
    except psycopg.Error as exc:
        return False, f"Gagal membaca detail pendaftaran ({type(exc).__name__})."


def pindahkan_pendaftaran(enrollment_id: int, program_tujuan_id: int):
    admin = _admin_aktif()
    if admin is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat memindahkan pendaftaran."
    try:
        hasil = enrollment_repo.pindahkan_admin(
            enrollment_id=enrollment_id,
            program_tujuan_id=program_tujuan_id,
            processed_by=admin["id"],
        )
    except ValueError as exc:
        return False, str(exc)
    except psycopg.errors.UniqueViolation:
        return False, (
            "Siswa sudah memiliki riwayat pada program tujuan. "
            "Tidak ada perubahan yang disimpan."
        )
    except psycopg.Error as exc:
        return False, f"Pemindahan gagal diproses database ({type(exc).__name__})."
    return bool(hasil.get("berhasil")), hasil.get("pesan", "Pemindahan tidak berhasil.")


def batalkan_pendaftaran(enrollment_id: int, alasan: str | None = None):
    admin = _admin_aktif()
    if admin is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat membatalkan pendaftaran."
    if alasan is not None and not isinstance(alasan, str):
        return False, "Alasan pembatalan tidak valid."
    if isinstance(alasan, str) and len(alasan.strip()) > 1000:
        return False, "Alasan pembatalan maksimal 1000 karakter."
    try:
        hasil = enrollment_repo.batalkan_admin(
            enrollment_id=enrollment_id,
            processed_by=admin["id"],
            alasan=alasan,
        )
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Pembatalan gagal diproses database ({type(exc).__name__})."
    return bool(hasil.get("berhasil")), hasil.get("pesan", "Pembatalan tidak berhasil.")
