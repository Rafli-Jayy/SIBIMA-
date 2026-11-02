"""Query pengumuman admin dan pembacaan ringkasan pengumuman siswa."""

from psycopg.rows import dict_row

from app.db import pool


_ROLE_LABEL = {"siswa": "Siswa", "tutor": "Tutor"}


def _catat_log(cur, user_id: int | None, aksi: str, detail: str) -> None:
    cur.execute(
        "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, %s, %s);",
        (user_id, aksi[:60], detail[:4000]),
    )


def buat_pengumuman(judul: str, isi: str, admin_id: int, target_roles: list[str]) -> dict:
    """Simpan pengumuman dan target penerimanya dalam satu transaksi."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO announcements (judul, isi, dibuat_by)
                VALUES (%s, %s, %s)
                RETURNING id, judul, isi, dibuat_by, created_at, archived_at;
                """,
                (judul, isi, admin_id),
            )
            pengumuman = cur.fetchone()
            for role in target_roles:
                cur.execute(
                    """
                    INSERT INTO announcement_targets (announcement_id, target_role)
                    VALUES (%s, %s);
                    """,
                    (pengumuman["id"], role),
                )
            _catat_log(
                cur,
                admin_id,
                "PENGUMUMAN_DIBUAT",
                f"Pengumuman ID {pengumuman['id']} dibuat untuk {', '.join(_ROLE_LABEL[r] for r in target_roles)}: {judul[:160]}",
            )
        conn.commit()
    pengumuman["target_roles"] = list(target_roles)
    return pengumuman


def daftar_pengumuman_admin(status: str = "aktif", limit: int = 100) -> list[dict]:
    """Ambil pengumuman aktif atau arsip beserta target dan nama pembuat."""
    if status not in {"aktif", "arsip"}:
        raise ValueError("Status daftar pengumuman tidak valid.")
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas pengumuman tidak valid.")
    limit = min(limit, 500)
    kondisi_arsip = "a.archived_at IS NULL" if status == "aktif" else "a.archived_at IS NOT NULL"
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT a.id, a.judul, a.isi, a.created_at, a.archived_at, a.dibuat_by,
                       COALESCE(u.nama_lengkap, u.username, 'Admin tidak tersedia') AS nama_pembuat,
                       COALESCE(array_agg(at.target_role::text ORDER BY at.target_role)
                           FILTER (WHERE at.target_role IS NOT NULL), ARRAY[]::text[]) AS target_roles
                FROM announcements AS a
                LEFT JOIN users AS u ON u.id = a.dibuat_by
                LEFT JOIN announcement_targets AS at ON at.announcement_id = a.id
                WHERE {kondisi_arsip} AND a.sumber = 'admin'
                GROUP BY a.id, u.nama_lengkap, u.username
                ORDER BY a.created_at DESC, a.id DESC
                LIMIT %s;
                """,
                (limit,),
            )
            return cur.fetchall()


def detail_pengumuman_admin(announcement_id: int) -> dict | None:
    """Ambil detail satu pengumuman untuk Admin."""
    if type(announcement_id) is not int or announcement_id < 1:
        raise ValueError("ID pengumuman tidak valid.")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT a.id, a.judul, a.isi, a.created_at, a.archived_at, a.dibuat_by,
                       COALESCE(u.nama_lengkap, u.username, 'Admin tidak tersedia') AS nama_pembuat,
                       COALESCE(array_agg(at.target_role::text ORDER BY at.target_role)
                           FILTER (WHERE at.target_role IS NOT NULL), ARRAY[]::text[]) AS target_roles
                FROM announcements AS a
                LEFT JOIN users AS u ON u.id = a.dibuat_by
                LEFT JOIN announcement_targets AS at ON at.announcement_id = a.id
                WHERE a.id = %s AND a.sumber = 'admin'
                GROUP BY a.id, u.nama_lengkap, u.username;
                """,
                (announcement_id,),
            )
            return cur.fetchone()


