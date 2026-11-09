"""SIBIMA-AI Patch 2: local, offline validation (no network or DB actions).

Run from the SIBIMA project root:
    python tools/validate_ai_patch2.py

Never prints GEMINI_API_KEY or database credentials.
"""
from __future__ import annotations

import ast
import glob
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    print('=== VALIDASI SIBIMA-AI PATCH 2 (OFFLINE) ===', flush=True)
    if not (ROOT / 'app').is_dir() or not (ROOT / 'tests').is_dir():
        print('ERROR: Jalankan file dari tools/ di dalam root proyek SIBIMA.')
        return 2
    print('Proyek:', ROOT)
    print('Python:', sys.version.split()[0])

    try:
        from dotenv import dotenv_values
        values = dotenv_values(ROOT / '.env')
        env_key = str(values.get('GEMINI_API_KEY') or '')
        live_key = str(os.getenv('GEMINI_API_KEY') or '')
        print('File .env tersedia:', (ROOT / '.env').is_file())
        print('API key pada .env:', 'ada' if env_key else 'belum ada')
        if live_key and env_key and live_key != env_key:
            print('PERINGATAN: GEMINI_API_KEY terminal berbeda dengan isi .env!')
            print('Jika ingin memakai .env, tutup terminal lama atau jalankan:')
            print('  Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue')
        elif live_key:
            print('GEMINI_API_KEY terminal:', 'tersedia (nilai tidak ditampilkan)')
        print('Model .env:', values.get('GEMINI_MODEL', '(tidak disetel)'))
        print('Thinking .env:', values.get('GEMINI_THINKING_LEVEL', '(tidak disetel)'))
    except ImportError:
        print('Catatan: python-dotenv belum terpasang; pemeriksaan .env dilewati.')

    sources = list((ROOT / 'app').rglob('*.py'))
    failures = []
    for path in sources:
        try:
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        except Exception as exc:
            failures.append((str(path.relative_to(ROOT)), str(exc)))
    print('Pemeriksaan sintaks:', len(sources), 'file Python, error:', len(failures))
    for filename, problem in failures:
        print('  -', filename, problem)
    if failures:
        return 1

    test_files = sorted(glob.glob(str(ROOT / 'tests' / 'test_ai*.py')))
    if not test_files:
        print('ERROR: Tidak ditemukan tests/test_ai*.py')
        return 2
    print('Menjalankan tes AI:', len(test_files), 'file')
    cmd = [sys.executable, '-m', 'pytest', '-q', '--disable-warnings', *test_files]
    result = subprocess.run(cmd, cwd=ROOT, timeout=150)
    print('===', 'LULUS' if result.returncode == 0 else 'GAGAL', '===')
    print('Ini tes OFFLINE. Respons Gemini nyata, akses tiga role, dan koneksi PostgreSQL')
    print('harus diuji secara terpisah di Windows. Tidak ada API/DB yang dipanggil.')
    return result.returncode


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except subprocess.TimeoutExpired:
        print('ERROR: Proses pytest melewati batas 150 detik.')
        raise SystemExit(3)
