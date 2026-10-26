"""Service persetujuan akun dan pendaftaran program SIBIMA."""

import psycopg

from app import session
from app.db import pool
from app.repositories import (
    user_repo,
    profile_repo,
    enrollment_repo,
    onboarding_repo,
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
    """Setujui tutor; untuk siswa, setujui akun + paket + invoice atomik."""
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

    if target["role"] == "siswa":
        # Siswa wajib sudah memilih satu paket. Operasi akun, NIS, enrollment,
        # dan invoice pertama dijalankan di satu transaksi database.
        try:
            hasil = onboarding_repo.setujui_siswa_dengan_paket(
                user_id=target["id"],
                approved_by=admin["id"],
            )
        except ValueError as exc:
            return False, str(exc)
        except (psycopg.Error, RuntimeError) as exc:
            return False, (
                "Persetujuan akun, paket, dan tagihan gagal; transaksi dibatalkan "
                f"({type(exc).__name__}). Periksa database sebelum mencoba lagi."
            )

        invoice = hasil.get("invoice")
        detail = (
            f"NIS: {hasil['nis']}\n"
            f"Program: {hasil['nama_program']} ({hasil['kode_program']})\n"
            f"Jenjang: {hasil['jenjang']}"
        )
        if invoice:
            detail += (
                f"\nNo. invoice: {invoice['no_invoice']}"
                f"\nTagihan pertama: {_format_rupiah(invoice['jumlah'])}"
                f"\nPeriode: {invoice['periode'].strftime('%B %Y')}"
                f"\nJatuh tempo: {invoice['jatuh_tempo'].strftime('%d-%m-%Y')}"
            )
            detail_pesan = (
                f" Tagihan pertama {invoice['no_invoice']} sebesar "
                f"{_format_rupiah(invoice['jumlah'])}, jatuh tempo "
                f"{invoice['jatuh_tempo'].strftime('%d-%m-%Y')}."
            )
        else:
            detail += "\nProgram gratis; tidak dibuat invoice bernilai nol."
            detail_pesan = " Program gratis, tidak dibuat tagihan."

        try:
            terkirim = email_service.kirim_notifikasi_status(
                email=hasil["email"],
                nama=hasil["nama_lengkap"],
                kategori="akun",
                status="aktif",
                detail=detail,
            )
        except Exception:
            terkirim = False

        pesan = (
            f"Akun {hasil['username']} disetujui; NIS {hasil['nis']} diterbitkan, "
            f"program {hasil['nama_program']} diaktifkan.{detail_pesan}"
        )
        if not terkirim:
            return True, pesan + " Email notifikasi gagal dikirim."
        return True, pesan + " Email pemberitahuan telah dikirim."

    # Tutor tidak memilih paket; cukup persetujuan akun dan penerbitan kode tutor.
    try:
        profile_repo.proses_persetujuan_akun(
            user_id=target["id"],
            approved_by=admin["id"],
            status="aktif",
        )
        terbaru = user_repo.cari_by_id(target["id"])
        if terbaru is None or terbaru.get("status") != "aktif":
            return False, "Persetujuan akun gagal diverifikasi di database."
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT kode_tutor FROM tutors WHERE user_id = %s",
                    (target["id"],),
                )
                row = cur.fetchone()
                kode_tutor = row[0] if row else None
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Terjadi kesalahan database saat menyetujui tutor ({type(exc).__name__})."

    try:
        terkirim = email_service.kirim_notifikasi_status(
            email=terbaru["email"],
            nama=terbaru["nama_lengkap"],
            kategori="akun",
            status="aktif",
            detail=f"Kode tutor: {kode_tutor}" if kode_tutor else None,
        )
    except Exception:
        terkirim = False

    pesan = f"Akun tutor {terbaru['username']} berhasil disetujui."
    if kode_tutor:
        pesan += f" Kode tutor: {kode_tutor}."
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

