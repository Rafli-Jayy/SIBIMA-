"""Validasi dan otorisasi untuk submenu admin: akun, siswa, dan tutor."""

import secrets

import psycopg

from app import session
from app.repositories import admin_management_repo, user_repo
from app.utils import security, validators
from app.utils.exceptions import DataTidakValid


_STATUS_AKUN = {
    "belum_verifikasi",
    "menunggu_konfirmasi",
    "aktif",
    "ditolak",
    "nonaktif",
}
_ROLE_AKUN = {"admin", "tutor", "siswa"}


def _admin_aktif():
    pengguna = session.get_user() or {}
    if pengguna.get("role") != "admin" or type(pengguna.get("id")) is not int:
        return None
    try:
        admin = user_repo.cari_by_id(pengguna["id"])
    except psycopg.Error:
        return None
    if not admin or admin.get("role") != "admin" or admin.get("status") != "aktif":
        return None
    return admin


def _teks(nilai, label, batas, wajib=True):
    if nilai is None:
        nilai = ""
    if not isinstance(nilai, str):
        raise ValueError(f"{label} harus berupa teks.")
    nilai = nilai.strip()
    if wajib and not nilai:
        raise ValueError(f"{label} wajib diisi.")
    if len(nilai) > batas:
        raise ValueError(f"{label} maksimal {batas} karakter.")
    return nilai or None


def daftar_akun(role=None, status=None):
    if _admin_aktif() is None:
        raise PermissionError("Hanya admin aktif yang dapat melihat daftar akun.")
    if role is not None and role not in _ROLE_AKUN:
        raise ValueError("Filter role tidak valid.")
    if status is not None and status not in _STATUS_AKUN:
        raise ValueError("Filter status tidak valid.")
    return admin_management_repo.daftar_akun_admin(role, status)


def ubah_status_akun(user_id: int, status_baru: str):
    admin = _admin_aktif()
    if admin is None:
        return False, "Hanya admin aktif yang dapat mengubah status akun."
    if type(user_id) is not int or user_id <= 0:
        return False, "ID akun tidak valid."
    if status_baru not in {"aktif", "nonaktif"}:
        return False, "Status tujuan tidak valid."
    if user_id == admin["id"]:
        return False, "Admin tidak dapat mengubah status akunnya sendiri dari menu ini."
    try:
        user = user_repo.cari_by_id(user_id)
        if not user:
            return False, "Akun tidak ditemukan."
        if user.get("role") == "admin":
            return False, "Perubahan status akun admin dibatasi demi mencegah seluruh admin terkunci."
        if user.get("status") not in {"aktif", "nonaktif"}:
            return False, "Status hanya dapat diubah untuk akun aktif/nonaktif; akun menunggu harus lewat Pusat Konfirmasi."
        if user["status"] == status_baru:
            return False, f"Akun sudah berstatus {status_baru}."
        if not admin_management_repo.ubah_status_akun_admin(user_id, status_baru, admin["id"]):
            return False, "Status akun tidak berubah. Muat ulang data dan coba lagi."
        return True, f"Akun {user['username']} berhasil diubah menjadi {status_baru}. Enrollment dan riwayatnya tidak dihapus."
    except psycopg.Error as exc:
        return False, f"Status akun gagal diperbarui ({type(exc).__name__})."


def buka_kunci_akun(user_id: int):
    admin = _admin_aktif()
    if admin is None:
        return False, "Hanya admin aktif yang dapat membuka kunci akun."
    if type(user_id) is not int or user_id <= 0:
        return False, "ID akun tidak valid."
    try:
        if not user_repo.cari_by_id(user_id):
            return False, "Akun tidak ditemukan."
        if not admin_management_repo.buka_kunci_akun_admin(user_id, admin["id"]):
            return False, "Akun tidak sedang terkunci dan tidak memiliki percobaan gagal yang perlu direset."
        return True, "Kunci login berhasil dibuka dan penghitung percobaan gagal direset."
    except psycopg.Error as exc:
        return False, f"Kunci akun gagal dibuka ({type(exc).__name__})."


def reset_password_akun(user_id: int):
    """Reset password ke nilai sementara acak; wajib diganti saat login selanjutnya."""
    admin = _admin_aktif()
    if admin is None:
        return False, "Hanya admin aktif yang dapat mereset password.", None
    if type(user_id) is not int or user_id <= 0:
        return False, "ID akun tidak valid.", None
    if user_id == admin["id"]:
        return False, "Gunakan alur lupa/ganti password untuk akun sendiri.", None
    try:
        user = user_repo.cari_by_id(user_id)
        if not user:
            return False, "Akun tidak ditemukan.", None
        # Prefix menjamin huruf, token hex memberi entropi, digit terakhir menjamin syarat password.
        password_sementara = f"Sibima-{secrets.token_hex(5)}{secrets.choice('0123456789')}"
        password_hash = security.hash_password(password_sementara)
        if not admin_management_repo.reset_password_akun_admin(user_id, password_hash, admin["id"]):
            return False, "Password gagal diperbarui.", None
        return True, (
            "Password sementara berhasil dibuat. Berikan secara aman kepada pemilik akun; "
            "pengguna wajib menggantinya ketika login berikutnya."
        ), password_sementara
    except psycopg.Error as exc:
        return False, f"Password gagal direset ({type(exc).__name__}).", None


