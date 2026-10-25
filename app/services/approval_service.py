"""Service persetujuan akun, enrollment, dan permohonan SIBIMA."""

import psycopg

from app import session
from app.repositories import (
    user_repo,
    profile_repo,
    enrollment_repo,
    engagement_repo,
    schedule_repo,
)
from app.services import email_service


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
    """Menyetujui akun siswa/tutor dan menerbitkan identitas profil atomik."""
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
        profile_repo.proses_persetujuan_akun(
            user_id=target["id"],
            approved_by=admin["id"],
            status="aktif",
        )
        terbaru = user_repo.cari_by_id(target["id"])
        if terbaru is None or terbaru.get("status") != "aktif":
            return False, "Persetujuan akun gagal diverifikasi di database."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error:
        return False, "Terjadi kesalahan database saat menyetujui akun."

    try:
        terkirim = email_service.kirim_notifikasi_status(
            email=terbaru["email"],
            nama=terbaru["nama_lengkap"],
            kategori="akun",
            status="aktif",
        )
    except Exception:
        terkirim = False

    if not terkirim:
        return True, "Akun berhasil disetujui, tetapi email notifikasi gagal dikirim."
    return True, (
        f"Akun {terbaru['username']} berhasil disetujui. "
        "Email pemberitahuan telah dikirim."
    )


def tolak_akun(user_id: int, alasan: str):
    """Menolak akun siswa/tutor dan menyimpan alasan penolakan."""
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
        profile_repo.proses_persetujuan_akun(
            user_id=target["id"],
            approved_by=admin["id"],
            status="ditolak",
            reject_reason=alasan,
        )
        terbaru = user_repo.cari_by_id(target["id"])
        if terbaru is None or terbaru.get("status") != "ditolak":
            return False, "Penolakan akun gagal diverifikasi di database."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error:
        return False, "Terjadi kesalahan database saat menolak akun."

    try:
        terkirim = email_service.kirim_notifikasi_status(
            email=terbaru["email"],
            nama=terbaru["nama_lengkap"],
            kategori="akun",
            status="ditolak",
            detail=alasan,
        )
    except Exception:
        terkirim = False

    if not terkirim:
        return True, "Akun berhasil ditolak dan alasan tersimpan, tetapi email notifikasi gagal dikirim."
    return True, f"Akun {terbaru['username']} berhasil ditolak. Email pemberitahuan telah dikirim."


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
    """Setujui pendaftaran program dan buat tagihan pertama dalam transaksi."""
    admin = _admin_aktif()
    if admin is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat menyetujui."
    if type(enrollment_id) is not int or enrollment_id <= 0:
        return False, "ID pendaftaran tidak valid."

    try:
        hasil = enrollment_repo.proses_keputusan_admin(
            enrollment_id=enrollment_id,
            processed_by=admin["id"],
            keputusan="disetujui",
        )
    except ValueError as exc:
        return False, str(exc)
    except (psycopg.Error, RuntimeError) as exc:
        return False, (
            "Persetujuan dan pembuatan tagihan gagal. Transaksi dibatalkan "
            f"({type(exc).__name__}). Silakan periksa database lalu coba lagi."
        )

    if not hasil.get("berhasil"):
        return False, hasil.get("pesan", "Pendaftaran tidak dapat disetujui.")

    try:
        siswa = user_repo.cari_by_id(hasil["student_id"])
    except psycopg.Error:
        siswa = None
    invoice = hasil.get("invoice")
    if invoice:
        detail_email = (
            f"Program: {hasil['nama_program']}\n"
            f"No. invoice: {invoice['no_invoice']}\n"
            f"Jumlah tagihan pertama: {_format_rupiah(invoice['jumlah'])}\n"
            f"Periode: {invoice['periode'].strftime('%B %Y')}\n"
            f"Jatuh tempo: {invoice['jatuh_tempo'].strftime('%d-%m-%Y')}"
        )
        pesan_tagihan = (
            f" Tagihan pertama {invoice['no_invoice']} sebesar "
            f"{_format_rupiah(invoice['jumlah'])}, jatuh tempo "
            f"{invoice['jatuh_tempo'].strftime('%d-%m-%Y')}."
        )
    else:
        detail_email = (
            f"Program: {hasil['nama_program']}\n"
            "Program ini gratis sehingga tidak dibuat tagihan."
        )
        pesan_tagihan = " Program gratis, tidak dibuat tagihan."

    if siswa is None:
        return True, (
            f"Pendaftaran {hasil['nama_program']} berhasil disetujui, "
            "tetapi data pengguna siswa tidak ditemukan setelah proses."
            + pesan_tagihan
        )

    try:
        terkirim = email_service.kirim_notifikasi_status(
            email=siswa["email"],
            nama=siswa["nama_lengkap"],
            kategori="pendaftaran",
            status="aktif",
            detail=detail_email,
        )
    except Exception:
        terkirim = False

    pesan = f"Pendaftaran {hasil['nama_program']} disetujui.{pesan_tagihan}"
    if not terkirim:
        return True, pesan + " Email notifikasi gagal dikirim."
    return True, pesan + " Email pemberitahuan telah dikirim."


