"""Migrasi tambahan status pertemuan; tidak menghapus laporan/absensi lama.

Dari folder utama SIBIMA:
    python tools/apply_migration_005e3b.py --check
    python tools/apply_migration_005e3b.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Migrasi PATCH-005E3-B: status sesi tutor.')
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--check', action='store_true')
    flags.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        import psycopg
        from app.config import DB_CONFIG
    except ImportError as exc:
        print(f'Dependensi belum tersedia: {type(exc).__name__}. Aktifkan venv.')
        return 1
    expected = DB_CONFIG.get('dbname')
    if not expected:
        print('DB_NAME belum diatur. Tidak ada perubahan.')
        return 1
    try:
        with psycopg.connect(**DB_CONFIG, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database()')
                actual = cur.fetchone()[0]
                if actual != expected:
                    print('Database aktif berbeda dari DB_NAME. Dihentikan.')
                    return 1
                cur.execute("""
                    SELECT e.enumlabel FROM pg_enum e
                    JOIN pg_type t ON t.oid = e.enumtypid
                    WHERE t.typname = 'session_status';
                """)
                enum_labels = {r[0] for r in cur.fetchall()}
                cur.execute("""
                    SELECT column_name, data_type, character_maximum_length
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'class_sessions'
                      AND column_name IN ('alasan_batal', 'selesai_at');
                """)
                columns = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
                if not {'terlaksana', 'batal'} <= enum_labels:
                    print('Tipe session_status tidak sesuai baseline SIBIMA. Dihentikan.')
                    return 1
                if 'alasan_batal' in columns and columns['alasan_batal'] != ('character varying', 500):
                    print('Kolom alasan_batal sudah ada tetapi tipenya berbeda. Dihentikan.')
                    return 1
                if 'selesai_at' in columns and columns['selesai_at'][0] != 'timestamp with time zone':
                    print('Kolom selesai_at ada dengan tipe berbeda. Dihentikan.')
                    return 1
                cur.execute("""
                    SELECT column_default FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'class_sessions' AND column_name = 'status';
                """)
                row = cur.fetchone()
                if not row:
                    print('Tabel class_sessions tidak ditemukan. Dihentikan.')
                    return 1
                current_default = row[0] or ''
                installed = ({'perlu_laporan', 'selesai'} <= enum_labels
                             and 'alasan_batal' in columns and 'selesai_at' in columns
                             and 'perlu_laporan' in current_default)
                print(f'Database: {actual}')
                print(f'Nilai enum: {", ".join(sorted(enum_labels))}')
                print(f'Kolom alasan_batal: {"ada" if "alasan_batal" in columns else "belum ada"}')
                print(f'Kolom selesai_at: {"ada" if "selesai_at" in columns else "belum ada"}')
                print(f'Default status: {current_default}')
                if args.check:
                    print('Pengecekan selesai. Tidak ada perubahan.')
                    return 0
                if installed:
                    print('Migrasi PATCH-005E3-B sudah terpasang. Tidak ada perubahan.')
                    return 0
                if input(f'Ketik nama database {actual} untuk konfirmasi migrasi: ').strip() != actual:
                    print('Dibatalkan. Tidak ada perubahan.')
                    return 1
                # PostgreSQL melarang penggunaan enum baru dalam transaksi yang
                # sama sebelum ADD VALUE di-commit. Dua tahap ini disengaja.
                with conn.transaction():
                    cur.execute("SET LOCAL lock_timeout = '5s'")
                    cur.execute("ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'perlu_laporan'")
                    cur.execute("ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'selesai'")
                with conn.transaction():
                    cur.execute("SET LOCAL lock_timeout = '5s'")
                    cur.execute('ALTER TABLE class_sessions ADD COLUMN IF NOT EXISTS alasan_batal VARCHAR(500)')
                    cur.execute('ALTER TABLE class_sessions ADD COLUMN IF NOT EXISTS selesai_at TIMESTAMPTZ')
                    cur.execute("ALTER TABLE class_sessions ALTER COLUMN status SET DEFAULT 'perlu_laporan'::session_status")
                print('MIGRASI PATCH-005E3-B BERHASIL. Status historis tidak diubah.')
                return 0
    except Exception as exc:
        print(f'Migrasi tidak selesai: {type(exc).__name__}. Periksa hak ALTER, database, dan koneksi.')
        print('Jika enum sudah bertambah tetapi tabel belum selesai, jalankan --check lalu --apply lagi.')
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
