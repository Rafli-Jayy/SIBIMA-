"""Compile allowlisted analytic plans, never SQL supplied by the model.

Uses AIReadRepository's authenticated READ ONLY transaction. Pure SQL compiler
is testable offline; all values go through psycopg parameters.
"""
from __future__ import annotations
from datetime import date, datetime, time
from decimal import Decimal

from app.services.ai_dynamic_plan import DOMAINS, MAX_GROUPS, validate_role_dynamic_plan
from app.repositories.class_access_sql import AKSES_TERKUNCI_SQL, ENROLLMENT_TERAKHIR_TERSEDIA_SQL


def compile_query(plan: dict, *, role: str = "admin", user_id: int | None = None) -> tuple[str, tuple, str, str, tuple]:
    """Return total SQL + group SQL fragments. ONLY registry fragments interpolate."""
    spec = DOMAINS[plan["domain"]]
    metrics = spec["metrics"]
    agg = metrics[plan["metrik"]]
    conditions = [spec["fixed_where"]] if spec.get("fixed_where") else []
    params: list = []
    source_from = spec["from"]
    if role != "admin":
        if type(user_id) is not int or user_id <= 0:
            raise PermissionError("Identitas sesi analitik tidak sah.")
        if role == "tutor":
            if plan["domain"] == "pendaftaran":
                conditions.extend([
                    "e.status='aktif'",
                    "EXISTS (SELECT 1 FROM schedules own_s WHERE own_s.program_id=e.program_id AND own_s.tutor_id=%s AND own_s.aktif=TRUE)",
                    "EXISTS (SELECT 1 FROM users own_u WHERE own_u.id=e.student_id AND own_u.role='siswa' AND own_u.status='aktif')",
                ])
            elif plan["domain"] == "jadwal":
                conditions.append("s.tutor_id=%s")
            elif plan["domain"] == "kehadiran":
                conditions.extend([
                    "s.tutor_id=%s", "s.aktif=TRUE",
                    "EXISTS (SELECT 1 FROM enrollments own_e JOIN users own_u ON own_u.id=own_e.student_id "
                    "WHERE own_e.id=a.enrollment_id AND own_e.student_id=a.student_id "
                    "AND own_e.program_id=s.program_id AND own_e.status='aktif' AND own_u.status='aktif')",
                ])
            else:
                raise PermissionError("Domain tidak tersedia untuk Tutor.")
        elif role == "siswa":
            if plan["domain"] == "kehadiran":
                source_from += (" JOIN enrollments e ON e.id=a.enrollment_id "
                                "AND e.student_id=a.student_id AND e.program_id=s.program_id")
                conditions.extend(["e.student_id=%s", ENROLLMENT_TERAKHIR_TERSEDIA_SQL,
                                   f"NOT {AKSES_TERKUNCI_SQL}", "cs.tanggal>=e.created_at::date"])
            elif plan["domain"] == "nilai":
                conditions.extend(["e.student_id=%s", ENROLLMENT_TERAKHIR_TERSEDIA_SQL,
                                   f"NOT {AKSES_TERKUNCI_SQL}"])
            elif plan["domain"] in {"pendaftaran", "tagihan", "pembayaran"}:
                conditions.append("e.student_id=%s")
            else:
                raise PermissionError("Domain tidak tersedia untuk Siswa.")
        else:
            raise PermissionError("Role tidak dikenal.")
        params.append(user_id)
    fixed_status = spec.get("fixed_status", {}).get(plan["metrik"])
    if fixed_status:
        conditions.append(f"{spec['status']} = %s")
        params.append(fixed_status)
    filt = plan["filter"]
    if "program_id" in filt:
        conditions.append("p.id = %s")
        params.append(filt["program_id"])
    if "status" in filt and not fixed_status:
        conditions.append(f"{spec['status']} = %s")
        params.append(filt["status"])
    if "tanggal_dari" in filt:
        conditions.append(f"{spec['date']} >= %s::date")
        params.append(filt["tanggal_dari"])
    if "tanggal_sampai" in filt:
        conditions.append(f"{spec['date']} <= %s::date")
        params.append(filt["tanggal_sampai"])
    source = source_from + (" WHERE " + " AND ".join(f"({c})" for c in conditions) if conditions else "")
    total_sql = f"SELECT {agg} AS nilai {source}"
    selected: list[tuple[str, str]] = []
    for dimension in plan["kelompok"]:
        selected.extend(spec["dimensions"][dimension])
    # No duplicate SQL columns / aliases allowed across dimensions in a single domain.
    expressions = [expr for expr, _ in selected]
    names = [alias for _, alias in selected]
    if len(set(expressions)) != len(expressions) or len(set(names)) != len(names):
        raise ValueError("Duplikasi dimensi analitik.")
    if expressions:
        grouped = ", ".join(expressions)
        fields = ", ".join(f"{expr} AS {alias}" for expr, alias in selected)
        grouped_source = f"{source} GROUP BY {grouped}"
        count_sql = f"SELECT COUNT(*)::int AS banyak_kelompok FROM (SELECT 1 {grouped_source}) AS grup"
        if plan["urut"] == "dimensi_naik":
            order_sql = ", ".join(f"{alias} ASC NULLS LAST" for alias in names)
        else:
            dir_sql = "DESC" if plan["urut"] == "nilai_terbesar" else "ASC"
            order_sql = f"nilai {dir_sql} NULLS LAST, " + ", ".join(f"{alias} ASC NULLS LAST" for alias in names)
        list_sql = f"SELECT {fields}, {agg} AS nilai {grouped_source} ORDER BY {order_sql} LIMIT {MAX_GROUPS}"
    else:
        count_sql = ""
        list_sql = ""
    return total_sql, tuple(params), count_sql, list_sql, tuple(params)


