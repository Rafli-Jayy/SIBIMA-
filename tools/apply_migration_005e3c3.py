"""PATCH-005E3-C3 — migrasi view kehadiran per enrollment secara konservatif.

    python tools/apply_migration_005e3c3.py --check
    python tools/apply_migration_005e3c3.py --apply

Tidak menulis/menautkan ulang catatan absensi, hanya CREATE OR REPLACE VIEW.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
MIGRATION = ROOT / 'sql/migrations/20261101_patch_005e3c3_rekap_kehadiran.sql'
LEGACY_COLUMNS = ('student_id', 'program_id', 'total_pertemuan', 'hadir',
                  'izin', 'sakit', 'alpa', 'persen_hadir')
ADDED_COLUMNS = ('enrollment_id', 'status_enrollment', 'tanggal_pendaftaran')


def _inspection(cur):
    cur.execute('SELECT current_database(), current_user;')
    database, active_user = cur.fetchone()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'attendances'
          AND column_name = 'enrollment_id';
    """)
    if not cur.fetchone():
        raise ValueError('Kolom attendances.enrollment_id belum ada; selesaikan PATCH-005E3-C2.')
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'v_rekap_kehadiran'
        ORDER BY ordinal_position;
    """)
    columns = tuple(row[0] for row in cur.fetchall())
    if columns not in (LEGACY_COLUMNS, LEGACY_COLUMNS + ADDED_COLUMNS):
        raise ValueError('Kolom view berbeda dari baseline yang didukung; tidak ditimpa.')
    cur.execute("""
        SELECT pg_get_userbyid(c.relowner), pg_get_viewdef(c.oid, true)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = current_schema() AND c.relname = 'v_rekap_kehadiran'
          AND c.relkind = 'v';
    """)
    row = cur.fetchone()
    if row is None:
        raise ValueError('View v_rekap_kehadiran tidak ditemukan.')
    owner, definition = row
    definition = ' '.join(definition.lower().split())
    if columns == LEGACY_COLUMNS + ADDED_COLUMNS:
        if ('enrollment_id' not in definition or 'status_enrollment' not in definition
                or 'a.enrollment_id' not in definition or 'cs.status' not in definition):
            raise ValueError('Definisi view yang telah dimigrasi berbeda; perlu tinjauan.')
    else:
        if ('attendances' not in definition or 'class_sessions' not in definition
                or 'group by' not in definition):
            raise ValueError('Definisi view lama berbeda; perlu tinjauan.')
    cur.execute('SELECT COUNT(*) FROM attendances WHERE enrollment_id IS NULL;')
    historical = cur.fetchone()[0]
    return dict(database=database, active_user=active_user, owner=owner,
                installed=columns == LEGACY_COLUMNS + ADDED_COLUMNS,
                historical=historical)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Pemeriksaan/migrasi view C3 SIBIMA')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        import psycopg
        from app.config import DB_CONFIG
    except ImportError:
        print('Aktifkan venv SIBIMA dan pastikan dependensi psycopg terpasang.')
        return 1
    expected = DB_CONFIG.get('dbname')
    if not expected:
        print('Nama database tidak tersedia di konfigurasi; dibatalkan.')
        return 1
    try:
        with psycopg.connect(**DB_CONFIG, autocommit=True) as conn:
            with conn.cursor() as cur:
                state = _inspection(cur)
                print(f"Database: {state['database']}")
                print(f"Pengguna DB: {state['active_user']}; pemilik view: {state['owner']}")
                print(f"Rekap per enrollment: {'sudah ada' if state['installed'] else 'belum ada'}")
                print(f"Absensi lama tanpa enrollment: {state['historical']}")
                if state['database'] != expected:
                    print('Database tidak cocok dengan konfigurasi; dibatalkan.')
                    return 1
                if args.check:
                    print('CHECK selesai. Database tidak berubah.')
                    return 0
                if state['installed']:
                    print('Migrasi sudah diterapkan; tidak ada perubahan.')
                    return 0
                print('Migrasi ini hanya memperbarui VIEW, bukan catatan absensi.')
                confirm = input(f'Ketik nama database {expected} untuk melanjutkan: ').strip()
                if confirm != expected:
                    print('Konfirmasi tidak sesuai; dibatalkan.')
                    return 1
                sql = MIGRATION.read_text(encoding='utf-8')
                with conn.transaction():
                    cur.execute("SET LOCAL lock_timeout = '5s';")
                    cur.execute(sql)
                after = _inspection(cur)
                if not after['installed'] or after['historical'] != state['historical']:
                    print('Verifikasi pasca-migrasi tidak sesuai; hentikan penggunaan laporan.')
                    return 1
                print('MIGRASI PATCH-005E3-C3 BERHASIL. Absensi historis tidak diubah.')
                return 0
    except Exception as exc:
        print(f'Pemeriksaan/migrasi berhenti: {type(exc).__name__}.')
        print('Jika pemilik view berbeda dan permission denied, minta pemilik DB menjalankan migrasi; jangan DROP VIEW.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
