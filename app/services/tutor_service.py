"""Service profil dan akun tutor."""

import psycopg

from app import session
from app.repositories import tutor_repo, user_repo
from app.services import auth_service
from app.utils.academic_validation import teks_catatan


def _tutor_aktif():
    current = session.get_user()
    if not current or current.get("role") != "tutor":
        return None
    tutor_id = current.get("id")
    if type(tutor_id) is not int or tutor_id <= 0:
        return None
    try:
        user = user_repo.cari_by_id(tutor_id)
    except psycopg.Error:
        return None
    if not user or user.get("role") != "tutor" or user.get("status") != "aktif":
        return None
    return user


def profil():
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak. Hanya tutor aktif yang dapat melihat profil."
    try:
        result = tutor_repo.profil(user["id"])
        if result is None:
            return False, "Profil tutor tidak ditemukan."
        return True, result
    except psycopg.Error as exc:
        return False, f"Profil tutor gagal diambil ({type(exc).__name__})."


def ubah_profil(keahlian, no_hp):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    try:
        keahlian = teks_catatan(keahlian, "Keahlian", 150)
        no_hp = teks_catatan(no_hp, "Nomor HP", 20)
        if no_hp and not no_hp.replace("+", "", 1).replace(" ", "").replace("-", "").isdigit():
            raise ValueError("Nomor HP hanya boleh berisi angka, spasi, tanda +, atau tanda hubung.")
        if not tutor_repo.ubah_profil(user["id"], keahlian=keahlian, no_hp=no_hp):
            return False, "Profil tidak ditemukan atau akun tutor tidak aktif."
        return True, "Profil tutor berhasil diperbarui."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Profil tutor gagal diperbarui ({type(exc).__name__})."


def ganti_password(password_lama, password_baru, konfirmasi):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    if not isinstance(password_baru, str) or password_baru != konfirmasi:
        return False, "Password baru dan konfirmasi tidak sama."
    try:
        berhasil, pesan = auth_service.ganti_password(
            user["id"], password_lama, password_baru
        )
    except psycopg.Error as exc:
        return False, f"Password gagal diperbarui ({type(exc).__name__})."
    if not berhasil:
        return False, pesan
    try:
        tutor_repo.catat_aktivitas(user["id"], "PASSWORD_TUTOR_DIUBAH", "password diganti dari menu profil")
    except psycopg.Error:
        # Password sudah berubah. Jangan klaim gagal karena audit log saja yang gagal.
        return True, "Password berhasil diganti, tetapi pencatatan log aktivitas gagal."
    return True, pesan
