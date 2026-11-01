"""Test ringan untuk alat audit read-only; tidak perlu database aktif."""
import importlib.util
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'tools' / 'audit_attendance_005e3c1.py'
spec = importlib.util.spec_from_file_location('audit_005e3c1', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DummyCursor:
    def __init__(self, *, enrollment_col=False, missing_table=False):
        columns = [(table, column) for table, names in module.REQUIRED_COLUMNS.items()
                   for column in names]
        if missing_table:
            columns = [(t, c) for t, c in columns if t != 'attendances']
        if enrollment_col:
            columns.append(('attendances', 'enrollment_id'))
        self.responses = [
            [{'table_name': t, 'column_name': c} for t, c in columns],
            [{'total_absensi': 12, 'tanpa_enrollment_program': 1,
              'sebelum_pendaftaran_tercatat': 2, 'calon_tunggal_tanggal': 4,
              'riwayat_enrollment_berganda': 5, 'absensi_sesi_batal': 1,
              'absensi_sesi_perlu_laporan': 0}],
            [{'pasangan_berganda': 3}],
            [{'status': 'selesai', 'jumlah': 4}, {'status': 'batal', 'jumlah': 2}],
        ]
        if enrollment_col:
            self.responses.append([{'belum_terhubung': 8, 'sudah_terhubung': 4}])
        self.executed = []

    def execute(self, sql):
        self.executed.append(sql)
        self.rows = self.responses.pop(0)

    def fetchone(self):
        return self.rows.pop(0)

    def fetchall(self):
        return self.rows


def test_audit_uses_only_select_statements():
    for sql in (module.QUERY_COUNTS, module.QUERY_MULTIPLE_ENROLLMENTS,
                module.QUERY_SESSION_STATUSES, module.QUERY_BOUND_COLUMN):
        assert sql.lstrip().upper().startswith(('SELECT', 'WITH'))
        assert 'DELETE FROM' not in sql.upper()
        assert 'UPDATE ' not in sql.upper()
        assert 'INSERT INTO' not in sql.upper()


def test_report_counts_and_statuses():
    cur = DummyCursor()
    report = module.make_report(cur)
    assert report['counts']['total_absensi'] == 12
    assert report['duplicate_pairs'] == 3
    assert report['statuses']['batal'] == 2
    assert report['bound'] is None
    assert len(cur.executed) == 4


def test_report_existing_enrollment_column():
    cur = DummyCursor(enrollment_col=True)
    report = module.make_report(cur)
    assert report['bound']['sudah_terhubung'] == 4
    assert len(cur.executed) == 5


def test_missing_required_schema_aborts():
    try:
        module.make_report(DummyCursor(missing_table=True))
    except ValueError as exc:
        assert 'attendances' in str(exc)
    else:
        assert False, 'Skema tidak cocok harus ditolak'


def test_no_student_identifiers_in_formatted_report():
    report = module.make_report(DummyCursor())
    output = module.format_report('bimbel_db', report)
    assert 'Total catatan absensi: 12' in output
    assert 'Calon tunggal' in output
    assert 'Belum ditautkan' not in output
    assert 'NIS:' not in output
    assert 'student_id' not in output


def test_attendance_categories_partition_total():
    report = module.make_report(DummyCursor())
    c = report['counts']
    assert sum(c[k] for k in (
        'tanpa_enrollment_program', 'sebelum_pendaftaran_tercatat',
        'calon_tunggal_tanggal', 'riwayat_enrollment_berganda')) == c['total_absensi']
