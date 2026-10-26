"""Repository jadwal berulang SIBIMA.

Semua query menggunakan parameter terikat. Bentrok waktu tetap dilindungi oleh
exclusion constraint PostgreSQL (ex_bentrok_tutor dan ex_bentrok_ruang), selain
pemeriksaan awal untuk memberikan pesan yang lebih ramah di CLI.
"""

from psycopg.rows import dict_row

from app.db import pool

HARI_VALID = ("senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu")


def daftar_opsi_program(*, aktif_saja: bool = True):
    """Daftar program untuk filter atau penjadwalan."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if aktif_saja:
                cur.execute(
                    """
                    SELECT id, kode, nama, jenjang, status::text AS status
                    FROM programs
                    WHERE status = 'buka'
                    ORDER BY nama, id;
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT id, kode, nama, jenjang, status::text AS status
                    FROM programs
                    ORDER BY nama, id;
                    """
                )
            return cur.fetchall()


def daftar_opsi_tutor(*, aktif_saja: bool = True):
    """Daftar tutor dengan akun aktif secara default."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if aktif_saja:
                cur.execute(
                    """
                    SELECT t.user_id AS id, t.kode_tutor, u.nama_lengkap,
                           u.status::text AS status, t.keahlian
                    FROM tutors AS t
                    JOIN users AS u ON u.id = t.user_id
                    WHERE u.role = 'tutor' AND u.status = 'aktif'
                    ORDER BY u.nama_lengkap, t.user_id;
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT t.user_id AS id, t.kode_tutor, u.nama_lengkap,
                           u.status::text AS status, t.keahlian
                    FROM tutors AS t
                    JOIN users AS u ON u.id = t.user_id
                    WHERE u.role = 'tutor'
                    ORDER BY u.nama_lengkap, t.user_id;
                    """
                )
            return cur.fetchall()


def daftar_opsi_ruang(*, aktif_saja: bool = True):
    """Daftar ruang; ruang nonaktif tidak dipilih untuk jadwal baru."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if aktif_saja:
                cur.execute(
                    """
                    SELECT id, nama, kapasitas, aktif
                    FROM rooms
                    WHERE aktif = TRUE
                    ORDER BY nama, id;
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT id, nama, kapasitas, aktif
                    FROM rooms
                    ORDER BY nama, id;
                    """
                )
            return cur.fetchall()


def daftar_jadwal(
    *,
    program_id: int | None = None,
    tutor_id: int | None = None,
    room_id: int | None = None,
    hari: str | None = None,
    aktif: bool | None = None,
):
    """Daftar jadwal dengan filter opsional per program/tutor/ruang/hari/status."""
    if hari is not None and hari not in HARI_VALID:
        raise ValueError("Filter hari tidak valid.")

    kondisi = []
    params = []
    for kolom, nilai in (
        ("s.program_id", program_id),
        ("s.tutor_id", tutor_id),
        ("s.room_id", room_id),
        ("s.hari", hari),
        ("s.aktif", aktif),
    ):
        if nilai is not None:
            if kolom == "s.hari":
                kondisi.append("s.hari = %s::nama_hari")
            else:
                kondisi.append(f"{kolom} = %s")
            params.append(nilai)

    where_sql = "WHERE " + " AND ".join(kondisi) if kondisi else ""
    query = f"""
        SELECT
            s.id,
            s.program_id,
            p.kode AS kode_program,
            p.nama AS nama_program,
            p.jenjang,
            s.tutor_id,
            t.kode_tutor,
            tu.nama_lengkap AS nama_tutor,
            s.room_id,
            r.nama AS nama_ruang,
            r.kapasitas AS kapasitas_ruang,
            s.hari::text AS hari,
            s.jam_mulai,
            s.jam_selesai,
            s.aktif,
            COALESCE(en.jumlah_siswa, 0)::INT AS jumlah_siswa,
            COALESCE(ss.jumlah_pertemuan, 0)::INT AS jumlah_pertemuan
        FROM schedules AS s
        JOIN programs AS p ON p.id = s.program_id
        JOIN tutors AS t ON t.user_id = s.tutor_id
        JOIN users AS tu ON tu.id = t.user_id
        JOIN rooms AS r ON r.id = s.room_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::INT AS jumlah_siswa
            FROM enrollments AS e
            WHERE e.program_id = s.program_id
              AND e.status = 'aktif'
        ) AS en ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::INT AS jumlah_pertemuan
            FROM class_sessions AS cs
            WHERE cs.schedule_id = s.id
        ) AS ss ON TRUE
        {where_sql}
        ORDER BY
            CASE s.hari
                WHEN 'senin' THEN 1 WHEN 'selasa' THEN 2
                WHEN 'rabu' THEN 3 WHEN 'kamis' THEN 4
                WHEN 'jumat' THEN 5 WHEN 'sabtu' THEN 6 ELSE 7
            END,
            s.jam_mulai, p.nama, s.id;
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def ambil_jadwal(jadwal_id: int):
    """Ambil satu jadwal berdasarkan ID."""
    daftar = daftar_jadwal()
    return next((item for item in daftar if item["id"] == jadwal_id), None)


