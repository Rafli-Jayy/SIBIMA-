"""Conservative per-turn evidence checks for SIBIMA-AI hybrid retrieval.

This layer never reads PostgreSQL or indexes documents. It only examines the
actual authorized tool results already returned to the Gemini chat controller.
No natural-language classifier is trusted to grant access or execute queries.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.rag.relevance import is_relevant
import re

RAG_TOOL = "search_knowledge_base"

# Conservative checks for explicit requests about *current private data*.
# General questions like "apa itu pembayaran" intentionally do not match.
_DATABASE_REQUIREMENTS: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = (
    (re.compile(r"\b(?:jumlah|berapa|total|ringkasan)\s+(?:akun\s+)?siswa\s+aktif\b", re.I),
     frozenset({"get_admin_overview"})),
    (re.compile(r"\b(?:status\s+)?pendaftaran\s+(?:saya|ku|program\s+\S+\s+saya)\b|"
                r"\b(?:pendaftaran|kelas)\s+saya\s+(?:sudah|masih|belum)\b", re.I),
     frozenset({"get_my_enrollments"})),
    (re.compile(r"\b(?:tagihan|invoice)\s+(?:saya|ku)\b", re.I),
     frozenset({"get_my_invoices"})),
    (re.compile(r"\b(?:pembayaran|riwayat\s+pembayaran)\s+(?:saya|ku)\b", re.I),
     frozenset({"get_my_payments", "get_my_enrollments"})),
    (re.compile(r"\bnilai\s+(?:akademik\s+)?(?:saya|ku)\b", re.I),
     frozenset({"get_my_grades"})),
    (re.compile(r"\bjadwal\s+(?:mengajar\s+)?(?:saya|ku)\b", re.I),
     frozenset({"get_my_teaching_schedule", "get_my_schedule"})),
    (re.compile(r"\b(?:siapa\s+(?:nama\s+)?saya|nama\s+(?:akun\s+)?(?:saya|gw|gue)|\busername\s+saya|\bakun\s+(?:yang\s+)?(?:sedang\s+)?login)\b", re.I),
     frozenset({"get_my_identity"})),
    (re.compile(r"\b(?:cari|temukan|profil|data|info)\s+(?:akun\s+)?(?:siswa|tutor|pengguna)\b|"
                r"\b(?:punya\s+kelas\s+berapa|kelas\s+berapa|mengajar\s+berapa\s+kelas|jumlah\s+kelas\s+tutor)\b", re.I),
     frozenset({"admin_find_users", "admin_get_user_summary"})),
    (re.compile(r"\b(?:siapa\s+s{1,2}aja\s+(?:murid|siswa)\s+(?:yang\s+)?(?:diajar|dibimbing)\s+(?:oleh\s+)?tutor|"
                r"(?:murid|siswa)\s+(?:yang\s+)?(?:diajar|dibimbing)\s+(?:oleh\s+)?tutor|"
                r"daftar\s+(?:murid|siswa)\s+(?:tutor|yang\s+diajar)|"
                r"(?:murid|siswa)\s+\w+\s+(?:siapa\s+saja|berapa\s+orang))\b", re.I),
     frozenset({"admin_list_students_by_tutor"})),
    (re.compile(r"\b(?:tagihan\s+siswa\s+yang\s+belum\s+lunas|"
                r"daftar\s+tagihan\s+belum\s+lunas)\b", re.I),
     frozenset({"list_unpaid_invoices"})),
)
_DOCUMENT_REQUEST = re.compile(
    r"\b(?:chatscreen|chat_screen|streaming_renderer|response_renderer|"
    r"databasefunctionchat|ai_service|ai_db_chat|aitoolcontroller|"
    r"reset\s+konteks\s+ai|function\s+calling\s+gemini|"
    r"knowledge\s*base|sumber\s+dokumen|"
    r"(?:berdasarkan|menurut|dari)\s+(?:dokumen|materi|modul|sop|kebijakan|peraturan)|"
    r"sop\s+resmi|sop\s+sibima|"
    r"(?:flow|alur|struktur|arsitektur|cara kerja|proses|mekanisme|logika)\s+.{0,55}"
    r"(?:sibima|bimbel|pendaftaran|pembayaran|tagihan|invoice|database|kode|coding)|"
    r"(?:sibima|bimbel)\s+.{0,35}(?:flow|alur|arsitektur|proses|database|kode)|"
    r"(?:database|skema|tabel|relasi|coding|kode|modul)\s+.{0,55}(?:sibima|bimbel))\b", re.I)
_OFFICIAL_REQUEST = re.compile(r"\b(?:sop|kebijakan|peraturan)\s+(?:resmi|sibima)\b", re.I)


def _label(value: object, limit: int = 100) -> str:
    """Untrusted source metadata must not create markdown/terminal directives."""
    if not isinstance(value, str):
        return ""
    sanitized = re.sub(r"[\x00-\x1f\x7f<>`*_\[\]{}]", " ", value)
    return " ".join(sanitized.split())[:limit]




# Displayable fields are explicitly allowlisted. Never render raw tool JSON or
# model-generated database values in a fallback response.
_FIELDS_FOR_TOOL = {
    "get_admin_overview": ("siswa_aktif", "tutor_aktif", "program_buka", "pendaftaran_aktif", "tagihan_belum_lunas"),
    "list_unpaid_invoices": ("siswa", "program", "no_invoice", "jumlah", "jatuh_tempo"),
    "get_my_teaching_schedule": ("program", "hari", "jam_mulai", "jam_selesai", "ruang"),
    "list_my_class_students": ("program", "siswa", "status"),
    "get_my_class_attendance": ("program", "siswa", "hadir", "izin", "sakit", "alpa"),
    "get_my_schedule": ("program", "hari", "jam_mulai", "jam_selesai", "ruang", "tutor"),
    "get_my_grades": ("program", "jenis", "judul", "nilai", "tanggal"),
    "get_my_attendance": ("program", "tanggal", "pertemuan_ke", "kehadiran"),
    "get_my_invoices": ("program", "no_invoice", "jumlah", "status", "jatuh_tempo"),
    "get_my_payments": ("program", "jumlah", "status", "paid_at"),
    "get_my_enrollments": ("program", "status_pendaftaran", "status_tagihan_terakhir", "status_pembayaran_terakhir"),
    "get_my_identity": ("nama_lengkap", "username", "role", "status"),
    "admin_find_users": ("user_id", "nama_lengkap", "username", "role", "status", "jadwal_mengajar_aktif", "program_diajar_aktif", "pendaftaran_aktif"),
    "admin_get_user_summary": ("user_id", "nama_lengkap", "username", "role", "status", "jadwal_mengajar_aktif", "program_diajar_aktif", "pendaftaran_aktif"),
    "admin_list_students_by_tutor": ("program", "siswa", "status_pendaftaran"),
}


def _safe_cell(value: object) -> str:
    """Plaintext-safe, bounded display of authorized scalars only."""
    if value is None:
        return "–"
    if type(value) not in (str, int, float, bool):
        return "–"
    return _label(str(value), 100)


def _format_db_row(name: str, row: dict) -> str:
    if name in ("get_my_teaching_schedule", "get_my_schedule"):
        title = _safe_cell(row.get("program"))
        day = _safe_cell(row.get("hari"))
        start = _safe_cell(row.get("jam_mulai"))
        end = _safe_cell(row.get("jam_selesai"))
        room = _safe_cell(row.get("ruang"))
        return f"- {title} — {day}, {start}–{end}, ruang {room}"
    fields = _FIELDS_FOR_TOOL.get(name, ())
    parts = [f"{k.replace('_', ' ')}: {_safe_cell(row[k])}" for k in fields if k in row]
    return "- " + "; ".join(parts) if parts else ""


@dataclass
class HybridEvidence:
    """Private, request-scoped provenance; never stores identity or raw SQL."""
    original_query: str | None = None
    tools: set[str] = field(default_factory=set)
    document_queries: int = 0
    document_errors: int = 0
    documents: list[tuple[str, str, str]] = field(default_factory=list)
    database_results: list[tuple[str, list[dict]]] = field(default_factory=list)

    def record(self, name: str, result: object) -> None:
        if name != RAG_TOOL:
            self.tools.add(name)
            rows = result.get("data") if isinstance(result, dict) else None
            if isinstance(rows, list):
                # Only retain allowlisted fields from authenticated repository results.
                fields = _FIELDS_FOR_TOOL.get(name, ())
                clean_rows = [{key: row[key] for key in fields if key in row}
                              for row in rows[:5] if isinstance(row, dict)]
                self.database_results.append((name, clean_rows))
            return
        self.document_queries += 1
        if not isinstance(result, dict) or result.get("status") != "ok":
            self.document_errors += 1
            return
        hits = result.get("hasil", [])
        if not isinstance(hits, list):
            self.document_errors += 1
            return
        for hit in hits[:3]:
            if not isinstance(hit, dict):
                continue
            title = _label(hit.get("judul"))
            section = _label(hit.get("bagian"))
            document_id = _label(hit.get("document_id"), 96)
            if self.original_query is not None and not is_relevant(
                    self.original_query, document_id, title, section,
                    str(hit.get("kutipan") or "")):
                continue
            if title and document_id and (title, section, document_id) not in self.documents:
                self.documents.append((title, section, document_id))

    def _missing_database(self, query: str) -> bool:
        return any(
            pattern.search(query) and not (allowed & self.tools)
            for pattern, allowed in _DATABASE_REQUIREMENTS
        )

    def _documents_sufficient(self, query: str) -> bool:
        if not self.documents:
            return False
        if _OFFICIAL_REQUEST.search(query):
            # 'Approved for indexing' does not make a DEMO an official policy.
            # This is intentionally conservative; authors still verify policies.
            return any(
                not re.search(r"\bdemo\b", title, re.I)
                and re.search(r"\b(?:sop|kebijakan|peraturan)\b", title, re.I)
                for title, _, _ in self.documents
            )
        return True

    def refusal(self, query: str) -> str | None:
        """Fail closed only when a user explicitly requests grounded evidence."""
        missing_db = self._missing_database(query)
        missing_doc = bool(_DOCUMENT_REQUEST.search(query)) and not self._documents_sufficient(query)
        if missing_db and missing_doc:
            return ("Saya belum dapat memverifikasi data PostgreSQL dan dokumen yang diminta "
                    "melalui sumber yang diizinkan. Saya tidak akan menebak hasilnya. "
                    "Coba periksa akses akun dan ketersediaan dokumen yang disetujui.")
        if missing_db:
            return ("Saya belum berhasil memeriksa data aktual SIBIMA menggunakan fungsi "
                    "database yang tepat. Agar tidak mengarang informasi, saya belum bisa "
                    "memastikan jawabannya.")
        if missing_doc:
            if self.tools:
                return ("Data operasional telah diperiksa, tetapi tidak ada dokumen yang "
                        "sesuai dan diizinkan untuk memverifikasi bagian kebijakan/materi "
                        "yang diminta. Saya tidak akan menyimpulkan aturan yang tidak tersedia.")
            return ("Dokumen yang relevan dan diizinkan belum tersedia untuk menjawab "
                    "pertanyaan tersebut. Saya tidak akan mengarang informasi atau "
                    "menganggap materi DEMO sebagai kebijakan resmi SIBIMA.")
        return None


    def database_part_when_document_missing(self, query: str) -> str | None:
        """Preserve only verified, role-authorized DB results; never trust partial model prose."""
        if self._missing_database(query) or not self.database_results:
            return None
        lines = ["Data SIBIMA yang berhasil diperiksa:"]
        for name, rows in self.database_results:
            if name not in _FIELDS_FOR_TOOL:
                continue
            if rows:
                lines.extend(line for row in rows if (line := _format_db_row(name, row)))
            else:
                lines.append("- Tidak ada data yang ditemukan untuk bagian ini.")
        if len(lines) == 1:
            return None
        lines += ["", "Bagian materi/dokumen belum dapat diverifikasi dari knowledge base yang diizinkan. "
                  "Data operasional di atas tetap dapat digunakan, tetapi saya tidak akan mengarang isi dokumen."]
        return "\n".join(lines)

    def source_footer(self) -> str:
        """App-authored references, not model-invented citations."""
        if not self.documents:
            return ""
        lines = ["", "", "Sumber dokumen yang ditemukan:"]
        for title, section, _ in self.documents[:3]:
            lines.append(f"- {title}" + (f" — bagian {section}" if section else ""))
        return "\n".join(lines)
