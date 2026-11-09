"""Safe offline RAG inspector; never indexes a document or calls Gemini."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.rag import DocumentAccessError, DocumentFormatError, chunk_document, load_document


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Audit dokumen SIBIMA RAG secara offline (tanpa embedding).")
    p.add_argument("path", type=Path, help="File .md/.txt/.pdf")
    p.add_argument("--preview", action="store_true", help="Periksa draf tanpa mengizinkannya diindeks")
    p.add_argument("--role", choices=("admin", "tutor", "siswa"), help="Uji pembatasan role")
    p.add_argument("--max-chars", type=int, default=1000)
    args = p.parse_args(argv)
    try:
        document = load_document(args.path, role=args.role, preview=args.preview)
        chunks = chunk_document(document, role=args.role, preview=args.preview, max_chars=args.max_chars)
    except (DocumentFormatError, DocumentAccessError) as exc:
        print(f"DITOLAK: {exc}", file=sys.stderr)
        return 2
    print(f"ID       : {document.document_id}")
    print(f"Judul    : {document.title}")
    print(f"Status   : {document.status}")
    print(f"Role     : {', '.join(sorted(document.allowed_roles))}")
    print(f"Indexing : {'BOLEH' if document.indexing_allowed and document.status == 'DISETUJUI' else 'TIDAK BOLEH'}")
    print(f"Chunks   : {len(chunks)}")
    print("--- Lokasi bagian ---")
    for ch in chunks:
        print(f"{ch.section[:50]} | {len(ch.text)} karakter | ID ...{ch.chunk_id[-10:]}")
    if args.preview:
        print("CATATAN: MODE PREVIEW SAJA; hasil ini tidak diindeks atau dikirim ke Gemini.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
