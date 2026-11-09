"""Patch 5D: bounded, read-only Admin audit/history queries.

Only invoked inside AIReadRepository's active-role checked READ ONLY transaction.
Never expose free-form activity_logs.detail because older log entries may contain
credentials, emails, OTP material, or attacker-supplied instructions.
"""
from __future__ import annotations

import re

from app.services.ai_history_plan import _decode_cursor, make_cursor

# Date filters are local Jakarta dates, with a half-open next-day upper bound.
# All SQL fragments here are constants. User/model values are always parameters.
_LOG_FILTER = """
    WHERE (%s::date IS NULL OR l.created_at >= (%s::date AT TIME ZONE 'Asia/Jakarta'))
      AND (%s::date IS NULL OR l.created_at < ((%s::date + 1) AT TIME ZONE 'Asia/Jakarta'))
      AND (%s::text IS NULL OR l.aksi = %s::text)
      AND (%s::int IS NULL OR l.user_id = %s::int)
"""
_LOG_COUNT = "SELECT COUNT(*)::bigint AS total_hasil FROM activity_logs l " + _LOG_FILTER
_LOG_PAGE = """
    SELECT l.id, l.user_id AS pelaku_user_id,
           COALESCE(u.nama_lengkap, u.username,
                    CASE WHEN l.user_id IS NULL THEN 'Sistem' ELSE 'Akun tidak tersedia' END) AS pelaku,
           l.aksi, l.created_at AS waktu
    FROM activity_logs l LEFT JOIN users u ON u.id=l.user_id
""" + _LOG_FILTER + """
    AND (%s::timestamptz IS NULL OR (l.created_at, l.id) < (%s::timestamptz, %s::bigint))
    ORDER BY l.created_at DESC, l.id DESC LIMIT %s
"""

# Status columns are CURRENT snapshots, NOT past status at each event timestamp.
# Every row is linked through real foreign keys; no search in free-text logs.
_TIMELINE_EVENTS = """
    WITH events AS (
        SELECT u.created_at AS waktu, 0 AS urut, u.id::bigint AS entity_id,
               'users'::text AS sumber_tabel, 'akun_dibuat'::text AS jenis_peristiwa,
               u.status::text AS status_terkini, NULL::text AS program
        FROM users u WHERE u.id=%s
        UNION ALL
        SELECT u.approved_at, 1, u.id::bigint, 'users', 'akun_disetujui',
               u.status::text, NULL::text
        FROM users u WHERE u.id=%s AND u.approved_at IS NOT NULL
        UNION ALL
        SELECT e.created_at, 2, e.id::bigint, 'enrollments', 'pendaftaran_dibuat',
               e.status::text, p.nama::text
        FROM enrollments e JOIN programs p ON p.id=e.program_id WHERE e.student_id=%s
        UNION ALL
        SELECT e.processed_at, 3, e.id::bigint, 'enrollments', 'pendaftaran_diproses',
               e.status::text, p.nama::text
        FROM enrollments e JOIN programs p ON p.id=e.program_id
        WHERE e.student_id=%s AND e.processed_at IS NOT NULL
        UNION ALL
        SELECT i.created_at, 4, i.id::bigint, 'invoices', 'tagihan_dibuat',
               i.status::text, p.nama::text
        FROM invoices i JOIN enrollments e ON e.id=i.enrollment_id
        JOIN programs p ON p.id=e.program_id WHERE e.student_id=%s
        UNION ALL
        SELECT pay.created_at, 5, pay.id::bigint, 'payments', 'pembayaran_diajukan',
               pay.status::text, p.nama::text
        FROM payments pay JOIN invoices i ON i.id=pay.invoice_id
        JOIN enrollments e ON e.id=i.enrollment_id JOIN programs p ON p.id=e.program_id
        WHERE e.student_id=%s
        UNION ALL
        SELECT pay.paid_at, 6, pay.id::bigint, 'payments', 'waktu_bayar_tercatat',
               pay.status::text, p.nama::text
        FROM payments pay JOIN invoices i ON i.id=pay.invoice_id
        JOIN enrollments e ON e.id=i.enrollment_id JOIN programs p ON p.id=e.program_id
        WHERE e.student_id=%s AND pay.paid_at IS NOT NULL
    )
"""
_TIMELINE_FILTER = """
    WHERE (%s::date IS NULL OR ev.waktu >= (%s::date AT TIME ZONE 'Asia/Jakarta'))
      AND (%s::date IS NULL OR ev.waktu < ((%s::date + 1) AT TIME ZONE 'Asia/Jakarta'))
"""
_TIMELINE_COUNT = _TIMELINE_EVENTS + "SELECT COUNT(*)::bigint AS total_hasil FROM events ev " + _TIMELINE_FILTER
_TIMELINE_PAGE = _TIMELINE_EVENTS + """
    SELECT ev.waktu, ev.urut, ev.entity_id, ev.sumber_tabel, ev.jenis_peristiwa,
           ev.status_terkini, ev.program
    FROM events ev
""" + _TIMELINE_FILTER + """
      AND (%s::timestamptz IS NULL OR (ev.waktu, ev.urut, ev.entity_id) <
           (%s::timestamptz, %s::int, %s::bigint))
    ORDER BY ev.waktu DESC, ev.urut DESC, ev.entity_id DESC LIMIT %s
"""