def arsipkan_pengumuman(announcement_id: int, admin_id: int) -> bool:
    """Arsipkan pengumuman aktif. Arsip bersifat satu arah/permanen."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE announcements
                SET archived_at = now()
                WHERE id = %s AND archived_at IS NULL AND sumber = 'admin'
                RETURNING id, judul;
                """,
                (announcement_id,),
            )
            item = cur.fetchone()
            if item:
                _catat_log(
                    cur,
                    admin_id,
                    "PENGUMUMAN_DIARSIPKAN",
                    f"Pengumuman ID {item['id']} diarsipkan: {item['judul'][:160]}",
                )
        conn.commit()
    return item is not None


def pengumuman_terbaru_siswa(limit: int = 3) -> list[dict]:
    """Kompatibilitas sementara dashboard lama: hanya pengumuman aktif target siswa."""
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas pengumuman tidak valid.")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT a.id, a.judul, a.isi, a.created_at
                FROM announcements AS a
                JOIN announcement_targets AS at ON at.announcement_id = a.id
                WHERE a.archived_at IS NULL AND a.penerima_user_id IS NULL
                  AND a.sumber = 'admin' AND at.target_role = 'siswa'
                ORDER BY a.created_at DESC, a.id DESC
                LIMIT %s;
                """,
                (min(limit, 10),),
            )
            return cur.fetchall()




# PATCH-N2: sumber, filter, arsip pribadi dan pengumuman kelas Tutor.
from secrets import token_hex


def _valid_pengguna(user_id, role):
    if type(user_id) is not int or user_id < 1 or role not in ('siswa', 'tutor'):
        raise ValueError('Akun notifikasi tidak valid.')


def _inbox_scope(arsip: bool = False) -> str:
    # Operator tidak dikendalikan string masukan pengguna.
    archived_condition = 'r.archived_at IS NOT NULL' if arsip else 'r.archived_at IS NULL'
    time_condition = '' if arsip else 'AND (a.expires_at IS NULL OR a.expires_at > now())'
    return f'''a.archived_at IS NULL {time_condition} AND {archived_condition}
      AND (a.penerima_user_id = %s OR
         (a.penerima_user_id IS NULL AND EXISTS (
           SELECT 1 FROM announcement_targets t WHERE t.announcement_id=a.id
           AND t.target_role = %s)))'''


def daftar_notifikasi_penerima(user_id: int, role: str, limit: int = 200, *,
                                arsip: bool = False, kategori: str = 'semua',
                                sumber: str = 'semua', baca: str = 'semua') -> list[dict]:
    _valid_pengguna(user_id, role)
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('Limit notifikasi tidak valid.')
    if kategori not in ('semua','umum','akun','pendaftaran','tagihan','nilai','absensi','jadwal','pengingat','pengumuman'):
        raise ValueError('Kategori tidak valid.')
    if sumber not in ('semua','admin','tutor','sistem') or baca not in ('semua','dibaca','baru'):
        raise ValueError('Filter notifikasi tidak valid.')
    filters = ''
    params = [user_id,user_id,role]
    if kategori == 'pengumuman':
        filters += " AND a.sumber IN ('admin','tutor')"
    elif kategori != 'semua':
        filters += ' AND a.kategori=%s'; params.append(kategori)
    if sumber != 'semua':
        filters += ' AND a.sumber=%s'; params.append(sumber)
    if baca == 'baru':
        filters += ' AND r.read_at IS NULL'
    elif baca == 'dibaca':
        filters += ' AND r.read_at IS NOT NULL'
    params.append(limit)
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f'''
          SELECT a.id,a.judul,a.isi,a.created_at,a.sumber,a.kategori,
                 a.expires_at,a.program_id,a.related_type,a.related_id,
                 a.actor_user_id,a.batch_key,
                 COALESCE(u.nama_lengkap,u.username) AS nama_pembuat,
                 COALESCE(actor.nama_lengkap,actor.username) AS nama_pelaku,
                 p.nama AS nama_program,r.read_at,
                 (r.read_at IS NOT NULL) AS sudah_dibaca,
                 r.archived_at
          FROM announcements a
          LEFT JOIN announcement_reads r ON r.announcement_id=a.id AND r.user_id=%s
          LEFT JOIN users u ON u.id=a.dibuat_by
          LEFT JOIN users actor ON actor.id=a.actor_user_id
          LEFT JOIN programs p ON p.id=a.program_id
          WHERE {_inbox_scope(arsip)} {filters}
          ORDER BY CASE
           WHEN a.judul ILIKE '%%Dibatalkan%%' OR a.judul ILIKE '%%Perubahan Jadwal%%'
             OR a.judul ILIKE '%%Tidak Berhasil%%' THEN 0
           WHEN a.kategori IN ('jadwal','pengingat') THEN 1
           ELSE 2 END,
           a.created_at DESC,a.id DESC LIMIT %s;
        ''', tuple(params))
        return cur.fetchall()


def jumlah_notifikasi_belum_dibaca(user_id: int, role: str) -> int:
    _valid_pengguna(user_id, role)
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(f'''
          SELECT COUNT(*) FROM announcements a
          LEFT JOIN announcement_reads r ON r.announcement_id=a.id AND r.user_id=%s
          WHERE {_inbox_scope()} AND r.announcement_id IS NULL;
        ''', (user_id,user_id,role))
        return int(cur.fetchone()[0] or 0)


def detail_notifikasi_penerima(user_id: int, role: str, announcement_id: int,
                                 *, arsip: bool = False) -> dict | None:
    _valid_pengguna(user_id,role)
    if type(announcement_id) is not int or announcement_id < 1:
        raise ValueError('ID notifikasi tidak valid.')
    # N1-compatible 3-parameter ownership guard. Arsip pribadi memakai guard ekstra.
    scope = """a.id = %s AND a.archived_at IS NULL
      AND (a.expires_at IS NULL OR a.expires_at > now())
      AND (a.penerima_user_id = %s OR (a.penerima_user_id IS NULL
       AND EXISTS (SELECT 1 FROM announcement_targets t
                   WHERE t.announcement_id=a.id AND t.target_role = %s)))"""
    params = [announcement_id,user_id,role]
    if arsip:
        scope = """a.id = %s AND a.archived_at IS NULL
          AND (a.penerima_user_id = %s OR (a.penerima_user_id IS NULL
           AND EXISTS (SELECT 1 FROM announcement_targets t
                       WHERE t.announcement_id=a.id AND t.target_role = %s)))
          AND EXISTS (SELECT 1 FROM announcement_reads rr
                      WHERE rr.announcement_id=a.id AND rr.user_id=%s
                        AND rr.archived_at IS NOT NULL)"""
        params.append(user_id)
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""
          SELECT a.id,a.judul,a.isi,a.created_at,a.sumber,a.kategori,
                 a.expires_at,a.program_id,a.actor_user_id,a.related_type,a.related_id,
                 COALESCE(u.nama_lengkap,u.username) AS nama_pembuat,
                 COALESCE(actor.nama_lengkap,actor.username) AS nama_pelaku,
                 p.nama AS nama_program
          FROM announcements a LEFT JOIN users u ON u.id=a.dibuat_by
          LEFT JOIN users actor ON actor.id=a.actor_user_id
          LEFT JOIN programs p ON p.id=a.program_id
          WHERE {scope};
        """,tuple(params))
        item=cur.fetchone()
        if item is None:return None
        if not arsip:
            cur.execute("""INSERT INTO announcement_reads (announcement_id,user_id)
              VALUES (%s,%s) ON CONFLICT (announcement_id,user_id) DO NOTHING;""",
              (announcement_id,user_id))
        conn.commit()
        return item


