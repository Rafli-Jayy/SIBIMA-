"""Quick Gemini Interactions REST diagnostic, isolated from SIBIMA.

Usage (from project root): python -u tools/llm_test/diagnose_api.py
Does NOT import SIBIMA, modify DB, or log your API key.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from urllib import error, request

MODEL = 'gemini-3.5-flash-lite'
URL = 'https://generativelanguage.googleapis.com/v1beta/interactions'


def worker() -> int:
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not key:
        print('[ERROR] GEMINI_API_KEY kosong', flush=True)
        return 2
    payload = json.dumps({
        'model': MODEL,
        'input': 'Jawab dengan satu kata: Halo',
        'store': False,
    }).encode('utf-8')
    req = request.Request(
        URL, data=payload, method='POST',
        headers={'x-goog-api-key': key, 'Content-Type': 'application/json'},
    )
    try:
        with request.urlopen(req, timeout=12) as res:
            doc = json.load(res)
            print(f'[HTTP] {res.status}', flush=True)
            outputs = []
            for step in doc.get('steps', []):
                if step.get('type') == 'model_output':
                    for part in step.get('content', []):
                        if part.get('type') == 'text' and part.get('text'):
                            outputs.append(part['text'])
            if outputs:
                print('Gemini:', ''.join(outputs), flush=True)
                return 0
            print('[INFO] Server merespons tetapi tidak ada teks output.', flush=True)
            print('Status interaksi:', doc.get('status', 'tidak diketahui'), flush=True)
            return 3
    except error.HTTPError as e:
        print(f'[HTTP ERROR] {e.code}', flush=True)
        try:
            data = json.loads(e.read().decode('utf-8', 'replace'))
            message = str(data.get('error', {}).get('message', 'Tidak ada detail'))
            print('Keterangan:', message[:500], flush=True)
        except Exception:
            print('Tidak dapat membaca detail respons.', flush=True)
        return 1
    except Exception as e:
        print(f'[NETWORK ERROR] {type(e).__name__}: {str(e)[:300]}', flush=True)
        return 1


def main() -> int:
    if '--worker' in sys.argv:
        return worker()
    project_root = Path(__file__).resolve().parents[2]
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=project_root / '.env', override=False)
    except ImportError:
        print('[ERROR] python-dotenv belum terpasang: python -m pip install python-dotenv')
        return 2
    if not os.getenv('GEMINI_API_KEY', '').strip():
        print('[ERROR] GEMINI_API_KEY belum terbaca dari .env')
        return 2
    print('TEST GEMINI INTERACTIONS API — langsung tanpa SDK / SIBIMA', flush=True)
    print('Model:', MODEL, '| HTTP retry: 0 | batas tunggu: 18 detik', flush=True)
    print('Menghubungi server...', flush=True)
    start = perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, '-u', str(Path(__file__).resolve()), '--worker'],
            env=os.environ.copy(),
            capture_output=True, text=True,
            timeout=18, check=False,
        )
    except subprocess.TimeoutExpired:
        print('[TIMEOUT] Tidak ada hasil selesai dalam 18 detik; proses tes dihentikan.', flush=True)
        print('Kemungkinan: jaringan/API terlalu lambat atau permintaan macet.', flush=True)
        print('Ini belum membuktikan kesalahan pada SIBIMA.', flush=True)
        return 124
    print('Durasi: %.2f detik' % (perf_counter() - start), flush=True)
    if result.stdout:
        print(result.stdout.strip(), flush=True)
    if result.stderr:
        print('[DIAGNOSTIK] ' + result.stderr.strip()[-450:], flush=True)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
