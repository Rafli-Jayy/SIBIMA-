"""Patch 5C: verified, read-only semantic registry for SIBIMA's 18-table schema.

This is NOT an SQL generator: relationships/metrics describe the fixed capabilities
exported by the repository. No table name or column supplied by Gemini is used
in executable SQL.
"""
from __future__ import annotations

SCHEMA_RELATIONS = (
    ("users", "id", "students", "user_id"),
    ("users", "id", "tutors", "user_id"),
    ("users", "id", "enrollments", "student_id"),
    ("programs", "id", "enrollments", "program_id"),
    ("enrollments", "id", "invoices", "enrollment_id"),
    ("invoices", "id", "payments", "invoice_id"),
    ("programs", "id", "schedules", "program_id"),
    ("users", "id", "schedules", "tutor_id"),
    ("schedules", "id", "class_sessions", "schedule_id"),
    ("class_sessions", "id", "attendances", "session_id"),
    ("enrollments", "id", "attendances", "enrollment_id"),
    ("enrollments", "id", "grades", "enrollment_id"),
)

METRICS = {
    "admin_enrollment_overview": ("enrollments", "jumlah_enrollment", "akun_siswa_aktif_global"),
    "admin_receivables_summary": ("invoices", "jumlah_invoice", "nominal_bruto_belum_lunas"),
    "admin_program_activity": ("programs", "jumlah_jadwal_aktif", "siswa_unik"),
    "admin_attendance_summary": ("class_sessions", "jumlah_sesi_selesai", "persentase_hadir_tercatat"),
    "tutor_program_summary": ("schedules", "jumlah_jadwal_aktif", "jumlah_siswa_aktif_unik"),
    "tutor_attendance_statistics": ("class_sessions", "jumlah_sesi_selesai", "persentase_hadir_tercatat"),
    "student_progress_summary": ("enrollments", "nilai_rata_rata_aritmetika", "kehadiran_tercatat"),
}