def tandai_semua_dibaca(user_id: int, role: str) -> int:
    _valid_pengguna(user_id, role)
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(f'''
          INSERT INTO announcement_reads (announcement_id,user_id)
          SELECT a.id,%s FROM announcements a
          LEFT JOIN announcement_reads r ON r.announcement_id=a.id AND r.user_id=%s
          WHERE {_inbox_scope()} AND r.read_at IS NULL
          ON CONFLICT (announcement_id,user_id) DO NOTHING;
        ''', (user_id,user_id,user_id,role))
        n=cur.rowcount
        conn.commit()
        return n


def arsipkan_notifikasi_pribadi(user_id: int, role: str, announcement_id: int) -> bool:
    _valid_pengguna(user_id,role)
    if type(announcement_id) is not int or announcement_id < 1:
        raise ValueError('ID notifikasi tidak valid.')
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        # Guard pada INSERT-SELECT; tak boleh mengarsip pesan pengguna lain.
        cur.execute('''
          INSERT INTO announcement_reads(announcement_id,user_id,archived_at)
          SELECT a.id,%s,now() FROM announcements a
          WHERE a.id=%s AND a.archived_at IS NULL
            AND (a.expires_at IS NULL OR a.expires_at>now())
            AND (a.penerima_user_id = %s OR (a.penerima_user_id IS NULL
              AND EXISTS (SELECT 1 FROM announcement_targets t
               WHERE t.announcement_id=a.id AND t.target_role = %s)))
          ON CONFLICT (announcement_id,user_id)
          DO UPDATE SET archived_at=now()
          RETURNING announcement_id;
        ''', (user_id,announcement_id,user_id,role))
        ok=cur.fetchone() is not None
        conn.commit()
        return ok


