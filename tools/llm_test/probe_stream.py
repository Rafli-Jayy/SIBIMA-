"""Bandingkan event Interactions API mentah (REST SSE) dengan yang dibaca SDK.

Jalankan dari root SIBIMA:
    python -u tools/llm_test/probe_stream.py --self-test
    python -u tools/llm_test/probe_stream.py --mode raw
    python -u tools/llm_test/probe_stream.py --mode sdk

Tidak mengimpor app SIBIMA, tidak mengakses database, tidak menyimpan prompt,
API key, isi jawaban, signature, interaction ID, atau respons mentah.
Satu pemanggilan API saja untuk setiap mode; tanpa retry otomatis.
"""
from __future__ import annotations

import argparse
import io
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from urllib import error, request

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions?alt=sse"
DEFAULT_PROMPT = (
    "Jelaskan lima contoh makanan yang populer di daerah kampus "
    "dalam lima poin singkat, masing-masing satu kalimat."
)
HARD_DEADLINE = 35


def label(value):
    if isinstance(value, str) and len(value) <= 64 and value.replace(".", "").replace("_", "").replace("-", "").isalnum():
        return value
    return "lainnya"


class EventAudit:
    def __init__(self):
        self.count = 0
        self.events = []
        self.chars = 0
        self.completed = False
        self.done = False
        self.open_steps = set()
        self.last_event = "belum-ada"
        self.error = False
        self.status = "tidak-ada"

    def record(self, kind, index=None, subtype=None, chars=0, status=None):
        self.count += 1
        self.last_event = label(kind)
        if len(self.events) < 40:
            item = self.last_event
            if kind == "step.start" and subtype:
                item += ":" + label(subtype)
            elif kind == "step.delta" and subtype:
                item += ":" + label(subtype)
            self.events.append(item)
        if kind == "step.start" and index is not None:
            self.open_steps.add(index)
        elif kind == "step.stop" and index is not None:
            self.open_steps.discard(index)
        elif kind == "interaction.completed":
            self.completed = True
            self.status = label(status) if status else "completed-event"
        elif kind in ("error", "interaction.failed"):
            self.error = True
        elif kind == "done":
            self.done = True
        self.chars += chars

    def summary(self, transport):
        print("=== HASIL EVENT STREAM ===", flush=True)
        print("Transport:", transport, flush=True)
        print("Jumlah event:", self.count, flush=True)
        print("Karakter jawaban:", self.chars, flush=True)
        print("Ada interaction.completed:", self.completed, flush=True)
        print("Ada [DONE]:", self.done if transport == "REST SSE" else "(tidak diperlukan)", flush=True)
        print("Step belum ditutup:", len(self.open_steps), flush=True)
        print("Event terakhir:", self.last_event, flush=True)
        print("Status interaksi:", self.status, flush=True)
        print("Event error:", self.error, flush=True)
        print("Alur (maks 40):", " > ".join(self.events), flush=True)
        print("Interpretasi:", ("stream selesai normal" if self.completed and not self.open_steps
                                 else "stream tidak lengkap / berhenti tanpa penanda selesai"), flush=True)



def parse_sse_events(byte_lines, audit):
    """Baca framing SSE dengan aman tanpa menyimpan isi atau ID event."""
    event_name, lines = "", []

    def consume():
        nonlocal event_name, lines
        if not lines:
            event_name = ""
            return
        raw = "\n".join(lines)
        lines = []
        if raw.strip() == "[DONE]":
            audit.record("done")
            event_name = ""
            return
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            audit.record("malformed-json")
            event_name = ""
            return
        if not isinstance(doc, dict):
            event_name = ""
            return
        kind = doc.get("event_type") or event_name
        delta = doc.get("delta") if isinstance(doc.get("delta"), dict) else {}
        step = doc.get("step") if isinstance(doc.get("step"), dict) else {}
        inter = doc.get("interaction") if isinstance(doc.get("interaction"), dict) else {}
        chunk = delta.get("text") if kind == "step.delta" and delta.get("type") == "text" else ""
        audit.record(kind, index=doc.get("index"),
                     subtype=(step.get("type") if kind == "step.start" else delta.get("type")),
                     chars=len(chunk) if isinstance(chunk, str) else 0,
                     status=inter.get("status"))
        event_name = ""

    for raw_line in byte_lines:
        if isinstance(raw_line, bytes):
            line = raw_line.decode("utf-8", "replace").rstrip("\r\n")
        else:
            line = str(raw_line).rstrip("\r\n")
        if not line:
            consume()
        elif line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            lines.append(line[5:].lstrip(" "))
    consume()


def safe_timeout_output(value):
    """TimeoutExpired.stdout bisa berupa bytes ATAU str pada Windows/Python."""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")[-600:]
    if isinstance(value, str):
        return value[-600:]
    return ""

def raw_worker(key, model, prompt, thinking):
    body = json.dumps({
        "model": model,
        "input": prompt,
        "stream": True,
        "store": False,
        "generation_config": {"thinking_level": thinking},
    }).encode("utf-8")
    req = request.Request(ENDPOINT, method="POST", data=body, headers={
        "x-goog-api-key": key,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    })
    audit = EventAudit()
    try:
        with request.urlopen(req, timeout=25) as res:
            print("HTTP:", res.status, flush=True)
            content_type = res.headers.get("Content-Type", "tidak-ada")
            # Cetak tipe media saja, tidak pernah konten respons atau kredensial.
            media_type = content_type.split(";", 1)[0].strip().lower()
            print("Content-Type:", media_type, flush=True)
            if media_type != "text/event-stream":
                print("RESPONS BUKAN SSE: tidak dapat dinilai sebagai event stream.", flush=True)
                return 5
            parse_sse_events(res, audit)
    except error.HTTPError as exc:
        print("HTTP ERROR:", exc.code, flush=True)
        print("Tidak membaca/mencetak respons mentah atau data kredensial.", flush=True)
        return 2
    except Exception as exc:
        print("NETWORK/STREAM ERROR:", type(exc).__name__, flush=True)
        return 3
    audit.summary("REST SSE")
    return 0 if audit.completed and not audit.open_steps else 4


