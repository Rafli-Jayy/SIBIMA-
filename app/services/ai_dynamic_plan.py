"""Patch 5G.1: bounded dynamic analytics plan for *Admin*.

Gemini supplies identifiers from this registry, never SQL/table names/column
expressions. All query fragments are application-authored and validated.
"""
from __future__ import annotations

from datetime import date
from copy import deepcopy

NAME = "admin_dynamic_query"
ROLE = "admin"
MAX_GROUPS = 20

# Date semantics and filter availability are specific to each fact family.
# The fact families below join only N:1 relationships: one fact row cannot be
# multiplied by schedules, attendance, grades or payments.
DOMAINS = {
    "pendaftaran": {
        "from": "FROM enrollments e JOIN programs p ON p.id=e.program_id",
        "date": "(e.created_at AT TIME ZONE 'Asia/Jakarta')::date",
        "status": "e.status::text",
        "statuses": {"menunggu", "aktif", "ditolak", "batal", "selesai", "menunggu_pembayaran"},
        "metrics": {
            "jumlah_pendaftaran": "COUNT(*)::int",
            "siswa_unik": "COUNT(DISTINCT e.student_id)::int",
        },
        "dimensions": {
            "program": (("p.id", "program_id"), ("p.nama", "program")),
            "status": (("e.status::text", "status"),),
            "bulan": (("date_trunc('month', e.created_at AT TIME ZONE 'Asia/Jakarta')::date", "bulan"),),
        },
        "definisi": "Tanggal pendaftaran = created_at waktu Jakarta; siswa unik berdasarkan student_id, bukan jumlah enrollment.",
    },
    "tagihan": {
        "from": "FROM invoices i JOIN enrollments e ON e.id=i.enrollment_id JOIN programs p ON p.id=e.program_id",
        "date": "i.periode",
        "status": "i.status::text",
        "statuses": {"belum_dibayar", "lunas", "batal"},
        "metrics": {
            "jumlah_tagihan": "COUNT(*)::int",
            "nominal_tagihan": "COALESCE(SUM(i.jumlah), 0)::numeric(18,2)",
            "nominal_belum_lunas": "COALESCE(SUM(i.jumlah), 0)::numeric(18,2)",
        },
        "fixed_status": {"nominal_belum_lunas": "belum_dibayar"},
        "dimensions": {
            "program": (("p.id", "program_id"), ("p.nama", "program")),
            "status": (("i.status::text", "status"),),
            "bulan": (("i.periode", "bulan"),),
        },
        "definisi": "Tanggal = invoices.periode (awal bulan). Nominal belum lunas adalah bruto invoice, BUKAN saldo sisa sesudah pembayaran parsial.",
    },
    "pembayaran": {
        "from": "FROM payments py JOIN invoices i ON i.id=py.invoice_id JOIN enrollments e ON e.id=i.enrollment_id JOIN programs p ON p.id=e.program_id",
        "date": "(py.paid_at AT TIME ZONE 'Asia/Jakarta')::date",
        "status": "py.status::text",
        "statuses": {"menunggu_pembayaran", "menunggu_konfirmasi", "lunas", "ditolak", "gagal", "direfund"},
        "metrics": {
            "jumlah_pembayaran": "COUNT(*)::int",
            "nominal_pembayaran_lunas": "COALESCE(SUM(py.jumlah), 0)::numeric(18,2)",
        },
        "fixed_status": {"nominal_pembayaran_lunas": "lunas"},
        "dimensions": {
            "program": (("p.id", "program_id"), ("p.nama", "program")),
            "status": (("py.status::text", "status"),),
            "bulan": (("date_trunc('month', py.paid_at AT TIME ZONE 'Asia/Jakarta')::date", "bulan"),),
        },
        "definisi": "Tanggal pembayaran = paid_at (boleh NULL). Hanya status lunas dihitung untuk nominal lunas; belum dikurangi refund atau biaya lain.",
    },
    "jadwal": {
        "from": "FROM schedules s JOIN programs p ON p.id=s.program_id JOIN users u ON u.id=s.tutor_id",
        "date": None,
        "status": None,
        "statuses": set(),
        "metrics": {
            "jumlah_jadwal_aktif": "COUNT(*)::int",
            "tutor_unik": "COUNT(DISTINCT s.tutor_id)::int",
        },
        "fixed_where": "s.aktif = TRUE",
        "dimensions": {
            "program": (("p.id", "program_id"), ("p.nama", "program")),
            "tutor": (("u.id", "tutor_user_id"), ("u.nama_lengkap", "tutor")),
        },
        "definisi": "Jadwal aktif adalah jadwal berulang, bukan pertemuan yang telah diselesaikan. Tutor unik berdasarkan tutor_id.",
    },
    "nilai": {
        "from": "FROM grades g JOIN enrollments e ON e.id=g.enrollment_id JOIN programs p ON p.id=e.program_id",
        "date": "g.tanggal",
        "status": None,
        "statuses": set(),
        "metrics": {
            "jumlah_nilai": "COUNT(*)::int",
            "rata_rata_nilai": "ROUND(AVG(g.nilai), 2)",
        },
        "dimensions": {
            "program": (("p.id", "program_id"), ("p.nama", "program")),
            "jenis": (("g.jenis::text", "jenis"),),
            "bulan": (("date_trunc('month', g.tanggal)::date", "bulan"),),
        },
        "definisi": "Rata-rata aritmetika setiap baris nilai; bukan nilai akhir berbobot. Nilai dari enrollment lama juga termasuk.",
    },
    "kehadiran": {
        "from": "FROM attendances a JOIN class_sessions cs ON cs.id=a.session_id JOIN schedules s ON s.id=cs.schedule_id JOIN programs p ON p.id=s.program_id",
        "date": "cs.tanggal",
        "status": None,
        "statuses": set(),
        "metrics": {
            "jumlah_catatan_absensi": "COUNT(*)::int",
            "jumlah_hadir": "COUNT(*) FILTER (WHERE a.status='H')::int",
            "persentase_hadir": "ROUND(100.0 * COUNT(*) FILTER (WHERE a.status='H') / NULLIF(COUNT(*), 0), 2)",
        },
        "fixed_where": "cs.status = 'selesai'",
        "dimensions": {
            "program": (("p.id", "program_id"), ("p.nama", "program")),
            "bulan": (("date_trunc('month', cs.tanggal)::date", "bulan"),),
        },
        "definisi": "Hanya absensi tercatat pada sesi selesai. Persentase = catatan H / semua catatan H/I/S/A, BUKAN semua siswa yang seharusnya hadir.",
    },
}

