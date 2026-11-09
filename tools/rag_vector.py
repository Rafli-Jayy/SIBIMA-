"""Explicit Patch4C local index/search CLI. No SIBIMA application changes."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.rag.document_loader import load_document
from app.services.rag.embedding_client import GeminiEmbedder
from app.services.rag.vector_store import KnowledgeVectorStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Index dan cari dokumen RAG disetujui secara lokal.")
    parser.add_argument("mode", choices=["index", "search"])
    parser.add_argument("text", help="Jalur file (index) atau pertanyaan (search)")
    parser.add_argument("--source-root", type=Path, default=ROOT / "knowledge/sources")
    parser.add_argument("--index-dir", type=Path, default=ROOT / "knowledge/index_demo")
    parser.add_argument("--role", choices=["admin", "tutor", "siswa"], default="siswa")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    try:
        # Fail fast on draft documents before making any network requests.
        if args.mode == "index":
            file = Path(args.text)
            if not file.is_absolute():
                file = (ROOT / file).resolve()
            load_document(file, preview=False)
            if args.source_root.resolve() == (ROOT / "knowledge/verified").resolve():
                from tools.verify_sibima_knowledge import verify
                ok, mismatches = verify()
                if not ok:
                    raise RuntimeError("Sumber kode SIBIMA tidak cocok dengan dokumen terverifikasi. "
                                       "Jalankan python tools/verify_sibima_knowledge.py sebelum indexing.")
        from app.config import GEMINI_API_KEY
        embedder = GeminiEmbedder(api_key=GEMINI_API_KEY)
        store = KnowledgeVectorStore(source_root=args.source_root, index_dir=args.index_dir, embedder=embedder)
        if args.mode == "index":
            n = store.index_document(file)
            print(f"Index lokal berhasil: {n} chunk. Dokumen disetujui; tidak ada perubahan PostgreSQL.")
        else:
            hits = store.search(args.text, role=args.role, limit=args.limit)
            if not hits:
                print("Tidak ada sumber disetujui yang cocok dan dapat diakses oleh role ini.")
            for i, hit in enumerate(hits, 1):
                print(f"\n{i}. {hit.source} | {hit.document_id} | jarak={hit.distance:.3f}")
                print(hit.text[:700])
        return 0
    except Exception as exc:
        print(f"GAGAL: {type(exc).__name__}: {exc if type(exc).__name__ not in ('EmbeddingError',) else str(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
