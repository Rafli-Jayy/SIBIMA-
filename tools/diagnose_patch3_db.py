"""Patch 3 preflight. SQL parsing and permissions only; no user records returned.
Run: python -u tools/diagnose_patch3_db.py
"""
from pathlib import Path
import os, re, sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def clean_error(exc):
    kind = type(exc).__name__
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,63}", kind):
        kind = "Error"
    state = getattr(exc, "sqlstate", None)
    return f"{kind}" + (f" / SQLSTATE {state}" if isinstance(state, str) and re.fullmatch(r"[A-Z0-9]{5}", state) else "")


def test():
    from app.db import pool
    from app.repositories.ai_read_repo import QUERIES

    print("=== PREFLIGHT POSTGRESQL PATCH 3 (READ-ONLY) ===", flush=True)
    print("Tidak membaca baris data, tidak mengirim permintaan Gemini.", flush=True)
    params = {
        "get_admin_overview": (),
        "list_unpaid_invoices": (False,),
        "get_my_teaching_schedule": (0,),
        "list_my_class_students": (None, None, 0),
        "get_my_class_attendance": (0, None, None),
        "get_my_schedule": (0,),
        "get_my_grades": (0, None, None),
        "get_my_attendance": (0, None, None),
        "get_my_invoices": (0,),
        "get_my_payments": (0,),
    }
    with pool.connection(timeout=8) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout = '5000ms'")
            print("Koneksi PostgreSQL: OK", flush=True)
            failures = 0
            for name, query in QUERIES.items():
                try:
                    # Nested transaction = SAVEPOINT: a failure cannot abort later checks.
                    with conn.transaction():
                        with conn.cursor() as cur:
                            cur.execute("EXPLAIN " + query, params[name])
                            # Only parse/plan; do not read or display query results.
                    print(f"{name}: OK", flush=True)
                except Exception as exc:
                    failures += 1
                    print(f"{name}: GAGAL ({clean_error(exc)})", flush=True)
    print(f"Pemeriksaan selesai. Gagal: {failures} dari {len(QUERIES)}.", flush=True)
    return failures

if __name__ == "__main__":
    try:
        sys.exit(1 if test() else 0)
    except Exception as exc:
        print("Koneksi/preflight gagal:", clean_error(exc), flush=True)
        sys.exit(1)