def _cek_program_tutor(cur, tutor_id: int, program_id: int) -> dict:
    cur.execute('''SELECT p.id,p.nama,
        (SELECT COUNT(DISTINCT e.student_id)::int FROM enrollments e JOIN users u ON u.id=e.student_id
         WHERE e.program_id=p.id AND e.status::text='aktif' AND u.status::text='aktif') AS jumlah_siswa
       FROM programs p WHERE p.id=%s AND EXISTS
       (SELECT 1 FROM schedules s WHERE s.program_id=p.id AND s.tutor_id=%s AND s.aktif=TRUE);''',
       (program_id,tutor_id))
    row=cur.fetchone()
    if row is None:
        raise PermissionError('Tutor tidak memiliki jadwal aktif pada kelas ini.')
    return row


def daftar_program_pengumuman_tutor(tutor_id: int) -> list[dict]:
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('''SELECT p.id,p.nama,COUNT(DISTINCT e.student_id)::int AS jumlah_siswa
         FROM programs p JOIN schedules s ON s.program_id=p.id AND s.tutor_id=%s AND s.aktif=TRUE
         LEFT JOIN enrollments e ON e.program_id=p.id AND e.status::text='aktif'
         GROUP BY p.id,p.nama ORDER BY p.nama''',(tutor_id,))
        return cur.fetchall()