def cek_bentrok(
    *,
    tutor_id: int,
    room_id: int,
    hari: str,
    jam_mulai,
    jam_selesai,
    kecuali_id: int | None = None,
):
    """Kembalikan info bentrok pertama, atau None bila jadwal tidak bentrok."""
    filter_id = "AND s.id <> %s" if kecuali_id is not None else ""
    parameter_buntut = (kecuali_id,) if kecuali_id is not None else ()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT s.id, 'tutor'::text AS jenis, p.nama AS nama_program,
                       s.jam_mulai, s.jam_selesai
                FROM schedules AS s
                JOIN programs AS p ON p.id = s.program_id
                WHERE s.aktif = TRUE
                  AND s.tutor_id = %s
                  AND s.hari = %s::nama_hari
                  AND s.jam_mulai < %s
                  AND s.jam_selesai > %s
                  {filter_id}
                ORDER BY s.jam_mulai
                LIMIT 1;
                """,
                (tutor_id, hari, jam_selesai, jam_mulai, *parameter_buntut),
            )
            bentrok = cur.fetchone()
            if bentrok:
                return bentrok

            cur.execute(
                f"""
                SELECT s.id, 'ruang'::text AS jenis, p.nama AS nama_program,
                       s.jam_mulai, s.jam_selesai
                FROM schedules AS s
                JOIN programs AS p ON p.id = s.program_id
                WHERE s.aktif = TRUE
                  AND s.room_id = %s
                  AND s.hari = %s::nama_hari
                  AND s.jam_mulai < %s
                  AND s.jam_selesai > %s
                  {filter_id}
                ORDER BY s.jam_mulai
                LIMIT 1;
                """,
                (room_id, hari, jam_selesai, jam_mulai, *parameter_buntut),
            )
            return cur.fetchone()


def buat_jadwal(
    *,
    program_id: int,
    tutor_id: int,
    room_id: int,
    hari: str,
    jam_mulai,
    jam_selesai,
    admin_id: int,
) -> int:
    """Buat jadwal dan catat aktivitas dalam satu transaksi."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO schedules (
                    program_id, tutor_id, room_id, hari, jam_mulai, jam_selesai, aktif
                )
                VALUES (%s, %s, %s, %s::nama_hari, %s, %s, TRUE)
                RETURNING id;
                """,
                (program_id, tutor_id, room_id, hari, jam_mulai, jam_selesai),
            )
            jadwal_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO activity_logs (user_id, aksi, detail)
                VALUES (%s, 'JADWAL_DITAMBAHKAN', %s);
                """,
                (admin_id, f"schedule_id={jadwal_id}; program_id={program_id}; tutor_id={tutor_id}; room_id={room_id}; hari={hari}"),
            )
        conn.commit()
    return jadwal_id


def ubah_jadwal(jadwal_id: int, *, data: dict, admin_id: int) -> bool:
    """Perbarui jadwal aktif dan simpan log dalam transaksi yang sama."""
    kolom_diizinkan = {
        "program_id", "tutor_id", "room_id", "hari", "jam_mulai", "jam_selesai"
    }
    if not isinstance(data, dict) or not data:
        raise ValueError("Tidak ada perubahan jadwal.")
    if set(data) - kolom_diizinkan:
        raise ValueError("Kolom jadwal tidak diizinkan.")

    perubahan = dict(data)
    if "hari" in perubahan:
        perubahan["hari"] = str(perubahan["hari"]).lower()

    assignments = []
    params = []
    for kolom, nilai in perubahan.items():
        if kolom == "hari":
            assignments.append("hari = %s::nama_hari")
        else:
            assignments.append(f"{kolom} = %s")
        params.append(nilai)

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE schedules SET {', '.join(assignments)} WHERE id = %s AND aktif = TRUE RETURNING id;",
                (*params, jadwal_id),
            )
            hasil = cur.fetchone()
            if hasil is None:
                conn.rollback()
                return False
            cur.execute(
                "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, 'JADWAL_DIUBAH', %s);",
                (admin_id, f"schedule_id={jadwal_id}; fields={','.join(perubahan.keys())}"),
            )
        conn.commit()
    return True


def ada_riwayat_pertemuan(jadwal_id: int) -> bool:
    """True jika jadwal sudah dipakai oleh satu atau lebih pertemuan."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM class_sessions WHERE schedule_id = %s);",
                (jadwal_id,),
            )
            return bool(cur.fetchone()[0])


def nonaktifkan_jadwal(jadwal_id: int, *, admin_id: int) -> bool:
    """Menonaktifkan jadwal tanpa menghapus riwayat pertemuan yang ada."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE schedules SET aktif = FALSE WHERE id = %s AND aktif = TRUE RETURNING id;",
                (jadwal_id,),
            )
            hasil = cur.fetchone()
            if hasil is None:
                conn.rollback()
                return False
            cur.execute(
                "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, 'JADWAL_DINONAKTIFKAN', %s);",
                (admin_id, f"schedule_id={jadwal_id}"),
            )
        conn.commit()
    return True
