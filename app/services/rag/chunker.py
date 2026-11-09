"""Deterministic, source-aware text chunker for Patch 4B.

Chunks are PREPARATION ONLY. Embeddings and vector indexing are not implemented.
Every non-preview call enforces document approval, including when a Document
object came from the explicit inspection/preview path.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from .document_loader import Document, DocumentFormatError


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    document_id: str
    document_version: str
    title: str
    section: str
    text: str
    allowed_roles: frozenset[str]
    page: int | None = None

    @property
    def source_label(self) -> str:
        if self.page is not None:
            return f"{self.title} — halaman {self.page}"
        return f"{self.title} — {self.section}"


def _sections_markdown(text: str):
    section = "Pendahuluan"
    buffer: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            if "\n".join(buffer).strip():
                yield section, "\n".join(buffer).strip()
            section = match.group(1).strip()
            buffer = [line]
        else:
            buffer.append(line)
    if "\n".join(buffer).strip():
        yield section, "\n".join(buffer).strip()


def _split_long_block(block: str, size: int):
    """Split oversized blocks at word boundaries; preserve all characters except whitespace."""
    remaining = block.strip()
    while remaining:
        if len(remaining) <= size:
            yield remaining
            break
        cut = remaining.rfind(" ", 0, size + 1)
        if cut < size // 3:
            cut = remaining.rfind("\n", 0, size + 1)
        if cut < size // 3:
            cut = size
        yield remaining[:cut].strip()
        remaining = remaining[cut:].lstrip()


def _split_section(text: str, max_chars: int, overlap_chars: int):
    blocks = re.split(r"\n\s*\n", text.strip())
    parts: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if len(block) <= max_chars:
            parts.append(block)
        else:
            parts.extend(_split_long_block(block, max_chars))
    groups: list[str] = []
    current = ""
    for part in parts:
        sep = "\n\n" if current else ""
        if current and len(current) + len(sep) + len(part) > max_chars:
            groups.append(current)
            current = part
        else:
            current += sep + part
    if current:
        groups.append(current)
    # A short overlap improves retrieval context, scoped within the same section/page.
    for i, group in enumerate(groups):
        if i == 0 or not overlap_chars:
            yield group
            continue
        prev = groups[i - 1]
        prefix = prev[-overlap_chars:].lstrip()
        # Keep each chunk within the explicit character budget.
        if prefix and len(prefix) + len(group) + 2 <= max_chars:
            yield prefix + "\n\n" + group
        else:
            yield group


def chunk_document(
    document: Document, *, role: str | None = None, preview: bool = False,
    max_chars: int = 1000, overlap_chars: int = 100,
) -> list[TextChunk]:
    """Prepare chunks, preserving section/page provenance and role ACL metadata.

    preview=True is for auditing drafts only; its results MUST NOT be indexed.
    """
    document.assert_access(role=role, preview=preview)
    if not (250 <= max_chars <= 5000):
        raise DocumentFormatError("max_chars harus 250–5000.")
    if not (0 <= overlap_chars <= max_chars // 4):
        raise DocumentFormatError("overlap_chars terlalu besar.")
    if document.document_type == "md":
        sections = ((section, None, content) for section, content in _sections_markdown(document.text))
    elif document.document_type == "pdf":
        sections = ((f"Halaman {p}", p, body) for p, body in document.page_texts if body)
    else:
        sections = (("Isi dokumen", None, document.text),)
    chunks = []
    for section, page, body in sections:
        for i, content in enumerate(_split_section(body, max_chars, overlap_chars), 1):
            digest = sha256(f"{document.document_id}|{document.version}|{section}|{page}|{i}|{content}".encode("utf-8")).hexdigest()[:20]
            chunks.append(TextChunk(
                chunk_id=f"{document.document_id}:{digest}",
                document_id=document.document_id,
                document_version=document.version,
                title=document.title,
                section=section,
                text=content,
                allowed_roles=document.allowed_roles,
                page=page,
            ))
    return chunks
