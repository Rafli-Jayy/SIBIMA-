"""Conservative local document loader for SIBIMA RAG.

Reads markdown with metadata frontmatter, or TXT/PDF with a JSON metadata
sidecar (<filename>.meta.json). Never creates embeddings or writes to DB.
Draft/unauthorized documents are rejected unless preview=True.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

ALLOWED_ROLES = frozenset({"admin", "tutor", "siswa"})
ALLOWED_EXTENSIONS = frozenset({".md", ".txt", ".pdf"})
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 150
MAX_TEXT_CHARS = 1_000_000


class DocumentFormatError(ValueError):
    """Invalid document or metadata."""


class DocumentAccessError(PermissionError):
    """Document cannot be indexed or read by the given role."""


@dataclass(frozen=True)
class Document:
    document_id: str
    title: str
    version: str
    status: str
    indexing_allowed: bool
    allowed_roles: frozenset[str]
    source_path: str
    document_type: str
    text: str
    # For PDF, page_texts are 1-based page number + extracted text.
    page_texts: tuple[tuple[int, str], ...] = ()

    def assert_access(self, *, role: str | None = None, preview: bool = False) -> None:
        if not preview and (self.status != "DISETUJUI" or not self.indexing_allowed):
            raise DocumentAccessError(
                f"Dokumen '{self.document_id}' belum disetujui untuk indexing/RAG."
            )
        if role is not None and role not in self.allowed_roles:
            raise DocumentAccessError("Role tidak berhak mengakses dokumen ini.")


def _parse_simple_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse only the small, documented subset of YAML metadata; fail closed."""
    content = content.lstrip("\ufeff")
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise DocumentFormatError("Markdown wajib memiliki metadata frontmatter YAML.")
    closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if closing is None:
        raise DocumentFormatError("Metadata frontmatter tidak ditutup dengan '---'.")
    meta: dict[str, Any] = {}
    for raw in lines[1:closing]:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise DocumentFormatError("Format metadata tidak dikenali.")
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if not re.fullmatch(r"[a-z_]+", k) or k in meta:
            raise DocumentFormatError("Nama metadata tidak valid atau duplikat.")
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            meta[k] = [p.strip().strip("\"'") for p in inner.split(",") if p.strip()]
        elif v.lower() in ("true", "false"):
            meta[k] = v.lower() == "true"
        else:
            meta[k] = v.strip("\"'")
    return meta, "".join(lines[closing + 1:]).strip()


def _metadata(meta: dict[str, Any]) -> tuple[str, str, str, str, frozenset[str], bool]:
    required = ("document_id", "judul", "versi", "status", "role_pembaca", "rag_indexing_allowed")
    if any(key not in meta for key in required):
        raise DocumentFormatError("Metadata wajib tidak lengkap: " + ", ".join(k for k in required if k not in meta))
    doc_id, title, version = (meta[k] for k in ("document_id", "judul", "versi"))
    if not isinstance(doc_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,95}", doc_id):
        raise DocumentFormatError("document_id tidak valid.")
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise DocumentFormatError("judul tidak valid.")
    if not isinstance(version, str) or not version.strip() or len(version) > 30:
        raise DocumentFormatError("versi tidak valid.")
    status = meta["status"]
    if not isinstance(status, str) or status not in ("DISETUJUI", "DRAF_BELUM_DISETUJUI"):
        raise DocumentFormatError("status tidak valid (DISETUJUI atau DRAF_BELUM_DISETUJUI).")
    roles = meta["role_pembaca"]
    if not isinstance(roles, list) or not roles or any(not isinstance(r, str) for r in roles):
        raise DocumentFormatError("role_pembaca harus berupa daftar.")
    role_set = frozenset(roles)
    if not role_set.issubset(ALLOWED_ROLES):
        raise DocumentFormatError("Role tidak dikenal dalam metadata.")
    allowed = meta["rag_indexing_allowed"]
    if type(allowed) is not bool:
        raise DocumentFormatError("rag_indexing_allowed harus boolean.")
    if allowed and status != "DISETUJUI":
        raise DocumentFormatError("Dokumen draf tidak boleh diberi rag_indexing_allowed=true.")
    return doc_id, title.strip(), version.strip(), status, role_set, allowed


def _read_pdf(path: Path) -> tuple[str, tuple[tuple[int, str], ...]]:
    try:
        import pymupdf  # type: ignore
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError as exc:
            raise DocumentFormatError("PDF membutuhkan PyMuPDF: pip install pymupdf") from exc
    try:
        pdf = pymupdf.open(str(path))
        with pdf:
            if getattr(pdf, "needs_pass", False):
                raise DocumentFormatError("PDF terenkripsi tidak didukung.")
            if pdf.page_count > MAX_PDF_PAGES:
                raise DocumentFormatError("PDF terlalu panjang.")
            page_texts = tuple((i + 1, p.get_text("text").strip()) for i, p in enumerate(pdf))
    except DocumentFormatError:
        raise
    except Exception as exc:
        raise DocumentFormatError(f"PDF tidak dapat dibaca ({type(exc).__name__}).") from exc
    if not any(s for _, s in page_texts):
        raise DocumentFormatError("PDF tidak memiliki teks yang dapat diekstrak (scan/OCR belum didukung).")
    return "\n\n".join(s for _, s in page_texts if s), page_texts


def load_document(path: str | Path, *, role: str | None = None, preview: bool = False) -> Document:
    """Load a local document and enforce indexing approval / access restrictions.

    preview=True permits inspection of a draft, NEVER permission to index it.
    A runtime retriever must always call without preview.
    """
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise DocumentFormatError("Sumber tidak ditemukan atau symbolic link ditolak.")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise DocumentFormatError("Hanya .md, .txt, .pdf yang didukung.")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise DocumentFormatError("Ukuran dokumen melampaui batas 8 MB.")
    suffix = path.suffix.lower()
    if suffix == ".md":
        try:
            meta, text = _parse_simple_frontmatter(path.read_text(encoding="utf-8-sig"))
        except UnicodeError as exc:
            raise DocumentFormatError("Markdown harus UTF-8.") from exc
        pages: tuple[tuple[int, str], ...] = ()
    else:
        sidecar = path.with_name(path.name + ".meta.json")
        if not sidecar.is_file() or sidecar.is_symlink():
            raise DocumentFormatError("File TXT/PDF memerlukan metadata sidecar <nama-file>.meta.json.")
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8-sig"))
        except (UnicodeError, ValueError) as exc:
            raise DocumentFormatError("JSON metadata tidak valid.") from exc
        if not isinstance(meta, dict):
            raise DocumentFormatError("JSON metadata harus berupa object.")
        if suffix == ".pdf":
            text, pages = _read_pdf(path)
        else:
            try:
                text = path.read_text(encoding="utf-8-sig").strip()
            except UnicodeError as exc:
                raise DocumentFormatError("TXT harus UTF-8.") from exc
            pages = ()
    if not text.strip():
        raise DocumentFormatError("Konten dokumen kosong.")
    if len(text) > MAX_TEXT_CHARS:
        raise DocumentFormatError("Jumlah karakter dokumen melebihi batas.")
    doc_id, title, version, status, roles, allowed = _metadata(meta)
    document = Document(doc_id, title, version, status, allowed, roles,
                        str(path), suffix.lstrip("."), text, pages)
    document.assert_access(role=role, preview=preview)
    return document