SCHEMA = {
    "type": "function", "name": NAME,
    "description": (
        "ADMIN SAJA: analitik database dinamis. Gabungkan metrik dan 0-2 dimensi tanpa SQL bebas. "
        "Domain pendaftaran: jumlah_pendaftaran/siswa_unik; tagihan: jumlah_tagihan/nominal_tagihan/nominal_belum_lunas; "
        "pembayaran: jumlah_pembayaran/nominal_pembayaran_lunas; jadwal: jumlah_jadwal_aktif/tutor_unik; "
        "nilai: jumlah_nilai/rata_rata_nilai; kehadiran: jumlah_catatan_absensi/jumlah_hadir/persentase_hadir. "
        "Dimensi: program, bulan, status, tutor, jenis SESUAI domain. Jangan menebak nilai atau meminta SQL. "
        "tanggal_dari/sampai berdasar created_at pendaftaran, periode invoice, paid_at pembayaran, "
        "tanggal nilai atau tanggal sesi; jadwal tidak mendukung tanggal. "
        "Hasil total dihitung dari seluruh data dan rincian maksimal 20 grup. "
        "Gunakan tool khusus lama untuk pertanyaan akun aktif global atau akses siswa/tutor."
    ),
    "parameters": {
        "type": "object", "properties": {
            "domain": {"type": "string", "enum": list(DOMAINS)},
            "metrik": {"type": "string", "enum": sorted({m for d in DOMAINS.values() for m in d["metrics"]})},
            "kelompok": {"type": "array", "items": {"type": "string", "enum": ["program", "bulan", "status", "tutor", "jenis"]}, "maxItems": 2},
            "filter": {"type": "object", "properties": {
                "program_id": {"type": "integer"},
                "status": {"type": "string"},
                "tanggal_dari": {"type": "string", "description": "YYYY-MM-DD, inklusif"},
                "tanggal_sampai": {"type": "string", "description": "YYYY-MM-DD, inklusif"},
            }},
            "urut": {"type": "string", "enum": ["nilai_terbesar", "nilai_terkecil", "dimensi_naik"]},
        },
        "required": ["domain", "metrik"],
    },
}


