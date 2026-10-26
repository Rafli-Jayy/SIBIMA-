"""Transaksi onboarding siswa: akun, paket, enrollment, dan invoice pertama.

Repository ini menangani operasi lintas tabel yang harus atomik agar status akun,
pendaftaran program, penerbitan NIS, dan invoice tidak terpisah-pisah.
"""

from psycopg.rows import dict_row

from app.db import pool
from app.repositories.billing_repo import buat_invoice_awal


def setujui_siswa_dengan_paket(user_id: int, approved_by: int) -> dict:
    """Aktifkan akun siswa + satu paket menunggu + invoice pertama dalam satu transaksi.

    Siswa wajib sudah verifikasi email dan memiliki tepat satu enrollment
    berstatus menunggu. Paket gratis diaktifkan tanpa invoice karena kolom
    invoices.jumlah mensyaratkan nilai lebih besar dari nol.
    """
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("ID pengguna tidak valid.")
    if type(approved_by) is not int or approved_by <= 0:
        raise ValueError("ID administrator tidak valid.")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, username, email, nama_lengkap, role, status,
                       email_verified, approved_by
                FROM users
                WHERE id = %s
                FOR UPDATE;
                """,
                (user_id,),
            )
            user = cur.fetchone()
            if user is None:
                raise ValueError("Pengguna tidak ditemukan.")
            if user["role"] != "siswa":
                raise ValueError("Operasi paket ini hanya untuk akun siswa.")
            if not user["email_verified"]:
                raise ValueError("Email siswa belum diverifikasi.")
            if user["status"] != "menunggu_konfirmasi":
                raise ValueError("Akun siswa tidak lagi menunggu persetujuan.")

            cur.execute(
                """
                SELECT user_id, nis
                FROM students
                WHERE user_id = %s
                FOR UPDATE;
                """,
                (user_id,),
            )
            profil = cur.fetchone()
            if profil is None:
                raise ValueError("Profil siswa tidak ditemukan.")

            # Kunci pendaftaran dan program agar dua admin tidak memproses
            # pilihan yang sama secara bersamaan.
            cur.execute(
                """
                SELECT e.id AS enrollment_id, e.program_id, e.status,
                       p.kode AS kode_program, p.nama AS nama_program,
                       p.jenjang, p.harga_bulanan
                FROM enrollments AS e
                JOIN programs AS p ON p.id = e.program_id
                WHERE e.student_id = %s AND e.status = 'menunggu'
                ORDER BY e.created_at, e.id
                FOR UPDATE OF e, p;
                """,
                (user_id,),
            )
            pilihan_paket = cur.fetchall()

            if not pilihan_paket:
                raise ValueError(
                    "Siswa wajib memilih satu paket bimbel sebelum akun disetujui."
                )
            if len(pilihan_paket) != 1:
                raise ValueError(
                    "Ditemukan lebih dari satu pendaftaran yang menunggu untuk siswa ini. "
                    "Rapikan antrean paket terlebih dahulu sebelum menyetujui akun."
                )

            paket = pilihan_paket[0]

            nis = profil["nis"]
            if not nis:
                cur.execute(
                    """
                    UPDATE students
                    SET nis = fn_next_nis()
                    WHERE user_id = %s AND nis IS NULL
                    RETURNING nis;
                    """,
                    (user_id,),
                )
                hasil_nis = cur.fetchone()
                if hasil_nis is None:
                    raise RuntimeError("NIS gagal diterbitkan.")
                nis = hasil_nis["nis"]

            cur.execute(
                """
                UPDATE enrollments
                SET status = 'aktif',
                    processed_by = %s,
                    processed_at = now(),
                    alasan_tolak = NULL
                WHERE id = %s AND student_id = %s AND status = 'menunggu'
                RETURNING id;
                """,
                (approved_by, paket["enrollment_id"], user_id),
            )
            if cur.fetchone() is None:
                raise ValueError(
                    "Pilihan paket sudah diproses. Muat ulang antrean admin."
                )

            jumlah = paket["harga_bulanan"]
            invoice = buat_invoice_awal(
                cur=cur,
                enrollment_id=paket["enrollment_id"],
                jumlah=jumlah,
            )

            # Status akun diperbarui dalam transaksi yang sama dengan paket
            # dan invoice. Jika bagian ini gagal, seluruh transaksi rollback.
            cur.execute(
                """
                UPDATE users
                SET status = 'aktif',
                    approved_by = %s,
                    approved_at = now(),
                    reject_reason = NULL
                WHERE id = %s
                  AND role = 'siswa'
                  AND status = 'menunggu_konfirmasi'
                  AND email_verified = TRUE
                RETURNING id;
                """,
                (approved_by, user_id),
            )
            if cur.fetchone() is None:
                raise ValueError(
                    "Status akun berubah. Muat ulang antrean konfirmasi."
                )

        conn.commit()

    return {
        "user_id": user_id,
        "username": user["username"],
        "email": user["email"],
        "nama_lengkap": user["nama_lengkap"],
        "role": user["role"],
        "status": "aktif",
        "nis": nis,
        "enrollment_id": paket["enrollment_id"],
        "program_id": paket["program_id"],
        "kode_program": paket["kode_program"],
        "nama_program": paket["nama_program"],
        "jenjang": paket["jenjang"],
        "harga_bulanan": jumlah,
        "invoice": invoice,
    }


def tolak_siswa_dan_paket(
    user_id: int,
    approved_by: int,
    alasan: str,
) -> dict:
    """Tolak akun siswa dan semua pilihan paket yang masih menunggu atomik."""
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("ID pengguna tidak valid.")
    if type(approved_by) is not int or approved_by <= 0:
        raise ValueError("ID administrator tidak valid.")
    if not isinstance(alasan, str) or not alasan.strip():
        raise ValueError("Alasan penolakan wajib diisi.")
    alasan = alasan.strip()

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, username, email, nama_lengkap, role, status,
                       email_verified
                FROM users
                WHERE id = %s
                FOR UPDATE;
                """,
                (user_id,),
            )
            user = cur.fetchone()
            if user is None:
                raise ValueError("Pengguna tidak ditemukan.")
            if user["role"] != "siswa":
                raise ValueError("Operasi penolakan paket ini hanya untuk siswa.")
            if not user["email_verified"]:
                raise ValueError("Email siswa belum diverifikasi.")
            if user["status"] != "menunggu_konfirmasi":
                raise ValueError("Akun siswa tidak lagi menunggu persetujuan.")

            cur.execute(
                """
                UPDATE enrollments
                SET status = 'ditolak',
                    processed_by = %s,
                    processed_at = now(),
                    alasan_tolak = %s
                WHERE student_id = %s AND status = 'menunggu'
                RETURNING id;
                """,
                (approved_by, alasan, user_id),
            )
            enrollment_ids = [row["id"] for row in cur.fetchall()]

            cur.execute(
                """
                UPDATE users
                SET status = 'ditolak',
                    approved_by = %s,
                    approved_at = now(),
                    reject_reason = %s
                WHERE id = %s
                  AND role = 'siswa'
                  AND status = 'menunggu_konfirmasi'
                  AND email_verified = TRUE
                RETURNING id;
                """,
                (approved_by, alasan, user_id),
            )
            if cur.fetchone() is None:
                raise ValueError(
                    "Status akun berubah. Muat ulang antrean konfirmasi."
                )

        conn.commit()

    return {
        "user_id": user_id,
        "username": user["username"],
        "email": user["email"],
        "nama_lengkap": user["nama_lengkap"],
        "enrollment_ids": enrollment_ids,
        "alasan": alasan,
    }