def terbitkan_pengumuman_tutor(tutor_id: int, program_id: int, judul: str,
                                 isi: str, durasi: str, expires_custom=None) -> dict:
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        program=_cek_program_tutor(cur,tutor_id,program_id)
        if program['jumlah_siswa'] <= 0:
            raise ValueError('Belum ada siswa aktif yang dapat menerima pengumuman.')
        if durasi=='7_hari':
            cur.execute("SELECT now()+interval '7 days' AS expires_at;")
        elif durasi=='pertemuan_berikut':
            cur.execute('''
             SELECT MIN((d.hari::date+s.jam_selesai) AT TIME ZONE 'Asia/Jakarta') AS expires_at
             FROM schedules s
             CROSS JOIN LATERAL generate_series(
               (now() AT TIME ZONE 'Asia/Jakarta')::date,
               (now() AT TIME ZONE 'Asia/Jakarta')::date+7,interval '1 day') AS d(hari)
             WHERE s.tutor_id=%s AND s.program_id=%s AND s.aktif=TRUE
               AND CASE s.hari::text WHEN 'senin' THEN 1 WHEN 'selasa' THEN 2
                 WHEN 'rabu' THEN 3 WHEN 'kamis' THEN 4 WHEN 'jumat' THEN 5
                 WHEN 'sabtu' THEN 6 ELSE 7 END=EXTRACT(ISODOW FROM d.hari)
               AND (d.hari::date+s.jam_selesai) AT TIME ZONE 'Asia/Jakarta'>now();
             ''',(tutor_id,program_id))
        elif durasi=='tanggal':
            cur.execute('SELECT %s::timestamptz AS expires_at;', (expires_custom,))
        else:
            raise ValueError('Pilihan masa berlaku tidak valid.')
        expires_at=cur.fetchone()['expires_at']
        if expires_at is None:
            raise ValueError('Belum ada jadwal pertemuan berikutnya yang aktif.')
        cur.execute('SELECT %s::timestamptz>now() AS valid;', (expires_at,))
        if not cur.fetchone()['valid']:
            raise ValueError('Waktu berakhir harus di masa depan.')
        batch='n2t-'+token_hex(16)
        cur.execute('''
           INSERT INTO announcements
             (judul,isi,dibuat_by,penerima_user_id,sumber,kategori,event_key,
              batch_key,expires_at,actor_user_id,program_id,related_type,related_id)
           SELECT %s,%s,%s,e.student_id,'tutor','pengumuman',%s||':'||e.student_id,
               %s,%s,%s,%s,'program',%s
           FROM enrollments e JOIN users u ON u.id=e.student_id AND u.status::text='aktif'
           WHERE e.program_id=%s AND e.status::text='aktif'
           ON CONFLICT DO NOTHING RETURNING id;
        ''',(judul,isi,tutor_id,batch,batch,expires_at,tutor_id,program_id,program_id,program_id))
        n=len(cur.fetchall())
        if n==0: raise ValueError('Tidak ada penerima saat penerbitan.')
        _catat_log(cur,tutor_id,'PENGUMUMAN_TUTOR_DIBUAT',f'program_id={program_id}; batch={batch}; siswa={n}')
        conn.commit()
        return {'batch_key':batch,'jumlah_penerima':n,'expires_at':expires_at,'nama_program':program['nama']}


def daftar_pengumuman_tutor(tutor_id: int, status: str = 'aktif') -> list[dict]:
    if status not in ('aktif','arsip'):
        raise ValueError('Status daftar pengumuman tidak valid.')
    predicate = ('a.archived_at IS NULL AND a.expires_at>now()' if status=='aktif'
                 else '(a.archived_at IS NOT NULL OR a.expires_at<=now())')
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f'''
           SELECT a.batch_key,MIN(a.judul) AS judul,MIN(a.isi) AS isi,
                  MIN(p.nama) AS nama_program,MIN(a.program_id) AS program_id,
                  MIN(a.created_at) AS created_at,MIN(a.expires_at) AS expires_at,
                  COUNT(*)::int AS jumlah_penerima
           FROM announcements a LEFT JOIN programs p ON p.id=a.program_id
           WHERE a.dibuat_by=%s AND a.sumber='tutor' AND a.batch_key IS NOT NULL
             AND {predicate}
           GROUP BY a.batch_key ORDER BY MIN(a.created_at) DESC;
        ''',(tutor_id,))
        return cur.fetchall()


def akhiri_pengumuman_tutor(tutor_id: int, batch_key: str) -> bool:
    if not isinstance(batch_key,str) or not batch_key.startswith('n2t-') or len(batch_key)>60:
        raise ValueError('Kode pengumuman tidak valid.')
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('''UPDATE announcements SET archived_at=now()
            WHERE batch_key=%s AND sumber='tutor' AND dibuat_by=%s
              AND archived_at IS NULL AND expires_at>now() RETURNING id;''',
            (batch_key,tutor_id))
        n=len(cur.fetchall())
        if n: _catat_log(cur,tutor_id,'PENGUMUMAN_TUTOR_DIAKHIRI',f'batch={batch_key}; pesan={n}')
        conn.commit()
        return n>0