def validate_dynamic_plan(arguments: object, role: str) -> dict:
    """Return immutable-in-practice, sanitized, server-approved plan."""
    if role != ROLE:
        raise PermissionError("Analitik dinamis tahap pertama hanya untuk Admin.")
    if not isinstance(arguments, dict) or set(arguments) - {"domain", "metrik", "kelompok", "filter", "urut"}:
        raise ValueError("Bentuk rencana dinamis tidak diizinkan.")
    domain = arguments.get("domain")
    if type(domain) is not str or domain not in DOMAINS:
        raise ValueError("Domain analitik tidak dikenal.")
    spec = DOMAINS[domain]
    metric = arguments.get("metrik")
    if type(metric) is not str or metric not in spec["metrics"]:
        raise ValueError("Metrik tidak tersedia untuk domain ini.")
    groups = arguments.get("kelompok", [])
    if not isinstance(groups, list) or len(groups) > 2 or any(type(g) is not str for g in groups):
        raise ValueError("Pengelompokan harus daftar maksimal dua dimensi.")
    if len(set(groups)) != len(groups) or any(g not in spec["dimensions"] for g in groups):
        raise ValueError("Dimensi tidak dikenal, duplikat, atau tidak cocok dengan domain.")
    order = arguments.get("urut", "nilai_terbesar")
    if type(order) is not str or order not in ("nilai_terbesar", "nilai_terkecil", "dimensi_naik"):
        raise ValueError("Pengurutan tidak diizinkan.")
    filters = arguments.get("filter", {})
    if not isinstance(filters, dict) or set(filters) - {"program_id", "status", "tanggal_dari", "tanggal_sampai"}:
        raise ValueError("Filter tidak dikenal.")
    validated = {}
    for k, v in filters.items():
        if v is None:
            continue
        if k == "program_id":
            if type(v) is not int or not (1 <= v <= 2147483647):
                raise ValueError("ID program tidak valid.")
        elif k == "status":
            if type(v) is not str or v not in spec["statuses"]:
                raise ValueError("Status tidak tersedia untuk domain ini.")
        else:
            if spec["date"] is None:
                raise ValueError("Domain ini tidak mendukung filter tanggal.")
            if type(v) is not str or len(v) != 10:
                raise ValueError("Tanggal harus format YYYY-MM-DD.")
            try:
                parsed = date.fromisoformat(v)
            except ValueError as exc:
                raise ValueError("Tanggal tidak valid.") from exc
            if parsed.isoformat() != v:
                raise ValueError("Tanggal harus format ISO YYYY-MM-DD.")
            if domain == "tagihan" and parsed.day != 1:
                raise ValueError("Filter periode tagihan harus tanggal pertama bulan, YYYY-MM-01.")
        validated[k] = v
    if ("tanggal_dari" in validated and "tanggal_sampai" in validated
            and validated["tanggal_dari"] > validated["tanggal_sampai"]):
        raise ValueError("Rentang tanggal terbalik.")
    fixed_status = spec.get("fixed_status", {}).get(metric)
    if fixed_status and "status" in validated and validated["status"] != fixed_status:
        raise ValueError("Filter status bertentangan dengan definisi metrik.")
    return {"domain": domain, "metrik": metric, "kelompok": groups.copy(), "filter": validated, "urut": order}