def tolak_enrollment(enrollment_id: int, alasan: str):
    """Tolak pendaftaran program dengan alasan dan pencatatan admin."""
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
            enrollment_id=enrollment_id,
            processed_by=admin["id"],
            keputusan="ditolak",
            alasan_tolak=alasan,
        )
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Terjadi kesalahan database saat menolak pendaftaran ({type(exc).__name__})."

    if not hasil.get("berhasil"):
        return False, hasil.get("pesan", "Pendaftaran tidak dapat ditolak.")

    siswa = user_repo.cari_by_id(hasil["student_id"])
    if siswa is None:
        return True, f"Pendaftaran {hasil['nama_program']} ditolak; data pengguna siswa tidak ditemukan."

    try:
        terkirim = email_service.kirim_notifikasi_status(
            email=siswa["email"],
            nama=siswa["nama_lengkap"],
            kategori="pendaftaran",
            status="ditolak",
            detail=f"Program: {hasil['nama_program']}\nAlasan: {alasan}",
        )
    except Exception:
        terkirim = False

    pesan = f"Pendaftaran {hasil['nama_program']} ditolak. Alasan tersimpan."
    if not terkirim:
        return True, pesan + " Email notifikasi gagal dikirim."
    return True, pesan + " Email pemberitahuan telah dikirim."


def proses_permohonan(
    jenis: str,
    permohonan_id: int,
    keputusan: str,
    alasan: str | None = None,
):
    """Proses permohonan izin siswa atau perubahan jadwal tutor."""
    admin = _admin_aktif()
    if admin is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat memproses."
    if type(permohonan_id) is not int or permohonan_id <= 0:
        return False, "ID permohonan tidak valid."
    if keputusan not in {"disetujui", "ditolak"}:
        return False, "Keputusan harus 'disetujui' atau 'ditolak'."
    if keputusan == "ditolak" and not (isinstance(alasan, str) and alasan.strip()):
        return False, "Alasan penolakan wajib diisi."

    if jenis == "izin":
        nama_repo = "proses_permohonan_izin"
        repo = engagement_repo
    elif jenis == "perubahan_jadwal":
        nama_repo = "proses_permohonan_perubahan_jadwal"
        repo = schedule_repo
    else:
        return False, "Jenis permohonan tidak dikenal."

    operasi = getattr(repo, nama_repo, None)
    if not callable(operasi):
        return False, f"Repository belum menyediakan fungsi {nama_repo}()."

    try:
        return operasi(
            permohonan_id=permohonan_id,
            keputusan=keputusan,
            processed_by=admin["id"],
            alasan=alasan.strip() if alasan else None,
        )
    except psycopg.Error:
        return False, "Terjadi kesalahan database saat memproses permohonan."
