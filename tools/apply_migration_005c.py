"""Migrasi PATCH-005C: ubah UNIQUE enrollment menjadi UNIQUE pendaftaran berjalan.

Penggunaan dari root SIBIMA:
  python tools/apply_migration_005c.py --check
  python tools/apply_migration_005c.py --apply

Tidak mengubah data siswa, pembayaran, invoice, atau refund.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _migration_statements():
    path = ROOT / 'sql' / 'migrations' / '20261101_patch_005c_daftar_ulang.sql'
    raw = path.read_text(encoding='utf-8')
    statements = [s.strip() for s in '\n'.join(line for line in raw.splitlines() if not line.lstrip().startswith('--')).split(';') if s.strip()]
    if len(statements) != 2 or not statements[0].upper().startswith('CREATE UNIQUE INDEX') or not statements[1].upper().startswith('ALTER TABLE ENROLLMENTS DROP CONSTRAINT'):
        raise RuntimeError('Isi migrasi tidak sesuai yang diharapkan. Jangan jalankan.')
    return statements


def main(argv=None):
    parser = argparse.ArgumentParser(description='Migrasi SIBIMA PATCH-005C: daftar ulang setelah pembatalan.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true', help='Periksa database tanpa mengubah apa pun.')
    group.add_argument('--apply', action='store_true', help='Jalankan migrasi setelah konfirmasi.')
    args = parser.parse_args(argv)

    try:
        import psycopg
        from app.config import DB_CONFIG
    except ImportError as exc:
        print(f'Dependensi belum tersedia: {exc}. Aktifkan venv dan install requirements.txt.')
        return 1
    dbname = DB_CONFIG.get('dbname')
    if not dbname:
        print('DB_NAME belum diatur di .env. Tidak ada perubahan.')
        return 1

    try:
        # Autocommit + conn.transaction membuat kedua DDL atomik saat --apply.
        with psycopg.connect(**DB_CONFIG, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database()')
                db_actual = cur.fetchone()[0]
                if db_actual != dbname:
                    print('Nama database aktif tidak sama dengan DB_NAME. Migrasi ditolak.')
                    return 1
                cur.execute('''
                    SELECT COUNT(*) FROM (
                        SELECT 1 FROM enrollments
                        WHERE status IN ('menunggu_pembayaran', 'menunggu', 'aktif')
                        GROUP BY student_id, program_id
                        HAVING COUNT(*) > 1
                    ) duplicate_groups
                ''')
                conflicts = cur.fetchone()[0]
                cur.execute('''
                    SELECT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conrelid = 'enrollments'::regclass
                          AND conname = 'uq_enrollment'
                    )
                ''')
                old_constraint = cur.fetchone()[0]
                cur.execute('''
                    SELECT indexdef FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename = 'enrollments'
                      AND indexname = 'uq_enrollment_berjalan'
                ''')
                index_row = cur.fetchone()
                if index_row:
                    index_def = index_row[0].lower()
                    if not all(x in index_def for x in ('unique index', 'student_id', 'program_id', 'menunggu_pembayaran', 'menunggu', 'aktif')):
                        print('Indeks uq_enrollment_berjalan sudah ada dengan definisi berbeda. Migrasi dihentikan.')
                        return 1

                print(f'Database: {db_actual}')
                print(f'Constraint unik lama: {"ada" if old_constraint else "tidak ada"}')
                print(f'Indeks aktif baru: {"ada" if index_row else "belum ada"}')
                print(f'Konflik pendaftaran berjalan: {conflicts}')
                if conflicts:
                    print('Ada duplikasi aktif. Migrasi ditolak agar data tetap aman.')
                    return 1
                if args.check:
                    print('Pengecekan selesai. Tidak ada data yang diubah.')
                    return 0
                if index_row and not old_constraint:
                    print('Migrasi PATCH-005C sudah terpasang. Tidak ada perubahan.')
                    return 0
                if input(f'Untuk mengubah constraint pada database {db_actual}, ketik nama database persis: ').strip() != db_actual:
                    print('Dibatalkan. Tidak ada perubahan database.')
                    return 1
                statements = _migration_statements()
                with conn.transaction():
                    cur.execute("SET LOCAL lock_timeout = '5s'")
                    for statement in statements:
                        cur.execute(statement)
                print('MIGRASI PATCH-005C BERHASIL. Riwayat pendaftaran tetap tersimpan.')
                return 0
    except (OSError, Exception) as exc:
        # Tidak mencetak repr exception untuk menghindari kredensial dalam string koneksi.
        print(f'Migrasi belum diterapkan: {type(exc).__name__}. Cek hak ALTER TABLE, koneksi, dan status PostgreSQL.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