def daftar_siswa(jenjang=None, program_id=None, status=None, cari=None):
    if _admin_aktif() is None:
        raise PermissionError("Hanya admin aktif yang dapat melihat data siswa.")
    if program_id is not None and (type(program_id) is not int or program_id <= 0):
        raise ValueError("ID program tidak valid.")
    if status is not None and status not in _STATUS_AKUN:
        raise ValueError("Filter status tidak valid.")
    if jenjang is not None:
        jenjang = _teks(jenjang, "Jenjang", 20, wajib=False)
    if cari is not None:
        cari = _teks(cari, "Kata pencarian", 120, wajib=False)
    return admin_management_repo.daftar_siswa_admin(jenjang, program_id, status, cari)


def detail_siswa(user_id: int):
    if _admin_aktif() is None:
        raise PermissionError("Hanya admin aktif yang dapat melihat detail siswa.")
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("ID siswa tidak valid.")
    return admin_management_repo.detail_siswa_admin(user_id)


def ubah_siswa(user_id: int, data: dict):
    admin = _admin_aktif()
    if admin is None:
        return False, "Hanya admin aktif yang dapat mengubah data siswa."
    if type(user_id) is not int or user_id <= 0:
        return False, "ID siswa tidak valid."
    if not isinstance(data, dict) or not data:
        return False, "Tidak ada data siswa yang dipilih untuk diubah."
    try:
        perubahan = {}
        allowed = {"nama_lengkap", "jenjang", "sekolah", "no_hp", "nama_wali"}
        if set(data) - allowed:
            raise ValueError("Ada kolom profil siswa yang tidak diizinkan.")
        if "nama_lengkap" in data:
            perubahan["nama_lengkap"] = _teks(data["nama_lengkap"], "Nama lengkap", 100)
        for key, label, batas in [
            ("jenjang", "Jenjang", 20),
            ("sekolah", "Sekolah", 100),
            ("nama_wali", "Nama wali", 100),
        ]:
            if key in data:
                perubahan[key] = _teks(data[key], label, batas, wajib=False)
        if "no_hp" in data:
            no_hp = _teks(data["no_hp"], "Nomor HP", 20, wajib=False)
            if no_hp:
                no_hp = validators.validasi_no_hp(no_hp)
            perubahan["no_hp"] = no_hp
        if not admin_management_repo.ubah_siswa_admin(user_id, perubahan, admin["id"]):
            return False, "Siswa tidak ditemukan."
        return True, "Data siswa berhasil diperbarui."
    except (ValueError, DataTidakValid) as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Data siswa gagal diperbarui ({type(exc).__name__})."


def daftar_tutor(cari=None):
    if _admin_aktif() is None:
        raise PermissionError("Hanya admin aktif yang dapat melihat data tutor.")
    if cari is not None:
        cari = _teks(cari, "Kata pencarian", 120, wajib=False)
    return admin_management_repo.daftar_tutor_admin(cari)


def detail_tutor(user_id: int):
    if _admin_aktif() is None:
        raise PermissionError("Hanya admin aktif yang dapat melihat detail tutor.")
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("ID tutor tidak valid.")
    return admin_management_repo.detail_tutor_admin(user_id)


def jadwal_tutor(user_id: int):
    if _admin_aktif() is None:
        raise PermissionError("Hanya admin aktif yang dapat melihat jadwal tutor.")
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("ID tutor tidak valid.")
    return admin_management_repo.jadwal_tutor_admin(user_id)


def ubah_tutor(user_id: int, data: dict):
    admin = _admin_aktif()
    if admin is None:
        return False, "Hanya admin aktif yang dapat mengubah data tutor."
    if type(user_id) is not int or user_id <= 0:
        return False, "ID tutor tidak valid."
    if not isinstance(data, dict) or not data:
        return False, "Tidak ada data tutor yang dipilih untuk diubah."
    try:
        perubahan = {}
        allowed = {"nama_lengkap", "keahlian", "no_hp"}
        if set(data) - allowed:
            raise ValueError("Ada kolom profil tutor yang tidak diizinkan.")
        if "nama_lengkap" in data:
            perubahan["nama_lengkap"] = _teks(data["nama_lengkap"], "Nama lengkap", 100)
        if "keahlian" in data:
            perubahan["keahlian"] = _teks(data["keahlian"], "Keahlian", 150, wajib=False)
        if "no_hp" in data:
            no_hp = _teks(data["no_hp"], "Nomor HP", 20, wajib=False)
            if no_hp:
                no_hp = validators.validasi_no_hp(no_hp)
            perubahan["no_hp"] = no_hp
        if not admin_management_repo.ubah_tutor_admin(user_id, perubahan, admin["id"]):
            return False, "Tutor tidak ditemukan."
        return True, "Data tutor berhasil diperbarui."
    except (ValueError, DataTidakValid) as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Data tutor gagal diperbarui ({type(exc).__name__})."