def _serialized(value):
    if isinstance(value, (Decimal, date, datetime, time)):
        return str(value)
    if isinstance(value, dict):
        return {k: _serialized(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialized(v) for v in value]
    return value


def execute_dynamic(cur, role: str, args: object, user_id: int | None = None) -> dict:
    """Run one global aggregate + up to 20 groups in the authenticated txn."""
    plan = validate_role_dynamic_plan(args, role)
    total_sql, params, group_count_sql, group_sql, group_params = compile_query(plan, role=role, user_id=user_id)
    cur.execute(total_sql, params)
    total_row = cur.fetchone() or {}
    all_value = _serialized(total_row.get("nilai"))
    rows: list = []
    group_count = 1
    if group_count_sql:
        cur.execute(group_count_sql, group_params)
        group_count = int((cur.fetchone() or {}).get("banyak_kelompok") or 0)
        cur.execute(group_sql, group_params)
        rows = _serialized(cur.fetchmany(MAX_GROUPS))
    return {
        "data": rows if group_sql else [{"nilai": all_value}],
        "agregat_global": all_value,
        "total_kelompok": group_count,
        "jumlah_ditampilkan": len(rows) if group_sql else 1,
        "terpotong": group_count > len(rows) if group_sql else False,
        "rencana": plan,
        "cakupan": ("Semua data yang sesuai filter Admin" if role == "admin" else
                    "Hanya program yang diampu Tutor login, dengan peserta aktif" if role == "tutor" else
                    "Hanya data siswa login; nilai dan absensi tunduk pada kontrol akses kelas"),
        "definisi": DOMAINS[plan["domain"]]["definisi"],
        "sumber": "PostgreSQL SIBIMA; query terparameterisasi READ ONLY",
        "timezone": "Asia/Jakarta",
        "catatan": "Agregat global dihitung dari semua baris yang cocok. COUNT DISTINCT dan AVG per kelompok tidak harus bisa dijumlahkan untuk memperoleh total global.",
    }
