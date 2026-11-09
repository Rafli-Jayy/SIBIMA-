"""Verify knowledge docs actually match the installed SIBIMA source snapshot.

No database/network operations. A mismatch means docs must be re-reviewed and
rebuilt from the user's CURRENT source, not a change to metadata flags.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
MANIFEST=ROOT/'knowledge/verified/source_manifest.json'

def verify(project_root: Path=ROOT, manifest_path: Path=MANIFEST) -> tuple[bool,list[str]]:
    if not manifest_path.is_file():
        return False,['Manifest sumber tidak ditemukan.']
    try:
        data=json.loads(manifest_path.read_text(encoding='utf-8'))
        expected=data['source_sha256']
        if not isinstance(expected,dict) or not expected:
            return False,['Manifest sumber kosong/tidak valid.']
    except (ValueError,KeyError,TypeError):
        return False,['Manifest sumber tidak valid.']
    mismatches=[]
    for name, digest in expected.items():
        if not isinstance(name,str) or not isinstance(digest,str) or name.startswith('/') or '..' in Path(name).parts:
            mismatches.append('Entri manifest tidak valid.')
            continue
        source=project_root/name
        if not source.is_file() or source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
            mismatches.append(name)
    from app.services.rag.document_loader import load_document
    for name in data.get('documents',[]):
        try:
            document_path=project_root/'knowledge/verified'/name
            if hashlib.sha256(document_path.read_bytes()).hexdigest()!=data.get('document_sha256',{}).get(name):
                mismatches.append('Isi knowledge berubah: '+name)
            doc=load_document(document_path,role='admin')
            if doc.status!='DISETUJUI' or not doc.indexing_allowed:
                mismatches.append(name)
        except Exception:
            mismatches.append(name)
    return not mismatches,mismatches

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--quiet',action='store_true')
    args=parser.parse_args()
    ok,errors=verify()
    if ok:
        if not args.quiet:
            print('OK: dokumentasi teknis cocok dengan source snapshot terpasang; boleh indeks khusus Admin.')
        return 0
    print('BLOKIR INDEXING: ada file berbeda/hilang dari snapshot terverifikasi.')
    for x in errors[:25]:print(' -',x)
    if len(errors)>25:print(' - dan',len(errors)-25,'file lainnya')
    print('Perbarui knowledge dari source kode terbaru sebelum indexing; jangan sekadar mengganti status metadata.')
    return 2

if __name__=='__main__':raise SystemExit(main())
