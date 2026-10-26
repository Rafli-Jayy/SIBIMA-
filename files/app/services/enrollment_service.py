"""Service pendaftaran program bimbel untuk siswa dengan akun aktif."""

import psycopg

from app import session
from app.repositories import enrollment_repo, user_repo


def daftar_program(student_id: int, program_id: int):
    """Daftarkan program untuk siswa yang sedang login.

    Pendaftaran program hanya boleh dilakukan setelah akun siswa disetujui
    admin dan berstatus aktif. Persetujuan akun menerbitkan NIS secara terpisah.
    """
    if type(student_id) is not int or student_id <= 0:
        return False, "ID siswa tidak valid."
    if type(program_id) is not int or program_id <= 0:
        return False, "Program yang dipilih tidak valid."

    pengguna = session.get_user()
    if pengguna is None:
        return False, "Silakan login terlebih dahulu."
    if pengguna.get("role") != "siswa":
        return False, "Fitur pendaftaran program hanya tersedia untuk siswa."

    session_student_id = pengguna.get("id")
    if type(session_student_id) is not int or session_student_id != student_id:
        return False, "Akses ditolak. Kamu hanya dapat mendaftarkan akun sendiri."

    try:
        user = user_repo.cari_by_id(session_student_id)
        if user is None or user.get("role") != "siswa":
            return False, "Data akun siswa tidak ditemukan."
        if not user.get("email_verified"):
            return False, "Verifikasi email terlebih dahulu."

        status_user = user.get("status")
        if status_user != "aktif":
            return False, (
                "Akun siswa harus disetujui admin terlebih dahulu. "
                "NIS diterbitkan saat persetujuan akun; setelah akun aktif, "
                "kamu dapat mendaftar program secara terpisah."
            )

        hasil = enrollment_repo.buat_enrollment(
            student_id=session_student_id,
            program_id=program_id,
        )

        if hasil["berhasil"]:
            return True, "Pendaftaran program berhasil dikirim. Status: menunggu persetujuan admin."

        alasan = hasil.get("alasan")
        pesan_gagal = {
            "siswa_tidak_ditemukan": "Profil siswa tidak ditemukan.",
            "program_tidak_ditemukan": "Program yang dipilih tidak ditemukan.",
            "program_tutup": "Program sudah ditutup dan tidak menerima pendaftaran.",
            "kuota_penuh": "Maaf, kuota program sudah penuh.",
        }

        if alasan == "sudah_terdaftar":
            status_lama = hasil.get("status")
            if status_lama == "menunggu":
                pesan = "Pendaftaran program ini masih menunggu keputusan admin."
            elif status_lama == "aktif":
                pesan = "Kamu sudah terdaftar aktif pada program ini."
            elif status_lama == "batal":
                pesan = "Pendaftaran sebelumnya dibatalkan; program yang sama belum dapat didaftarkan ulang."
            elif status_lama == "ditolak":
                pesan = "Pendaftaran sebelumnya ditolak; program yang sama belum dapat didaftarkan ulang."
            else:
                pesan = "Kamu sudah memiliki riwayat pendaftaran untuk program ini."
            return False, pesan

        return False, pesan_gagal.get(alasan, "Pendaftaran gagal diproses.")

    except psycopg.Error as exc:
        return False, (
            "Terjadi masalah saat mengakses database "
            f"({type(exc).__name__}). Pendaftaran belum dapat dipastikan berhasil."
        )


def batalkan(enrollment_id: int):
    """Batalkan pendaftaran milik siswa yang sedang login."""
    if type(enrollment_id) is not int or enrollment_id <= 0:
        return False, "ID pendaftaran tidak valid."

    pengguna = session.get_user()
    if pengguna is None:
        return False, "Silakan login terlebih dahulu."
    if pengguna.get("role") != "siswa":
        return False, "Fitur ini hanya tersedia untuk siswa."

    student_id = pengguna.get("id")
    if type(student_id) is not int or student_id <= 0:
        return False, "Identitas siswa pada sesi tidak valid."

    try:
        berhasil = enrollment_repo.batalkan_milik_siswa(
            enrollment_id=enrollment_id,
            student_id=student_id,
        )
    except psycopg.Error as exc:
        return False, (
            "Terjadi masalah saat mengakses database "
            f"({type(exc).__name__}). Pembatalan belum dapat dipastikan berhasil."
        )

    if not berhasil:
        return False, (
            "Pendaftaran tidak ditemukan, bukan milik akun kamu, "
            "atau sudah tidak menunggu persetujuan."
        )
    return True, "Pendaftaran berhasil dibatalkan."
