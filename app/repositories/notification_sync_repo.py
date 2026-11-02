"""PATCH-N2: sinkronisasi pengingat saat inbox dibuka. Bukan push/background worker.

Semua event idempotent, terikat akun. Tidak pernah membuat sesi/absensi palsu.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from psycopg.rows import dict_row
from app.db import pool


def sinkronisasi(user_id: int, role: str) -> None:
    if type(user_id) is not int or user_id <= 0 or role not in ('siswa', 'tutor'):
        raise ValueError('Pengguna tidak valid.')
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        # Sinkronisasi notifikasi kelas hari ini; 1 event per akun/jadwal/tanggal.
        cur.execute('''
            INSERT INTO announcements
              (judul,isi,dibuat_by,penerima_user_id,sumber,kategori,event_key,
               expires_at,program_id,related_type,related_id)
            SELECT 'Jadwal Kelas Hari Ini',
              'Hari ini ada '||p.nama||' pukul '||to_char(s.jam_mulai,'HH24:MI')||
              '-'||to_char(s.jam_selesai,'HH24:MI')||' WIB, ruang '||r.nama||
              CASE WHEN %s='tutor' THEN '. Periksa Kelola Pertemuan setelah kelas.' ELSE '.' END,
              %s,%s,'sistem','jadwal',
              'n2:jadwal:'||s.id||':'||(now() AT TIME ZONE 'Asia/Jakarta')::date::text||':'||%s,
              (((now() AT TIME ZONE 'Asia/Jakarta')::date+1)::timestamp AT TIME ZONE 'Asia/Jakarta'),
              s.program_id,'schedule',s.id
            FROM schedules s JOIN programs p ON p.id=s.program_id JOIN rooms r ON r.id=s.room_id
            WHERE s.aktif=TRUE
              AND CASE s.hari::text
                WHEN 'senin' THEN 1 WHEN 'selasa' THEN 2 WHEN 'rabu' THEN 3
                WHEN 'kamis' THEN 4 WHEN 'jumat' THEN 5 WHEN 'sabtu' THEN 6 ELSE 7 END
                = EXTRACT(ISODOW FROM (now() AT TIME ZONE 'Asia/Jakarta'))
              AND (now() AT TIME ZONE 'Asia/Jakarta')::time <= s.jam_selesai
              AND NOT EXISTS (SELECT 1 FROM class_sessions cs WHERE cs.schedule_id=s.id
               AND cs.tanggal=(now() AT TIME ZONE 'Asia/Jakarta')::date
               AND cs.status::text IN ('selesai','batal'))
              AND (CASE WHEN %s='tutor' THEN s.tutor_id=%s
                  ELSE EXISTS (SELECT 1 FROM enrollments e WHERE e.program_id=s.program_id
                    AND e.student_id=%s AND e.status::text='aktif') END)
            ON CONFLICT DO NOTHING;
        ''', (role, user_id, user_id, user_id, role, user_id, user_id))
        if role == 'tutor':
            # Status dihitung dari tanggal-tanggal jadwal sejak pemasangan N2;
            # bukan otomatis menganggap pertemuan telah terlaksana.
            cur.execute('''
                SELECT s.id AS schedule_id, p.nama AS program,
                  COUNT(*)::int AS tertunda, min(d.hari)::date AS sejak
                FROM schedules s JOIN programs p ON p.id=s.program_id
                JOIN LATERAL generate_series(
                  (s.notif_monitor_from AT TIME ZONE 'Asia/Jakarta')::date,
                  (now() AT TIME ZONE 'Asia/Jakarta')::date, interval '1 day') AS d(hari) ON TRUE
                WHERE s.tutor_id=%s AND s.aktif=TRUE
                  AND CASE s.hari::text
                    WHEN 'senin' THEN 1 WHEN 'selasa' THEN 2 WHEN 'rabu' THEN 3
                    WHEN 'kamis' THEN 4 WHEN 'jumat' THEN 5 WHEN 'sabtu' THEN 6 ELSE 7 END
                    = EXTRACT(ISODOW FROM d.hari)
                  AND (d.hari::date+s.jam_mulai) AT TIME ZONE 'Asia/Jakarta' >= s.notif_monitor_from
                  AND (d.hari::date+s.jam_selesai) AT TIME ZONE 'Asia/Jakarta' < now()
                  AND EXISTS (SELECT 1 FROM enrollments e
                    WHERE e.program_id=s.program_id AND e.status::text='aktif'
                    AND COALESCE(e.processed_at::date,e.created_at::date)<=d.hari::date)
                  AND NOT EXISTS (SELECT 1 FROM class_sessions cs
                    WHERE cs.schedule_id=s.id AND cs.tanggal=d.hari::date
                      AND cs.status::text IN ('selesai','batal'))
                GROUP BY s.id,p.nama;
            ''', (user_id,))
            pending = {int(x['schedule_id']): x for x in cur.fetchall()}
            cur.execute('''SELECT id,related_id FROM announcements
              WHERE penerima_user_id=%s AND sumber='sistem' AND related_type='schedule_pending'
                AND (expires_at IS NULL OR expires_at>now()) FOR UPDATE''', (user_id,))
            active = {int(x['related_id']): int(x['id']) for x in cur.fetchall()}
            for schedule_id, row in pending.items():
                isi = (f"{row['program']}: {row['tertunda']} pertemuan dijadwalkan belum memiliki "
                       f"laporan selesai atau pembatalan sejak {row['sejak']}. "
                       "Periksa Kelola Pertemuan. Ini bukan bukti kelas tidak berlangsung.")
                if schedule_id in active:
                    cur.execute('UPDATE announcements SET isi=%s WHERE id=%s',
                                (isi, active[schedule_id]))
                else:
                    cur.execute('''
                      INSERT INTO announcements
                        (judul,isi,dibuat_by,penerima_user_id,sumber,kategori,event_key,related_type,related_id)
                      VALUES ('Pertemuan Belum Dilaporkan',%s,%s,%s,'sistem','pengingat',%s,
                              'schedule_pending',%s) ON CONFLICT DO NOTHING;
                    ''', (isi,user_id,user_id,f'n2:pending:{schedule_id}:'+datetime.now(ZoneInfo('Asia/Jakarta')).date().isoformat() ,schedule_id))
            for schedule_id, item_id in active.items():
                if schedule_id not in pending:
                    cur.execute('UPDATE announcements SET expires_at=now() WHERE id=%s', (item_id,))
        conn.commit()


def daftar_pertemuan_tertunda(tutor_id: int, limit: int = 200) -> list[dict]:
    """Jadwal lewat sejak N2, termasuk tanggal yang belum punya class_sessions."""
    if type(tutor_id) is not int or tutor_id <= 0 or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('Tutor / limit tidak valid.')
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('''
          SELECT s.id AS schedule_id,p.nama AS nama_program,
            d.hari::date AS tanggal,cs.id AS session_id,
            cs.status::text AS status_pertemuan,s.jam_mulai,s.jam_selesai
          FROM schedules s JOIN programs p ON p.id=s.program_id
          CROSS JOIN LATERAL generate_series(
            (s.notif_monitor_from AT TIME ZONE 'Asia/Jakarta')::date,
            (now() AT TIME ZONE 'Asia/Jakarta')::date,interval '1 day') AS d(hari)
          LEFT JOIN class_sessions cs ON cs.schedule_id=s.id AND cs.tanggal=d.hari::date
          WHERE s.tutor_id=%s AND s.aktif=TRUE
            AND CASE s.hari::text WHEN 'senin' THEN 1 WHEN 'selasa' THEN 2
              WHEN 'rabu' THEN 3 WHEN 'kamis' THEN 4 WHEN 'jumat' THEN 5
              WHEN 'sabtu' THEN 6 ELSE 7 END=EXTRACT(ISODOW FROM d.hari)
            AND (d.hari::date+s.jam_mulai) AT TIME ZONE 'Asia/Jakarta'>=s.notif_monitor_from
            AND (d.hari::date+s.jam_selesai) AT TIME ZONE 'Asia/Jakarta'<now()
            AND EXISTS(SELECT 1 FROM enrollments e
              WHERE e.program_id=s.program_id AND e.status::text='aktif'
                AND COALESCE(e.processed_at::date,e.created_at::date)<=d.hari::date)
            AND (cs.id IS NULL OR cs.status::text NOT IN ('selesai','batal'))
          ORDER BY d.hari DESC,s.jam_mulai,s.id LIMIT %s;
        ''',(tutor_id,limit))
        return cur.fetchall()


def buka_pertemuan_terlewat(tutor_id: int, schedule_id: int, tanggal) -> int:
    """Buat catatan untuk tanggal jadwal lampau; bukan otomatis menyatakan kelas berlangsung."""
    from datetime import date
    if any(type(x) is not int or x<1 for x in (tutor_id,schedule_id)) or type(tanggal) is not date:
        raise ValueError('Identitas pertemuan tidak valid.')
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        # Kunci per jadwal agar 2 pembukaan berbarengan tidak membuat nomor sama.
        cur.execute('SELECT pg_advisory_xact_lock(9202,%s);',(schedule_id,))
        cur.execute('''SELECT s.id,s.program_id,s.hari::text AS hari,s.jam_mulai,s.jam_selesai,
                          s.notif_monitor_from
                 FROM schedules s WHERE s.id=%s AND s.tutor_id=%s AND s.aktif=TRUE''',
                    (schedule_id,tutor_id))
        row=cur.fetchone()
        if not row:
            raise PermissionError('Jadwal bukan milik Tutor aktif ini.')
        local_start=datetime.combine(tanggal,row['jam_mulai'],tzinfo=ZoneInfo('Asia/Jakarta'))
        local_end=datetime.combine(tanggal,row['jam_selesai'],tzinfo=ZoneInfo('Asia/Jakarta'))
        now=datetime.now(ZoneInfo('Asia/Jakarta'))
        days=('senin','selasa','rabu','kamis','jumat','sabtu','minggu')
        if tanggal.weekday()>=7 or row['hari'] != days[tanggal.weekday()] or \
           local_start < row['notif_monitor_from'].astimezone(ZoneInfo('Asia/Jakarta')) or local_end >= now:
            raise ValueError('Tanggal bukan jadwal terlewat sejak pemasangan N2.')
        cur.execute('''SELECT EXISTS(SELECT 1 FROM enrollments e WHERE e.program_id=%s
            AND e.status::text='aktif'
            AND COALESCE(e.processed_at::date,e.created_at::date)<=%s::date) AS ada''',
                    (row['program_id'],tanggal))
        if not cur.fetchone()['ada']:
            raise ValueError('Tidak ada peserta aktif yang sah untuk tanggal ini.')
        cur.execute('SELECT id,status::text AS status FROM class_sessions WHERE schedule_id=%s AND tanggal=%s;',
                    (schedule_id,tanggal))
        existing=cur.fetchone()
        if existing:
            if existing['status'] in ('selesai','batal'):
                raise ValueError('Pertemuan sudah selesai / batal.')
            conn.commit();return existing['id']
        cur.execute('SELECT COALESCE(MAX(pertemuan_ke),0)+1 AS next FROM class_sessions WHERE schedule_id=%s',
                    (schedule_id,))
        no=cur.fetchone()['next']
        cur.execute('''INSERT INTO class_sessions (schedule_id,tanggal,pertemuan_ke)
              VALUES (%s,%s,%s) RETURNING id;''',(schedule_id,tanggal,no))
        new_id=cur.fetchone()['id']
        cur.execute('''INSERT INTO activity_logs(user_id,aksi,detail)
          VALUES (%s,'PERTEMUAN_TERLAMBAT_DIBUKA',%s)''',
          (tutor_id,f'session_id={new_id}; schedule_id={schedule_id}; tanggal={tanggal.isoformat()}'))
        conn.commit()
        return new_id
