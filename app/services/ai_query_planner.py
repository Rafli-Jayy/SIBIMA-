"""Patch 5C: bounded, schema-aware execution plans from approved function calls.

The model chooses a declared capability; only this whitelist determines the
scope and acceptable filters. No arbitrary SQL / table / column / identity args.
"""
from __future__ import annotations

from datetime import date
from app.services.ai_schema_registry import METRICS

TOOL_ROLE = {
    "admin_enrollment_overview": "admin",
    "admin_receivables_summary": "admin",
    "admin_program_activity": "admin",
    "admin_attendance_summary": "admin",
    "tutor_program_summary": "tutor",
    "tutor_attendance_statistics": "tutor",
    "student_progress_summary": "siswa",
}

_FILTERS = {
    "admin_enrollment_overview": ("program_id", "status", "tanggal_dari", "tanggal_sampai"),
    "admin_receivables_summary": ("program_id", "periode_dari", "periode_sampai", "keterlambatan", "kelompok"),
    "admin_program_activity": ("program_id", "status_enrollment"),
    "admin_attendance_summary": ("program_id", "tanggal_dari", "tanggal_sampai"),
    "tutor_program_summary": ("program_id",),
    "tutor_attendance_statistics": ("program_id", "tanggal_dari", "tanggal_sampai"),
    "student_progress_summary": ("program_id",),
}

# Derived exactly from enrollment_status ENUM in sql/schema.sql.
ENROLLMENT_STATUSES = frozenset({"menunggu", "aktif", "ditolak", "batal", "selesai", "menunggu_pembayaran"})
_OPTIONS = {
    "keterlambatan": ("semua", "overdue", "lewat_h3"),
    "kelompok": ("total", "program", "periode"),
    "status": tuple(sorted(ENROLLMENT_STATUSES)),
    "status_enrollment": tuple(sorted(ENROLLMENT_STATUSES)),
}
_DEFAULTS = {"keterlambatan": "semua", "kelompok": "total"}

DESCRIPTIONS = {
    "admin_enrollment_overview": "ADMIN. Hitung akun siswa aktif TERPISAH dari pendaftaran/enrollment dan siswa unik. Dapat merinci status serta program. Tanggal adalah created_at enrollment waktu Jakarta. Untuk total yang akurat gunakan ini, bukan daftar 20 baris.",
    "admin_receivables_summary": "ADMIN. SUM SELURUH nominal BRUTO invoice dengan status belum_dibayar, bukan saldo bersih setelah pembayaran. Bisa tampilkan per program atau periode. Terlambat (overdue) berbeda dengan lewat H+3. Periode adalah bulan invoice (YYYY-MM-01), bukan created_at.",
    "admin_program_activity": "ADMIN. Aktivitas program: siswa unik, pendaftaran, kuota, jadwal aktif, Tutor unik. Hitungan join terpisah supaya tidak terduplikasi.",
    "admin_attendance_summary": "ADMIN. Rekap status H/I/S/A pada catatan absensi untuk sesi selesai. Persentase hadir hanya dari catatan yang tersedia; sesi belum dilaporkan bukan otomatis alpa.",
    "tutor_program_summary": "TUTOR. Program/jadwal aktif milik Tutor login dan siswa aktif pada program tersebut. Tidak boleh membaca program yang tidak diampu.",
    "tutor_attendance_statistics": "TUTOR. Statistik kehadiran catatan sesi selesai pada jadwal Tutor login. Persentase dari absensi yang tercatat, bukan jumlah siswa yang seharusnya hadir.",
    "student_progress_summary": "SISWA. Ringkasan nilai rata-rata aritmetika dan absensi siswa login pada program yang boleh diakses, bukan nilai akhir berbobot. Tidak menerima ID siswa.",
}


def tool_schema(name: str) -> dict:
    if name not in TOOL_ROLE:
        raise ValueError("Kemampuan analitik tidak dikenal.")
    props = {}
    for key in _FILTERS[name]:
        if key == "program_id":
            props[key] = {"type": "integer", "description": "ID program positif; opsional, tanpa ID berarti semua program dalam izin sesi."}
        elif key in _OPTIONS:
            props[key] = {"type": "string", "enum": list(_OPTIONS[key])}
        elif key.startswith("periode_"):
            props[key] = {"type": "string", "description": "Tanggal awal bulan invoice format YYYY-MM-01."}
        else:
            props[key] = {"type": "string", "description": "Tanggal YYYY-MM-DD waktu Asia/Jakarta (batas inklusif)."}
    return {"type": "function", "name": name, "description": DESCRIPTIONS[name],
            "parameters": {"type": "object", "properties": props}}


def validate_plan(name: str, args: object, role: str) -> dict:
    """Validate *all* supplied data before any DB call. Scope is server-owned."""
    if TOOL_ROLE.get(name) != role:
        raise PermissionError("Fungsi analitik tidak diizinkan untuk role ini.")
    if not isinstance(args, dict):
        raise ValueError("Parameter analitik harus objek JSON.")
    extra = set(args) - set(_FILTERS[name])
    if extra:
        raise ValueError("Parameter analitik di luar daftar yang diizinkan.")
    result = {}
    for key, value in args.items():
        if value is None:
            continue
        if key == "program_id":
            if type(value) is not int or value <= 0:
                raise ValueError("ID program harus bilangan bulat positif.")
        elif key in _OPTIONS:
            if type(value) is not str or value not in _OPTIONS[key]:
                raise ValueError(f"Pilihan {key} tidak valid.")
        else:
            if type(value) is not str or len(value) != 10:
                raise ValueError(f"{key} harus format YYYY-MM-DD.")
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"Tanggal {key} tidak valid.") from exc
            if parsed.isoformat() != value or (key.startswith("periode_") and parsed.day != 1):
                raise ValueError(f"Tanggal {key} harus ISO dan periode harus tanggal pertama bulan.")
        result[key] = value
    for key, value in _DEFAULTS.items():
        if key in _FILTERS[name]:
            result.setdefault(key, value)
    for start, end in (("tanggal_dari", "tanggal_sampai"), ("periode_dari", "periode_sampai")):
        if start in result and end in result and result[start] > result[end]:
            raise ValueError("Awal rentang tidak boleh setelah akhir rentang.")
    return result


def plan_metadata(name: str, role: str) -> dict:
    """Expose deterministic, non-executable explanatory metadata."""
    if TOOL_ROLE.get(name) != role:
        raise PermissionError("Role tidak diizinkan.")
    return {"domain": METRICS[name][0], "metrics": METRICS[name][1:], "scope": {
        "admin": "admin_global", "tutor": "tutor_login", "siswa": "siswa_login"}[role]}
