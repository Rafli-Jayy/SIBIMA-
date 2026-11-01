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
    """Batalkan enrollment dan kirim bukti refund setelah transaksi DB commit."""
    admin = _admin_aktif()
    if admin is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat membatalkan pendaftaran."
    if alasan is not None and not isinstance(alasan, str):
        return False, "Alasan pembatalan tidak valid."
    if isinstance(alasan, str) and len(alasan.strip()) > 1000:
        return False, "Alasan pembatalan maksimal 1000 karakter."
    try:
        hasil = enrollment_repo.batalkan_admin(
            enrollment_id=enrollment_id, processed_by=admin["id"], alasan=alasan,
        )
    except ValueError as exc:
        return False, str(exc)
    except (psycopg.Error, RuntimeError) as exc:
        return False, f"Pembatalan gagal diproses database ({type(exc).__name__}): {exc}"
    if not hasil.get("berhasil"):
        return False, hasil.get("pesan", "Pembatalan tidak berhasil.")

    # Email/PDF adalah efek pasca-commit. Kegagalannya tidak mengubah hasil refund.
    pesan = hasil["pesan"]
    refunds = hasil.get("refunds") or []
    if not refunds:
        return True, pesan
    try:
        siswa = user_repo.cari_by_id(hasil["student_id"])
    except Exception as exc:
        return True, pesan + f" Data siswa untuk pengiriman bukti tidak dapat dibaca ({type(exc).__name__})."
    if not siswa or not siswa.get("email"):
        return True, pesan + " Email siswa tidak ditemukan; refund tetap tercatat."

    from app.services import billing_receipt_service
    gagal_kirim = 0
    for refund in refunds:
        detail = {
            **refund,
            "jenis_refund": "pembatalan",
            "nama_siswa": siswa.get("nama_lengkap"),
            "email_siswa": siswa.get("email"),
            "nama_program": hasil["nama_program"],
            "alasan": hasil["alasan"],
        }
        try:
            pdf = billing_receipt_service.buat_pdf_bukti_refund(detail)
            terkirim, _ = billing_receipt_service.kirim_pdf_refund_via_email(detail, pdf)
            if not terkirim:
                gagal_kirim += 1
        except Exception:
            gagal_kirim += 1
    if gagal_kirim:
        return True, (
            pesan + f" Refund sudah tercatat, tetapi {gagal_kirim} dari "
            f"{len(refunds)} email/PDF bukti belum berhasil dikirim."
        )
    return True, pesan + f" {len(refunds)} email dan PDF bukti refund dikirim."
