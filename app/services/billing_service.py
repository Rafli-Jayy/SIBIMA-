"""Aturan bisnis tagihan dan pembayaran VA penuh SIBIMA."""

import psycopg

from app import session
from app.repositories import billing_repo, user_repo


def _pengguna_aktif(role: str) -> dict:
    current = session.get_user()
    if not current or current.get("role") != role:
        raise PermissionError(f"Akses ditolak. Fitur ini khusus {role}.")
    user_id = current.get("id")
    if type(user_id) is not int or user_id <= 0:
        raise PermissionError("Sesi pengguna tidak valid. Silakan login ulang.")
    pengguna = user_repo.cari_by_id(user_id)
    if not pengguna or pengguna.get("role") != role or pengguna.get("status") != "aktif":
        raise PermissionError(f"Akun {role} tidak aktif atau tidak ditemukan.")
    return pengguna


def buat_tagihan_bulanan() -> dict:
    admin = _pengguna_aktif("admin")
    invoices = billing_repo.buat_tagihan_bulanan(admin["id"])
    from app.services import invoice_email_service
    terkirim = 0
    gagal = 0
    for invoice in invoices:
        ok, _pesan = invoice_email_service.kirim_email_tagihan_bulanan(
            email=invoice.get("email_siswa"), nama=invoice.get("nama_siswa"),
            nama_program=invoice.get("nama_program"), invoice=invoice,
        )
        if ok:
            terkirim += 1
        else:
            gagal += 1
    return {"dibuat": len(invoices), "email_terkirim": terkirim, "email_gagal": gagal}


def daftar_tagihan_admin(status=None, tunggakan=False):
    _pengguna_aktif("admin")
    return billing_repo.daftar_tagihan_admin(status=status, tunggakan=tunggakan)


def daftar_tagihan_saya(status=None):
    siswa = _pengguna_aktif("siswa")
    return billing_repo.daftar_tagihan_siswa(siswa["id"], status=status)


def bayar_simulasi(invoice_id: int) -> dict:
    """Checkout simulasi otomatis untuk siswa; tidak memakai uang sungguhan."""
    siswa = _pengguna_aktif("siswa")
    hasil = billing_repo.proses_simulasi_pembayaran(siswa["id"], invoice_id)
    from app.services import billing_receipt_service
    try:
        if hasil.get("payment_status") == "lunas":
            delivery = kirim_bukti_pembayaran_email(hasil["payment_id"])
            email_ok, email_message = delivery["sent"], delivery["message"]
        else:
            email_ok, email_message = billing_receipt_service.kirim_email_simulasi_gagal(hasil)
        hasil["email_sent"] = bool(email_ok)
        hasil["email_message"] = email_message
    except Exception as exc:
        hasil["email_sent"] = False
        hasil["email_message"] = f"Email notifikasi gagal ({type(exc).__name__})."
    return hasil


def riwayat_pembayaran_admin():
    _pengguna_aktif("admin")
    return billing_repo.daftar_riwayat_pembayaran()


def riwayat_pembayaran_saya():
    siswa = _pengguna_aktif("siswa")
    return billing_repo.daftar_riwayat_pembayaran(student_id=siswa["id"])


def bukti_pembayaran_admin(payment_id: int):
    _pengguna_aktif("admin")
    return billing_repo.ambil_bukti_pembayaran(payment_id)


def bukti_pembayaran_saya(payment_id: int):
    siswa = _pengguna_aktif("siswa")
    return billing_repo.ambil_bukti_pembayaran(payment_id, student_id=siswa["id"])


def _detail_bukti_untuk_sesi(payment_id: int) -> dict:
    """Retrieve a paid receipt, restricting students to their own payments."""
    current = session.get_user()
    if not current:
        raise PermissionError("Sesi pengguna tidak ditemukan. Silakan login ulang.")
    role = current.get("role")
    if role == "admin":
        _pengguna_aktif("admin")
        detail = billing_repo.ambil_bukti_pembayaran(payment_id)
    elif role == "siswa":
        siswa = _pengguna_aktif("siswa")
        detail = billing_repo.ambil_bukti_pembayaran(payment_id, student_id=siswa["id"])
    else:
        raise PermissionError("Fitur bukti pembayaran hanya untuk admin atau siswa.")
    if not detail:
        raise LookupError("Bukti tidak ditemukan, bukan milik akun ini, atau pembayaran belum LUNAS.")
    return detail


def buat_bukti_pembayaran_pdf(payment_id: int):
    """Create a PDF receipt for the currently authenticated admin/student."""
    from app.services import billing_receipt_service

    detail = _detail_bukti_untuk_sesi(payment_id)
    return billing_receipt_service.buat_pdf_bukti(detail)


def kirim_bukti_pembayaran_email(payment_id: int) -> dict:
    """Generate and email a paid receipt to the student's registered email."""
    from app.services import billing_receipt_service

    detail = _detail_bukti_untuk_sesi(payment_id)
    path = billing_receipt_service.buat_pdf_bukti(detail)
    terkirim, pesan = billing_receipt_service.kirim_pdf_via_email(detail, path)
    return {
        "path": path,
        "email": detail.get("email_siswa"),
        "sent": terkirim,
        "message": pesan,
    }