# Patch 5G.2. Explicit role/domain/metric matrix. User-supplied permissions
# never influence these immutable application-side allowlists.
ROLE_DYNAMIC_NAMES = {
    "admin": NAME,
    "tutor": "tutor_dynamic_query",
    "siswa": "student_dynamic_query",
}
ROLE_DOMAIN_METRICS = {
    "tutor": {
        "pendaftaran": frozenset({"jumlah_pendaftaran", "siswa_unik"}),
        "jadwal": frozenset({"jumlah_jadwal_aktif"}),
        "kehadiran": frozenset({"jumlah_catatan_absensi", "jumlah_hadir", "persentase_hadir"}),
    },
    "siswa": {
        "pendaftaran": frozenset({"jumlah_pendaftaran"}),
        "tagihan": frozenset({"jumlah_tagihan", "nominal_tagihan", "nominal_belum_lunas"}),
        "pembayaran": frozenset({"jumlah_pembayaran", "nominal_pembayaran_lunas"}),
        "nilai": frozenset({"jumlah_nilai", "rata_rata_nilai"}),
        "kehadiran": frozenset({"jumlah_catatan_absensi", "jumlah_hadir", "persentase_hadir"}),
    },
}
ROLE_DIMENSIONS = {
    "tutor": {
        "pendaftaran": frozenset({"program"}),
        "jadwal": frozenset({"program"}),
        "kehadiran": frozenset({"program", "bulan"}),
    },
    "siswa": {
        "pendaftaran": frozenset({"program", "status", "bulan"}),
        "tagihan": frozenset({"program", "status", "bulan"}),
        "pembayaran": frozenset({"program", "status", "bulan"}),
        "nilai": frozenset({"program", "jenis", "bulan"}),
        "kehadiran": frozenset({"program", "bulan"}),
    },
}


def validate_role_dynamic_plan(args: object, role: str) -> dict:
    """Apply strict role caps on top of the existing full semantic validator."""
    if role == "admin":
        return validate_dynamic_plan(args, "admin")
    if role not in ROLE_DOMAIN_METRICS:
        raise PermissionError("Role tidak memiliki akses analitik dinamis.")
    # Reuse the full validator's ENUM, dates, fixed-status, type and SQL-key
    # checks; its admin-only guard is intentionally not exposed to Gemini.
    parsed = validate_dynamic_plan(args, "admin")
    domain = parsed["domain"]
    if parsed["metrik"] not in ROLE_DOMAIN_METRICS[role].get(domain, ()):
        raise PermissionError("Metrik atau domain tidak diizinkan untuk role ini.")
    if any(g not in ROLE_DIMENSIONS[role][domain] for g in parsed["kelompok"]):
        raise PermissionError("Pengelompokan tidak diizinkan untuk role ini.")
    if role == "tutor" and domain == "pendaftaran" and parsed["filter"].get("status", "aktif") != "aktif":
        raise PermissionError("Tutor hanya dapat menghitung siswa dengan pendaftaran aktif.")
    return parsed


def role_dynamic_schema(role: str) -> dict:
    """Expose only permitted plan options, never schema or arbitrary SQL."""
    if role == "admin":
        return deepcopy(SCHEMA)
    if role not in ROLE_DOMAIN_METRICS:
        raise PermissionError("Role tidak memiliki tool dinamis.")
    schema = deepcopy(SCHEMA)
    schema["name"] = ROLE_DYNAMIC_NAMES[role]
    allowed = ROLE_DOMAIN_METRICS[role]
    schema["description"] = (
        ("TUTOR SAJA: analisis jumlah siswa aktif pada program yang diampu, "
         "jadwal aktif sendiri, dan catatan kehadiran pada sesi selesai milik jadwal sendiri. "
         "Jumlah siswa adalah siswa dengan enrollment aktif dan akun aktif. "
         "Tidak boleh melihat tagihan, pembayaran, nilai, atau program Tutor lain. ")
        if role == "tutor" else
        ("SISWA SAJA: analisis pendaftaran, tagihan dan pembayaran MILIK SENDIRI; "
         "nilai dan kehadiran sendiri hanya pada enrollment terakhir yang masih "
         "boleh diakses dan tidak terkunci oleh tunggakan. Tidak boleh melihat siswa lain. ")
    ) + "Pilih satu domain/metrik dan maksimal dua kelompok. SQL bebas dilarang. Perhitungan PostgreSQL read-only."
    props = schema["parameters"]["properties"]
    props["domain"]["enum"] = list(allowed)
    props["metrik"]["enum"] = sorted(set().union(*allowed.values()))
    props["kelompok"]["items"]["enum"] = sorted(set().union(*ROLE_DIMENSIONS[role].values()))
    return schema
