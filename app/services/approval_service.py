"""Service persetujuan akun dan pendaftaran program SIBIMA."""

import psycopg

from app import session
from app.repositories import (
    user_repo,
    profile_repo,
    enrollment_repo,
    onboarding_repo,
)
from app.services import email_service, invoice_email_service


def _admin_aktif():
    """Pastikan pengguna yang sedang login adalah admin aktif."""
    pengguna = session.get_user()
    if pengguna is None or pengguna.get("role") != "admin":
        return None

    admin_id = pengguna.get("id")
    if type(admin_id) is not int:
        return None

    admin = user_repo.cari_by_id(admin_id)
    if (
        admin is None
        or admin.get("role") != "admin"
        or admin.get("status") != "aktif"
    ):
        return None
    return admin


def setujui_akun(user_id: int):
    """Setujui akun secara mandiri; NIS/kode tutor terbit pada tahap akun."""
    admin = _admin_aktif()
    if admin is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat menyetujui akun."
    if type(user_id) is not int or user_id <= 0:
        return False, "ID pengguna tidak valid."

    target = user_repo.cari_by_id(user_id)
    if target is None:
        return False, "Pengguna tidak ditemukan."
    if target.get("role") not in {"siswa", "tutor"}:
        return False, "Hanya akun siswa dan tutor yang dapat disetujui."
    if not target.get("email_verified"):
        return False, "Email pengguna belum diverifikasi."
    if target.get("status") != "menunggu_konfirmasi":
        return False, "Akun tidak sedang menunggu persetujuan."

    try:
        # Penerbitan identitas dan aktivasi akun berada di satu transaksi.
        # Untuk siswa, pendaftaran program tetap menunggu keputusan terpisah.
        hasil = profile_repo.proses_persetujuan_akun(
            user_id=target["id"],
            approved_by=admin["id"],
            status="aktif",
        )
        # Repository mengembalikan identitas dari transaksi yang sama, sehingga
        # tidak perlu query pasca-commit yang bisa gagal setelah approval sukses.
        identitas = hasil.get("identitas")
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, (
            "Terjadi kesalahan database saat menyetujui akun "
            f"({type(exc).__name__})."
        )

    if target["role"] == "siswa":
        detail = (
            f"NIS: {identitas or '-'}\n"
            "Akun siswa telah disetujui. Pendaftaran program dilakukan terpisah; "
            "invoice berbayar akan dibuat otomatis saat siswa mendaftar."
        )
        pesan = f"Akun siswa {target['username']} disetujui."
        if identitas:
            pesan += f" NIS {identitas} diterbitkan."
    else:
        detail = f"Kode tutor: {identitas}" if identitas else None
        pesan = f"Akun tutor {target['username']} berhasil disetujui."
        if identitas:
            pesan += f" Kode tutor: {identitas}."

    try:
        terkirim = email_service.kirim_notifikasi_status(
            email=target["email"],
            nama=target["nama_lengkap"],
            kategori="akun",
            status="aktif",
            detail=detail,
        )
    except Exception:
        terkirim = False

    if not terkirim:
        return True, pesan + " Email notifikasi gagal dikirim."
    return True, pesan + " Email pemberitahuan telah dikirim."


def tolak_akun(user_id: int, alasan: str):
    """Tolak akun; untuk siswa, tolak juga paket menunggunya dalam satu transaksi."""
    admin = _admin_aktif()
    if admin is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat menolak akun."
    if type(user_id) is not int or user_id <= 0:
        return False, "ID pengguna tidak valid."
    if not isinstance(alasan, str) or not alasan.strip():
        return False, "Alasan penolakan wajib diisi."

    target = user_repo.cari_by_id(user_id)
    if target is None:
        return False, "Pengguna tidak ditemukan."
    if target.get("role") not in {"siswa", "tutor"}:
        return False, "Hanya akun siswa dan tutor yang dapat ditolak."
    if not target.get("email_verified"):
        return False, "Email pengguna belum diverifikasi."
    if target.get("status") != "menunggu_konfirmasi":
        return False, "Akun tidak sedang menunggu persetujuan."

    alasan = alasan.strip()
    try:
        if target["role"] == "siswa":
            hasil = onboarding_repo.tolak_siswa_dan_paket(
                user_id=target["id"],
                approved_by=admin["id"],
                alasan=alasan,
            )
            terbaru = user_repo.cari_by_id(target["id"])
            if terbaru is None or terbaru.get("status") != "ditolak":
                return False, "Penolakan akun gagal diverifikasi di database."
            detail = alasan
            if hasil.get("enrollment_ids"):
                detail += "\nPendaftaran paket yang masih menunggu juga ditolak."
        else:
            profile_repo.proses_persetujuan_akun(
                user_id=target["id"],
                approved_by=admin["id"],
                status="ditolak",
                reject_reason=alasan,
            )
            terbaru = user_repo.cari_by_id(target["id"])
            if terbaru is None or terbaru.get("status") != "ditolak":
                return False, "Penolakan akun gagal diverifikasi di database."
            detail = alasan
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Terjadi kesalahan database saat menolak akun ({type(exc).__name__})."

    try:
        terkirim = email_service.kirim_notifikasi_status(
            email=terbaru["email"],
            nama=terbaru["nama_lengkap"],
            kategori="akun",
            status="ditolak",
            detail=detail,
        )
    except Exception:
        terkirim = False

    pesan = f"Akun {terbaru['username']} berhasil ditolak."
    if target["role"] == "siswa":
        pesan += " Pendaftaran paket yang masih menunggu juga ditolak."
    if not terkirim:
        return True, pesan + " Email notifikasi gagal dikirim."
    return True, pesan + " Email pemberitahuan telah dikirim."


