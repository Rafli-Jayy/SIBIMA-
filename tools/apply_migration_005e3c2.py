"""PATCH-005E3-C2: check/apply migrasi attendance.enrollment_id konservatif.

    python tools/apply_migration_005e3c2.py --check
    python tools/apply_migration_005e3c2.py --apply

Tidak pernah memetakan ulang attendance historis secara otomatis.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FK_NAME = "fk_attendances_enrollment"
INDEX_NAME = "idx_attend_enrollment"


def _inspection(cur):
    cur.execute("SELECT current_database();")
    database = cur.fetchone()[0]
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name IN ('attendances', 'enrollments');
    """)
    tables = {r[0] for r in cur.fetchall()}
    if not {'attendances','enrollments'} <= tables:
        raise ValueError('Tabel absensi atau enrollment tidak ditemukan.')
    cur.execute("""
        SELECT data_type, is_nullable FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name='attendances'
          AND column_name='enrollment_id';
    """)
    col = cur.fetchone()
    if col and col != ('integer', 'YES'):
        raise ValueError('Kolom enrollment_id sudah ada dengan tipe/nullable yang berbeda.')
    cur.execute("""
        SELECT pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        WHERE c.conrelid = 'attendances'::regclass AND c.conname = %s;
    """, (FK_NAME,))
    fk_row = cur.fetchone()
    fk = fk_row[0] if fk_row else None
    if fk and not (
        'FOREIGN KEY (enrollment_id)' in fk and 'REFERENCES enrollments(id)' in fk
    ):
        raise ValueError('Constraint bernama sama memiliki definisi berbeda.')
    cur.execute("""
        SELECT indexdef FROM pg_indexes
        WHERE schemaname = current_schema() AND tablename = 'attendances'
          AND indexname = %s;
    """, (INDEX_NAME,))
    ix_row = cur.fetchone()
    ix = ix_row[0] if ix_row else None
    if ix and not ('(enrollment_id)' in ix and 'enrollment_id IS NOT NULL' in ix):
        raise ValueError('Indeks bernama sama memiliki definisi berbeda.')
    cur.execute('SELECT COUNT(*) FROM attendances;')
    total = cur.fetchone()[0]
    unassigned = total
    if col:
        cur.execute('SELECT COUNT(*) FROM attendances WHERE enrollment_id IS NULL;')
        unassigned = cur.fetchone()[0]
    return dict(database=database, col=bool(col), fk=bool(fk), index=bool(ix),
                total=total, unassigned=unassigned)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Migrasi read-safe PATCH-005E3-C2')
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--check', action='store_true')
    flags.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        import psycopg
        from app.config import DB_CONFIG
    except ImportError:
        print('Dependensi psycopg tidak tersedia. Aktifkan venv SIBIMA.')
        return 1
    expected = DB_CONFIG.get('dbname')
    if not expected:
        print('DB_NAME tidak tersedia. Tidak ada perubahan.')
        return 1
    try:
        with psycopg.connect(**DB_CONFIG, autocommit=True) as conn:
            with conn.cursor() as cur:
                state = _inspection(cur)
                if state['database'] != expected:
                    print('Database aktif berbeda dengan konfigurasi; tidak ada perubahan.')
                    return 1
                print(f"Database: {state['database']}")
                print(f"Total absensi: {state['total']}")
                print(f"Absensi belum terhubung: {state['unassigned']}")
                print(f"Kolom enrollment_id: {'ada' if state['col'] else 'belum ada'}")
                print(f"Foreign key: {'ada' if state['fk'] else 'belum ada'}")
                print(f"Index enrollment: {'ada' if state['index'] else 'belum ada'}")
                if args.check:
                    print('CHECK selesai; database tidak diubah.')
                    return 0
                if state['col'] and state['fk'] and state['index']:
                    print('Migrasi sudah lengkap. Tidak ada perubahan.')
                    return 0
                confirm = input(f"Untuk menerapkan migrasi, ketik nama database {expected}: ").strip()
                if confirm != expected:
                    print('Batal. Tidak ada perubahan.')
                    return 1
                with conn.transaction():
                    cur.execute("SET LOCAL lock_timeout = '5s';")
                    if not state['col']:
                        cur.execute('ALTER TABLE attendances ADD COLUMN enrollment_id INTEGER;')
                    if not state['fk']:
                        cur.execute("""ALTER TABLE attendances ADD CONSTRAINT fk_attendances_enrollment
                            FOREIGN KEY (enrollment_id) REFERENCES enrollments(id);""")
                    if not state['index']:
                        cur.execute("""CREATE INDEX idx_attend_enrollment ON attendances (enrollment_id)
                            WHERE enrollment_id IS NOT NULL;""")
                done = _inspection(cur)
                if not (done['col'] and done['fk'] and done['index']):
                    print('Pemeriksaan pasca-migrasi belum lengkap. Hentikan aplikasi.')
                    return 1
                if done['total'] != state['total'] or done['unassigned'] != state['unassigned']:
                    print('Jumlah data sebelum/sesudah berubah. Perlu pemeriksaan Admin.')
                    return 1
                print('MIGRASI PATCH-005E3-C2 BERHASIL. Absensi lama tidak dipetakan/diubah.')
                return 0
    except Exception as exc:
        print(f'Pemeriksaan/migrasi berhenti: {type(exc).__name__}.')
        print('Jika terjadi kegagalan, jangan jalankan aplikasi sebelum --check berhasil.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