# Grouping choice only selects one trusted SQL expression; it is never SQL input.
_GROUP_EXPRESSIONS = {
    "aksi": "l.aksi",
    "pelaku": "l.user_id",
    "hari": "(l.created_at AT TIME ZONE 'Asia/Jakarta')::date",
}


def _date_args(args: dict) -> tuple:
    return (args.get("tanggal_dari"),) * 2 + (args.get("tanggal_sampai"),) * 2


def _log_args(args: dict, target_user: int | None) -> tuple:
    return _date_args(args) + (args.get("aksi"),) * 2 + (target_user,) * 2


def _row(row: dict) -> dict:
    # This is deliberately a strict whitelist: never forward detail/raw SQL.
    def display(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if isinstance(value, str):
            # Do not carry raw terminal control bytes or oversized log labels.
            return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", value)[:120]
        return value
    return {key: display(value)
            for key, value in row.items() if key in {
                "id", "pelaku_user_id", "pelaku", "aksi", "waktu", "entity_id",
                "sumber_tabel", "jenis_peristiwa", "status_terkini", "program", "jumlah", "kelompok"
            }}


def _logged_history(cur, name: str, args: dict) -> dict:
    target = args["user_id"] if name == "admin_user_activity" else None
    params = _log_args(args, target)
    cur.execute(_LOG_COUNT, params)
    count = int((cur.fetchone() or {}).get("total_hasil") or 0)
    cursor = _decode_cursor(args["cursor"], timeline=False) if args.get("cursor") else None
    cur.execute(_LOG_PAGE, params + (
        cursor[0] if cursor else None,
        cursor[0] if cursor else None,
        cursor[1] if cursor else None,
        args["limit"] + 1,
    ))
    rows = cur.fetchmany(args["limit"] + 1)
    clipped = rows[:args["limit"]]
    more = len(rows) > args["limit"]
    return {
        "data": [_row(x) for x in clipped], "total_hasil": count,
        "jumlah_ditampilkan": len(clipped), "terpotong": more,
        "next_cursor": make_cursor(clipped[-1]["waktu"], clipped[-1]["id"]) if more and clipped else None,
        "sumber": "PostgreSQL.activity_logs", "zona_waktu": "Asia/Jakarta",
        "basis": ("user_id log adalah pelaku aktivitas (bukan subjek yang diubah). "
                  "Detail bebas log sengaja tidak diberikan karena bisa memuat informasi rahasia."),
    }


def _timeline(cur, args: dict) -> dict:
    user_id = args["user_id"]
    cur.execute("SELECT id FROM users WHERE id=%s", (user_id,))
    if not cur.fetchone():
        raise ValueError("Pengguna target tidak ditemukan.")
    params = (user_id,) * 7 + _date_args(args)
    cur.execute(_TIMELINE_COUNT, params)
    count = int((cur.fetchone() or {}).get("total_hasil") or 0)
    cursor = _decode_cursor(args["cursor"], timeline=True) if args.get("cursor") else None
    cur.execute(_TIMELINE_PAGE, params + (
        cursor[0] if cursor else None,
        cursor[0] if cursor else None,
        cursor[1] if cursor else None,
        cursor[2] if cursor else None,
        args["limit"] + 1,
    ))
    rows = cur.fetchmany(args["limit"] + 1)
    clipped = rows[:args["limit"]]
    more = len(rows) > args["limit"]
    return {
        "data": [_row(x) for x in clipped], "total_hasil": count,
        "jumlah_ditampilkan": len(clipped), "terpotong": more,
        "next_cursor": make_cursor(clipped[-1]["waktu"], clipped[-1]["entity_id"], seq=clipped[-1]["urut"])
                       if more and clipped else None,
        "sumber": "PostgreSQL.users,enrollments,invoices,payments", "zona_waktu": "Asia/Jakarta",
        "basis": "Waktu kejadian berasal dari kolom tercatat; status_terkini adalah status SEKARANG, "
                 "bukan status saat kejadian. Data ini tidak mencakup perubahan yang tidak pernah dicatat.",
    }


def _analytics(cur, args: dict) -> dict:
    dates_and_action = _log_args(args, None)
    cur.execute(_LOG_COUNT, dates_and_action)
    count = int((cur.fetchone() or {}).get("total_hasil") or 0)
    expr = _GROUP_EXPRESSIONS[args["kelompok"]]
    # Group on account ID (not display name), so duplicate names stay separate.
    if args["kelompok"] == "pelaku":
        grouped = f"""
            SELECT l.user_id AS pelaku_user_id,
                   COALESCE(u.nama_lengkap, u.username,
                       CASE WHEN l.user_id IS NULL THEN 'Sistem' ELSE 'Akun tidak tersedia' END) AS kelompok,
                   COUNT(*)::bigint AS jumlah
            FROM activity_logs l LEFT JOIN users u ON u.id=l.user_id
            {_LOG_FILTER}
            GROUP BY l.user_id, u.nama_lengkap, u.username
        """
    else:
        grouped = f"""
            SELECT {expr} AS kelompok, COUNT(*)::bigint AS jumlah
            FROM activity_logs l
            {_LOG_FILTER}
            GROUP BY {expr}
        """
    cur.execute("SELECT COUNT(*)::bigint AS banyak_kelompok FROM (" + grouped + ") t", dates_and_action)
    groups = int((cur.fetchone() or {}).get("banyak_kelompok") or 0)
    cur.execute(grouped + " ORDER BY jumlah DESC, kelompok LIMIT 20", dates_and_action)
    rows = cur.fetchmany(20)
    return {
        "data": [_row(x) for x in rows], "total_hasil": count,
        "total_kelompok": groups, "jumlah_ditampilkan": len(rows), "terpotong": groups > len(rows),
        "sumber": "PostgreSQL.activity_logs", "zona_waktu": "Asia/Jakarta",
        "basis": "Total adalah seluruh baris log pada filter; kelompok dibatasi 20 teratas. "
                 "Grouping pelaku berdasarkan user_id; nama sama tidak digabung.",
    }


def execute_history(cur, role: str, name: str, args: dict) -> dict:
    """Requires an already-validated principal/transaction from caller."""
    if role != "admin":
        raise PermissionError("Histori global hanya untuk Admin.")
    if name in ("admin_system_history", "admin_user_activity"):
        return _logged_history(cur, name, args)
    if name == "admin_user_timeline":
        return _timeline(cur, args)
    if name == "admin_history_analytics":
        return _analytics(cur, args)
    raise PermissionError("Fungsi histori tidak tersedia.")
