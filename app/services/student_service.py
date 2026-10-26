"""Service fitur siswa: otorisasi, validasi, dan akses data milik sendiri."""

import psycopg

from app import session
from app.repositories import student_repo, user_repo, log_repo
from app.services import auth_service
from app.utils.student_validation import validasi_profil
from app.utils.exceptions import DataTidakValid


HARI_VALID = {"senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu"}


def _siswa_aktif() -> dict:
    current = session.get_user() or {}
    if current.get("role") != "siswa" or type(current.get("id")) is not int:
        raise PermissionError("Akses ditolak. Silakan login sebagai siswa.")
    actual = user_repo.cari_by_id(current["id"])
    if not actual or actual.get("role") != "siswa" or actual.get("status") != "aktif":
        raise PermissionError("Akun siswa tidak aktif atau sesi sudah tidak berlaku.")
    return actual


def _read(label: str, function, *args, **kwargs):
    try:
        user = _siswa_aktif()
        return True, function(user["id"], *args, **kwargs)
    except (PermissionError, ValueError) as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"{label} gagal diambil ({type(exc).__name__})."


def kelas_saya():
    return _read("Daftar kelas", student_repo.daftar_kelas)


def program_akademik():
    return _read("Program akademik", student_repo.daftar_program_akademik)


def jadwal_saya(hari: str | None = None, program_id: int | None = None):
    if hari is not None and hari not in HARI_VALID:
        return False, "Nama hari tidak valid."
    if program_id is not None and (type(program_id) is not int or program_id <= 0):
        return False, "ID program tidak valid."
    return _read("Jadwal", student_repo.daftar_jadwal, hari, program_id)


def rekap_absensi(program_id: int | None = None):
    if program_id is not None and (type(program_id) is not int or program_id <= 0):
        return False, "ID program tidak valid."
    return _read("Rekap absensi", student_repo.rekap_absensi, program_id)


def riwayat_absensi(program_id: int | None = None):
    if program_id is not None and (type(program_id) is not int or program_id <= 0):
        return False, "ID program tidak valid."
    return _read("Riwayat absensi", student_repo.daftar_absensi, program_id)


def ringkasan_nilai(program_id: int | None = None):
    if program_id is not None and (type(program_id) is not int or program_id <= 0):
        return False, "ID program tidak valid."
    return _read("Ringkasan nilai", student_repo.ringkasan_nilai, program_id)


def detail_nilai(program_id: int):
    if type(program_id) is not int or program_id <= 0:
        return False, "ID program tidak valid."
    return _read("Detail nilai", student_repo.daftar_nilai, program_id)


def catatan_materi(program_id: int):
    if type(program_id) is not int or program_id <= 0:
        return False, "ID program tidak valid."
    return _read("Catatan materi", student_repo.daftar_catatan_materi, program_id)


def profil_saya():
    return _read("Profil siswa", student_repo.profil_siswa)


def ubah_profil(data: dict):
    try:
        user = _siswa_aktif()
        if not isinstance(data, dict):
            raise ValueError("Data profil tidak valid.")
        profil_bersih = validasi_profil(data)
        ok = student_repo.ubah_profil_siswa(user["id"], profil_bersih)
        if not ok:
            return False, "Profil siswa tidak ditemukan."
        return True, "Profil berhasil diperbarui."
    except (PermissionError, ValueError, DataTidakValid) as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Profil gagal diperbarui ({type(exc).__name__})."


def ganti_password(password_lama: str, password_baru: str):
    try:
        user = _siswa_aktif()
        ok, pesan = auth_service.ganti_password(user["id"], password_lama, password_baru)
        if ok:
            try:
                log_repo.catat(user["id"], "PASSWORD_SISWA_DIUBAH", "Siswa mengganti password dari menu profil.")
            except (psycopg.Error, ValueError):
                # Kegagalan pencatatan log tidak boleh menyamarkan keberhasilan perubahan password.
                pass
        return ok, pesan
    except PermissionError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Password gagal diperbarui ({type(exc).__name__})."
