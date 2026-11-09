"""SIBIMA-AI 4F.4 final audit runner: offline tests and manifest only.

Does not connect to PostgreSQL, Gemini or Chroma, does not edit app files or index.
Run from the project root: python tools/audit_hybrid_rag_final.py
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description="Offline final audit SIBIMA-AI")
    p.add_argument("--tests-only", action="store_true", help="Skip source verification")
    p.add_argument("--verify-only", action="store_true", help="Skip pytest")
    args = p.parse_args()
    if args.tests_only and args.verify_only:
        p.error("Choose one mode only")
    print("SIBIMA-AI — FINAL OFFLINE AUDIT 4F.4", flush=True)
    if not args.tests_only:
        print("[1] Verifikasi source vs knowledge manifest", flush=True)
        res = subprocess.run([sys.executable, "tools/verify_sibima_knowledge.py"], cwd=ROOT)
        if res.returncode:
            print("BLOKIR: source atau knowledge berbeda; jangan finalisasi atau indexing.")
            return res.returncode
    if not args.verify_only:
        print("[2] Security release gate", flush=True)
        res = subprocess.run([sys.executable, "-m", "pytest", "-q",
                              "tests/test_ai_patch4f4_release_gate.py"], cwd=ROOT)
        if res.returncode:
            print("BLOKIR: ada tes keamanan yang gagal.")
            return res.returncode
        print("[3] Regresi file tes AI/RAG (offline)", flush=True)
        # Enumerate tests BEFORE pytest collection so unrelated app modules
        # requiring psycopg/bcrypt do not prevent the AI-only suite from running.
        paths = sorted(set((ROOT / "tests").glob("test_ai*.py")) |
                       set((ROOT / "tests").glob("test_rag*.py")))
        if not paths:
            print("BLOKIR: tidak ada file tes AI/RAG ditemukan.")
            return 2
        res = subprocess.run([sys.executable, "-m", "pytest", "-q", *map(str, paths)], cwd=ROOT)
        if res.returncode:
            print("BLOKIR: regresi AI/RAG belum bersih.")
            return res.returncode
    print("LULUS AUDIT OFFLINE. Live Tutor/Siswa dan pemeriksaan data asli masih harus dinilai manual.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