def sdk_worker(key, model, prompt, thinking):
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("SDK google-genai tidak terpasang.", flush=True)
        return 2
    try:
        version = importlib.metadata.version("google-genai")
    except importlib.metadata.PackageNotFoundError:
        version = "tidak diketahui"
    print("Versi SDK:", version, flush=True)
    audit = EventAudit()
    try:
        with genai.Client(api_key=key, http_options=types.HttpOptions(
            timeout=25000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
            stream = client.interactions.create(model=model, input=prompt, stream=True, store=False,
                  generation_config={"thinking_level": thinking})
            for event in stream:
                kind = getattr(event, "event_type", "")
                delta = getattr(event, "delta", None)
                step = getattr(event, "step", None)
                inter = getattr(event, "interaction", None)
                text_value = getattr(delta, "text", "") if getattr(delta, "type", "") == "text" else ""
                audit.record(kind, index=getattr(event, "index", None),
                    subtype=(getattr(step, "type", None) if kind == "step.start" else getattr(delta, "type", None)),
                    chars=len(text_value) if isinstance(text_value, str) else 0,
                    status=getattr(inter, "status", None))
    except Exception as exc:
        print("SDK/STREAM ERROR:", type(exc).__name__, flush=True)
        return 3
    audit.summary("Google Gen AI SDK")
    return 0 if audit.completed and not audit.open_steps else 4


def self_test():
    test = EventAudit()
    test.record("interaction.created")
    test.record("step.start", 0, "model_output")
    test.record("step.delta", 0, "text", chars=8)
    test.record("step.stop", 0)
    test.record("interaction.completed", status="completed")
    test.record("done")
    assert test.completed and test.done and not test.open_steps and test.chars == 8
    # Simulasi alur SSE sesuai contoh resmi. Tidak menghubungi Google.
    sample = (
        'event: interaction.created\ndata: {"event_type":"interaction.created"}\n\n'
        'event: step.start\ndata: {"event_type":"step.start","index":0,"step":{"type":"model_output"}}\n\n'
        'event: step.delta\ndata: {"event_type":"step.delta","index":0,"delta":{"type":"text","text":"Halo"}}\n\n'
        'event: step.stop\ndata: {"event_type":"step.stop","index":0}\n\n'
        'event: interaction.completed\ndata: {"event_type":"interaction.completed","interaction":{"status":"completed"}}\n\n'
    )
    parsed = EventAudit()
    parse_sse_events(io.BytesIO(sample.encode("utf-8")), parsed)
    assert parsed.completed and not parsed.open_steps and parsed.count == 5 and parsed.chars == 4
    assert safe_timeout_output(b"timeout") == "timeout"
    assert safe_timeout_output("timeout") == "timeout"
    assert "alt=sse" in ENDPOINT
    print("SELF-TEST LULUS: terminasi SSE, parser event, dan timeout Windows.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Diagnosis Interactions SSE, bukan tester percakapan.")
    parser.add_argument("--mode", choices=("raw", "sdk"), default="raw")
    parser.add_argument("--model", default=None)
    parser.add_argument("--thinking", choices=("low", "medium", "high"), default=None)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    root = Path(__file__).resolve().parents[2]
    try:
        from dotenv import dotenv_values
    except ImportError:
        print("python-dotenv belum terpasang.")
        return 2
    settings = dotenv_values(root / ".env")
    # Sengaja prioritaskan .env untuk menghindari konflik environment terminal lama.
    key = (settings.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    model = args.model or settings.get("GEMINI_MODEL") or "gemini-3.8-flash"
    thinking = args.thinking or settings.get("GEMINI_THINKING_LEVEL") or "low"
    if not key:
        print("GEMINI_API_KEY tidak ditemukan.")
        return 2
    if thinking not in {"low", "medium", "high"}:
        print("Thinking level tidak valid.")
        return 2
    if args.worker:
        return raw_worker(key, model, DEFAULT_PROMPT, thinking) if args.mode == "raw" else sdk_worker(key, model, DEFAULT_PROMPT, thinking)
    print("=== DIAGNOSIS KELENGKAPAN STREAM GEMINI ===", flush=True)
    print("Model:", model, "| Mode:", args.mode, "| Retry: 0 | Maksimum 35 detik", flush=True)
    start = perf_counter()
    cmd = [sys.executable, "-u", str(Path(__file__).resolve()), "--mode", args.mode, "--model", model, "--thinking", thinking, "--worker"]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=HARD_DEADLINE)
    except subprocess.TimeoutExpired as exc:
        print("TIMEOUT: proses dihentikan setelah 35 detik.")
        print("Catatan: ini batas pengujian, bukan bukti server Google rusak.")
        if exc.stdout:
            print(safe_timeout_output(exc.stdout))
        return 124
    print("Durasi:", f"{perf_counter() - start:.2f} detik")
    print(run.stdout.strip() or "(Tidak ada output dari worker)")
    if run.stderr:
        print("Worker mengirim output error tambahan (disembunyikan demi keamanan).")
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