def _enrollment_menunggu(enrollment_id: int):
    """Mencari enrollment menunggu untuk kebutuhan tampilan/detail."""
    if type(enrollment_id) is not int or enrollment_id <= 0:
        return None
    for item in enrollment_repo.daftar_menunggu():
        if item["enrollment_id"] == enrollment_id:
            return item
    return None


def _format_rupiah(nilai) -> str:
    """Format nominal numerik ke format rupiah sederhana."""
    return "Rp " + f"{nilai:,.0f}".replace(",", ".")


def setujui_enrollment(enrollment_id: int):
    """Setujui enrollment yang sudah lunas (atau program gratis)."""
    admin = _admin_aktif()
    if admin is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat menyetujui."
    if type(enrollment_id) is not int or enrollment_id <= 0:
        return False, "ID pendaftaran tidak valid."
    try:
        hasil = enrollment_repo.proses_keputusan_admin(
            enrollment_id=enrollment_id, processed_by=admin["id"], keputusan="disetujui",
        )
    except (ValueError, psycopg.Error, RuntimeError) as exc:
        return False, f"Persetujuan pendaftaran gagal ({type(exc).__name__}): {exc}"
    if not hasil.get("berhasil"):
        return False, hasil.get("pesan", "Pendaftaran tidak dapat disetujui.")
    siswa = user_repo.cari_by_id(hasil["student_id"])
    if not siswa:
        return True, f"Pendaftaran {hasil['nama_program']} aktif, tetapi data email siswa tidak ditemukan."
    detail = f"Program: {hasil['nama_program']}\nStatus: Aktif"
    try:
        terkirim = email_service.kirim_notifikasi_status(
            email=siswa["email"], nama=siswa["nama_lengkap"], kategori="pendaftaran",
            status="aktif", detail=detail,
        )
    except Exception:
        terkirim = False
    pesan = f"Pendaftaran {hasil['nama_program']} diterima dan siswa sekarang aktif."
    return True, pesan + (" Email konfirmasi dikirim." if terkirim else " Email konfirmasi gagal dikirim; status tetap aktif.")


def tolak_enrollment(enrollment_id: int, alasan: str):
    """Tolak pendaftaran; refund simulasi otomatis jika pembayaran sudah lunas."""
    admin = _admin_aktif()
    if admin is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat menolak."
    if type(enrollment_id) is not int or enrollment_id <= 0:
        return False, "ID pendaftaran tidak valid."
    if not isinstance(alasan, str) or not alasan.strip():
        return False, "Alasan penolakan wajib diisi."
    alasan = alasan.strip()
    try:
        hasil = enrollment_repo.proses_keputusan_admin(
            enrollment_id=enrollment_id, processed_by=admin["id"],
            keputusan="ditolak", alasan_tolak=alasan,
        )
    except (ValueError, psycopg.Error, RuntimeError) as exc:
        return False, f"Penolakan pendaftaran gagal ({type(exc).__name__}): {exc}"
    if not hasil.get("berhasil"):
        return False, hasil.get("pesan", "Pendaftaran tidak dapat ditolak.")

    siswa = user_repo.cari_by_id(hasil["student_id"])
    refunds = hasil.get("refunds") or []
    if siswa is None:
        return True, f"Pendaftaran ditolak. {len(refunds)} refund simulasi tercatat; email siswa tidak ditemukan."

    if refunds:
        from app.services import billing_receipt_service
        semua_email_ok = True
        detail_email = []
        for refund in refunds:
            refund_detail = {
                **refund, "nama_siswa": siswa.get("nama_lengkap"),
                "email_siswa": siswa.get("email"), "nama_program": hasil["nama_program"],
                "alasan": alasan,
            }
            try:
                pdf = billing_receipt_service.buat_pdf_bukti_refund(refund_detail)
                email_ok, email_message = billing_receipt_service.kirim_pdf_refund_via_email(refund_detail, pdf)
                semua_email_ok = semua_email_ok and email_ok
                detail_email.append(email_message)
            except Exception as exc:
                semua_email_ok = False
                detail_email.append(f"Dokumen/email refund gagal ({type(exc).__name__}).")
        pesan = f"Pendaftaran {hasil['nama_program']} ditolak. {len(refunds)} refund simulasi berhasil dicatat."
        if semua_email_ok:
            pesan += " Email penolakan dan PDF refund dikirim."
        else:
            pesan += " Refund tetap tercatat, tetapi email/PDF perlu diperiksa: " + "; ".join(detail_email)
        return True, pesan

    try:
        terkirim = email_service.kirim_notifikasi_status(
            email=siswa["email"], nama=siswa["nama_lengkap"], kategori="pendaftaran",
            status="ditolak", detail=f"Program: {hasil['nama_program']}\nAlasan: {alasan}",
        )
    except Exception:
        terkirim = False
    pesan = f"Pendaftaran {hasil['nama_program']} ditolak. Alasan tersimpan."
    return True, pesan + (" Email pemberitahuan dikirim." if terkirim else " Email pemberitahuan gagal dikirim; data tetap tersimpan.")

