"""Adapter Gemini Interactions API (tanpa database atau penyimpanan server).

Patch 2I: urutan event diagnostik hanya berisi metadata, tanpa isi pesan.
Satu turn dianggap berhasil hanya ketika interaction.completed diterima dan
langkah streaming tertutup. Output analisis eksplisit tidak ditampilkan.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from time import sleep, monotonic
from typing import Any, Iterator
from .search_grounding import get_field, citations_from_step, suggestions_from_step


# Guard sangat sempit untuk kasus yang benar-benar terlihat dalam log pengguna:
# model_output dimulai dengan narasi "Here is a thinking process ...". Isi thought
# dari step bertipe thought selalu diabaikan, terlepas dari formatnya.
_PRIVATE_REASONING_OPENERS = (
    "here is a thinking process",
    "here is my chain of thought",
    "my internal reasoning:",
    "internal reasoning:",
    "chain of thought:",
)


def _opening_state(value: str) -> str:
    """safe | pending | blocked, agar potongan awal tidak bocor saat SSE terfragmentasi."""
    prefix = value.lstrip().lower()
    if any(prefix.startswith(marker) for marker in _PRIVATE_REASONING_OPENERS):
        return "blocked"
    if len(value) <= 100 and (not prefix or any(marker.startswith(prefix) for marker in _PRIVATE_REASONING_OPENERS)):
        return "pending"
    return "safe"

from app.ui.ai.mock_responder import MockEvent


class _ProviderStreamError(RuntimeError):
    """Sanitized status from an Interactions event (no raw API payload)."""

    def __init__(self, code: int | None):
        super().__init__("Gemini menghentikan permintaan streaming.")
        self.code = code


@dataclass(frozen=True)
class GeminiOptions:
    api_key: str
    model: str = "gemini-3.8-flash"
    thinking_level: str = "medium"
    max_attempts: int = 3
    timeout_seconds: int = 60
    google_search_enabled: bool = False


class GeminiClient:
    def __init__(self, options: GeminiOptions, client: Any = None, sleep_fn=sleep):
        self.options = options
        self._sleep = sleep_fn
        self._client = client
        self._owned_client = client is None
        # Only for this AI chat session; never toggles project billing or .env.
        self._search_suspended = False
        if not options.api_key.strip() and client is None:
            raise ValueError("GEMINI_API_KEY belum diatur di .env.")
        if options.thinking_level not in {"low", "medium", "high"}:
            raise ValueError("GEMINI_THINKING_LEVEL harus low, medium, atau high.")
        if not 1 <= options.max_attempts <= 3:
            raise ValueError("GEMINI_MAX_ATTEMPTS harus 1 sampai 3.")
        if not 10 <= options.timeout_seconds <= 300:
            raise ValueError("GEMINI_TIMEOUT_SECONDS harus 10 sampai 300.")
        if client is None:
            try:
                from google import genai
                from google.genai import types
            except ImportError as exc:
                raise RuntimeError("Library google-genai belum tersedia. Jalankan: python -m pip install 'google-genai>=2.3.0'") from exc
            # Disable automatic SDK retries: this adapter owns the total retry budget.
            # SDK uses milliseconds for HttpOptions.timeout.
            self._client = genai.Client(
                api_key=options.api_key,
                http_options=types.HttpOptions(
                    timeout=options.timeout_seconds * 1000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )

    def close(self) -> None:
        if self._owned_client and self._client is not None:
            closer = getattr(self._client, "close", None)
            if callable(closer):
                closer()

    @staticmethod
    def _code(exc: Exception) -> int | None:
        for field in ("code", "status_code"):
            val = getattr(exc, field, None)
            if isinstance(val, int):
                return val
            if isinstance(val, str) and val.isdigit():
                return int(val)
        match = re.search(r"\b(400|401|403|404|408|429|500|502|503|504)\b", str(exc))
        return int(match.group(1)) if match else None

    @classmethod
    def _retryable(cls, exc: Exception) -> bool:
        code = cls._code(exc)
        if code == 429:
            info = str(exc).lower()
            return not any(term in info for term in ("quota exceeded", "quota exhausted", "daily limit", "per day"))
        if code in {408, 500, 502, 503, 504}:
            return True
        return code is None and isinstance(exc, (TimeoutError, ConnectionError))

    @classmethod
    def _friendly_error(cls, exc: Exception) -> str:
        code = cls._code(exc)
        if code in (401, 403):
            return "Autentikasi Gemini gagal. Periksa GEMINI_API_KEY dan akses proyek."
        if code == 404:
            return "Model Gemini tidak tersedia untuk API key ini. Periksa GEMINI_MODEL."
        if code == 429:
            return "Batas penggunaan Gemini tercapai. Periksa kuota dan coba lagi nanti."
        if isinstance(exc, (TimeoutError, ConnectionError)) or code in {408, 500, 502, 503, 504}:
            return "Koneksi atau layanan Gemini sedang bermasalah. Silakan coba lagi."
        return "Permintaan Gemini gagal. Periksa koneksi dan konfigurasi API."

    @staticmethod
    def _search_access_error(exc: Exception, status: int | None) -> str | None:
        """Public explanation only. Never include provider response/error text verbatim."""
        raw = str(exc).lower()
        if status == 429:
            if ("free tier" in raw or "free-tier" in raw) and (
                "grounding" in raw or "google search" in raw
            ):
                return (
                    "Google Search Grounding tidak tersedia untuk tier API proyek ini "
                    "(HTTP 429). Search dinonaktifkan untuk sisa sesi AI; "
                    "chat biasa tetap dapat digunakan tanpa pencarian web."
                )
            return (
                "Permintaan dengan Google Search ditolak (HTTP 429). "
                "Penyebabnya bisa batas kuota model, batas Search, atau akses Grounding; "
                "status tier belum dapat dipastikan dari kode ini. "
                "Search dinonaktifkan untuk sisa sesi AI; chat biasa tetap tersedia "
                "tanpa pencarian web."
            )
        if status == 403:
            return (
                "Permintaan dengan Google Search ditolak (HTTP 403). "
                "Periksa izin API/proyek. Search dinonaktifkan untuk sisa sesi AI; "
                "chat biasa tetap tersedia tanpa pencarian web."
            )
        if status == 400 and any(x in raw for x in ("google_search", "google search", "grounding")):
            return (
                "Konfigurasi Google Search ditolak API (HTTP 400). "
                "Search dinonaktifkan untuk sisa sesi AI; chat biasa tetap tersedia "
                "tanpa pencarian web."
            )
        return None

    @staticmethod
    def _safe_event_label(value: Any, fallback: str = "tidak-ada") -> str:
        """Only show short code-like event labels, never arbitrary server text."""
        if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]{0,39}", value):
            return fallback
        return value

    @classmethod
    def _diagnostic(cls, exc: Exception, *, phase: str, last_event: str,
                    last_delta: str, sse_code: str, reason: str,
                    attempt: int, max_attempts: int,
                    elapsed: float, partial_chars: int, trace: list[str] | None = None,
                    events_seen: int = 0, open_steps: int = 0) -> str:
        """Only derived metadata; never show raw errors, prompts, API keys or responses."""
        status = cls._code(exc)
        status_label = f"HTTP {status}" if status is not None else "HTTP tidak-terdeteksi"
        error_type = cls._safe_event_label(type(exc).__name__, "Error")
        parts = [
            status_label,
            f"jenis={error_type}",
            f"fase={phase}",
            f"event={cls._safe_event_label(last_event)}",
        ]
        if last_event == "step.delta":
            parts.append(f"delta={cls._safe_event_label(last_delta)}")
        if sse_code != "tidak-ada":
            parts.append(f"kode-event={cls._safe_event_label(sse_code)}")
        if reason != "tidak-ada":
            parts.append(f"alasan={cls._safe_event_label(reason)}")
        parts.extend([
            f"percobaan={attempt}/{max_attempts}",
            f"durasi={elapsed:.2f}dtk",
            f"teks-terkirim={partial_chars}karakter",
            f"jumlah-event={events_seen}",
            f"step-terbuka={open_steps}",
        ])
        if trace:
            # Label dibentuk dari jenis event saja, tanpa data model/prompt.
            parts.append("alur=" + ">".join(trace))
        return "[Diagnostik Gemini: " + "; ".join(parts) + "]"

    def stream(self, history: list[dict], query: str, system_instruction: str) -> Iterator[MockEvent]:
        """Stream event untuk renderer yang sudah dipakai Patch 1.

        history hanya di-commit melalui completed.data['steps']; caller yang
        menambahkannya setelah jawaban sukses. Gagal/terputus tidak commit.
        """
        user_step = {"type": "user_input", "content": [{"type": "text", "text": query}]}
        request_history = deepcopy(history) + [user_step]
        # If Search was refused earlier, the next *user turn* is normal chat.
        # Do not silently retry the failed search request as a new API call.
        search_for_turn = self.options.google_search_enabled and not self._search_suspended
        for attempt in range(1, self.options.max_attempts + 1):
            started_at = monotonic()
            chunks: list[str] = []
            steps_by_index: dict[int, dict] = {}
            active_type: dict[int, str] = {}
            stopped_steps: set[int] = set()
            trace: list[str] = []
            events_seen = 0
            first_text_pending = ""
            first_text_released = False
            completed = False
            search_used = False
            search_suggestions = []
            citations = []
            search_started = False
            phase = "membuka-stream"
            last_event = "tidak-ada"
            last_delta = "tidak-ada"
            sse_code = "tidak-ada"
            reason = "tidak-ada"
            try:
                kwargs = dict(
                    model=self.options.model,
                    input=request_history,
                    system_instruction=system_instruction,
                    generation_config={"thinking_level": self.options.thinking_level},
                    stream=True,
                    store=False,
                )
                if search_for_turn:
                    kwargs["tools"] = [{"type": "google_search"}]
                events = self._client.interactions.create(**kwargs)
                phase = "menunggu-event"
                for event in events:
                    events_seen += 1
                    name = getattr(event, "event_type", "")
                    last_event = self._safe_event_label(name)
                    index = getattr(event, "index", None)
                    if name == "step.start" and index is not None:
                        step = getattr(event, "step", None)
                        kind = getattr(step, "type", None)
                        label = self._safe_event_label(kind)
                        if len(trace) < 20:
                            trace.append("start:" + label)
                        if kind not in {"thought", "model_output", "google_search_call", "google_search_result"}:
                            reason = "jenis-step-tidak-didukung"
                            raise RuntimeError("Gemini menghasilkan langkah yang tidak didukung di Patch 2.")
                        if kind in {"google_search_call", "google_search_result"}:
                            if not search_for_turn:
                                reason = "search-tidak-diaktifkan"
                                raise RuntimeError("Google Search tidak aktif untuk sesi ini.")
                            search_used = True
                            if not search_started:
                                search_started = True
                                yield MockEvent("search_started", None)
                        active_type[index] = kind
                        steps_by_index[index] = {"type": kind}
                        if kind == "model_output":
                            steps_by_index[index]["content"] = []
                        elif kind == "thought":
                            # Google dapat menempatkan signature pada step.start
                            # atau mengirimkannya lewat thought_signature delta.
                            signature = getattr(step, "signature", None)
                            if isinstance(signature, str) and signature:
                                steps_by_index[index]["signature"] = signature
                    elif name == "step.delta":
                        delta = getattr(event, "delta", None)
                        kind = getattr(delta, "type", None)
                        last_delta = self._safe_event_label(kind)
                        if len(trace) < 20:
                            trace.append("delta:" + last_delta)
                        current = steps_by_index.get(index)
                        current_kind = active_type.get(index)
                        if kind == "text" and current is not None and current_kind == "model_output":
                            citations.extend(citations_from_step({"content": [{"type": "text", "annotations": get_field(delta, "annotations") or []}]}))
                            part = str(getattr(delta, "text", "") or "")
                            if part:
                                phase = "menerima-teks"
                                # Tunggu sebentar hanya jika awalnya mungkin
                                # berbentuk narasi penalaran yang terlarang.
                                if not first_text_released:
                                    first_text_pending += part
                                    verdict = _opening_state(first_text_pending)
                                    if verdict == "blocked":
                                        phase = "memvalidasi-output"
                                        reason = "output-analisis-terdeteksi"
                                        raise RuntimeError("Model mengirim teks analisis sebagai jawaban.")
                                    if verdict == "pending":
                                        continue
                                    part = first_text_pending
                                    first_text_pending = ""
                                    first_text_released = True
                                chunks.append(part)
                                content = current["content"]
                                if content and content[-1]["type"] == "text":
                                    content[-1]["text"] += part
                                else:
                                    content.append({"type": "text", "text": part})
                                if not search_used:
                                    yield MockEvent("text_chunk", part)
                        elif kind == "thought_signature" and current is not None and current_kind == "thought":
                            signature = getattr(delta, "signature", None)
                            if isinstance(signature, str) and signature:
                                current["signature"] = signature
                        elif current_kind in {"google_search_call", "google_search_result"}:
                            # Search payloads contain third-party snippets: never stream to terminal.
                            if current_kind == "google_search_result":
                                suggestions = suggestions_from_step({"result": get_field(delta, "result") or []})
                                search_suggestions.extend(suggestions)
                            continue
                        elif current_kind == "thought" and kind in {"thought_summary", "text"}:
                            # Thought content is never user-facing output.
                            continue
                        elif kind not in {"thought_summary", None}:
                            reason = "jenis-delta-tidak-didukung"
                            raise RuntimeError("Gemini menghasilkan konten yang tidak didukung pada Patch 2.")
                    elif name == "step.stop" and index is not None:
                        full_step = getattr(event, "step", None)
                        if full_step is not None:
                            if active_type.get(index) == "model_output":
                                citations.extend(citations_from_step(full_step))
                            elif active_type.get(index) == "google_search_result":
                                search_suggestions.extend(suggestions_from_step(full_step))
                        if active_type.get(index) == "google_search_result":
                            yield MockEvent("search_finished", None)
                        stopped_steps.add(index)
                        if len(trace) < 20:
                            trace.append("stop")
                    elif name == "interaction.completed":
                        if len(trace) < 20:
                            trace.append("completed")
                        interaction = getattr(event, "interaction", None)
                        status = getattr(interaction, "status", None)
                        if status not in (None, "completed"):
                            reason = "status-selesai-tidak-valid"
                            raise RuntimeError("Gemini melaporkan status penyelesaian tidak valid.")
                        completed = True
                        if search_used:
                            interaction = getattr(event, "interaction", None)
                            for step in (get_field(interaction, "steps") or []):
                                if get_field(step, "type") == "model_output":
                                    citations.extend(citations_from_step(step))
                                elif get_field(step, "type") == "google_search_result":
                                    search_suggestions.extend(suggestions_from_step(step))
                    elif name in {"interaction.failed", "error"}:
                        if len(trace) < 20:
                            trace.append("error")
                        reason = "event-gagal"
                        server_error = get_field(event, "error") or get_field(
                            get_field(event, "interaction"), "error"
                        )
                        raw_code = get_field(server_error, "code")
                        raw_status = get_field(server_error, "status")
                        original_code = str(raw_code or raw_status or "")
                        code_token = original_code.upper()
                        sse_code = self._safe_event_label(original_code)
                        status = None
                        if isinstance(raw_code, int):
                            status = raw_code
                        elif isinstance(raw_code, str) and raw_code.isdigit():
                            status = int(raw_code)
                        elif code_token in {
                            "RESOURCE_EXHAUSTED", "RATE_LIMIT_EXCEEDED",
                            "QUOTA_EXCEEDED", "TOO_MANY_REQUESTS",
                        }:
                            status = 429
                        elif code_token in {"PERMISSION_DENIED", "FORBIDDEN"}:
                            status = 403
                        elif code_token in {"UNAVAILABLE", "SERVICE_UNAVAILABLE"}:
                            status = 503
                        # Never print or propagate the raw server message.
                        raise _ProviderStreamError(status)
                    elif len(trace) < 20:
                        trace.append(self._safe_event_label(name))
                phase = "memvalidasi-hasil"
                if not completed:
                    reason = "event-completed-tidak-ada"
                    raise RuntimeError("Gemini tidak mengirim event interaction.completed.")
                if set(steps_by_index) - stopped_steps:
                    reason = "step-stop-tidak-ada"
                    raise RuntimeError("Gemini tidak menutup seluruh langkah respons.")
                if first_text_pending:
                    if _opening_state(first_text_pending) == "blocked":
                        reason = "output-analisis-terdeteksi"
                        raise RuntimeError("Model mengirim teks analisis sebagai jawaban.")
                    # Penutup stream sudah sah; fragment awal yang ambigu aman.
                    chunks.append(first_text_pending)
                    current = next((steps_by_index[i] for i in sorted(steps_by_index)
                                    if steps_by_index[i]["type"] == "model_output"), None)
                    if current is not None:
                        current["content"].append({"type": "text", "text": first_text_pending})
                    if not search_used:
                        yield MockEvent("text_chunk", first_text_pending)
                if not chunks:
                    reason = "teks-kosong"
                    raise RuntimeError("Gemini tidak mengirim jawaban lengkap.")
                steps = [steps_by_index[i] for i in sorted(steps_by_index)]
                # Avoid silently losing thought signatures in stateless follow-ups.
                if any(s["type"] == "thought" and not s.get("signature") for s in steps):
                    reason = "signature-konteks-hilang"
                    raise RuntimeError("Signature konteks Gemini tidak lengkap.")
                # Do not put provider-supplied Search Suggestions into stateless
                # conversation history. The browser viewer keeps them in RAM only.
                history_steps = [user_step] + [s for s in steps if s["type"] in {"thought", "model_output"}]
                if search_used:
                    if not search_suggestions:
                        reason = "saran-google-tidak-tersedia"
                        raise RuntimeError("Google tidak mengirim Search Suggestions untuk ditampilkan bersama hasil.")
                    from .search_grounding import deduplicate_citations
                    yield MockEvent("completed", {
                        "kind": "search", "content": "Hasil Google Search tersedia di browser pendamping.",
                        "data": {
                            "steps": history_steps,
                            "search_result": {
                                "answer": "".join(chunks),
                                "citations": deduplicate_citations(citations),
                                "search_suggestions": search_suggestions[:5],
                            },
                        },
                    })
                else:
                    yield MockEvent("completed", {
                        "kind": "markdown", "content": "".join(chunks),
                        "data": {"steps": history_steps},
                    })
                return
            except (KeyboardInterrupt, GeneratorExit):
                raise
            except Exception as exc:
                # Never retry after a visible chunk: it could duplicate output.
                status = self._code(exc)
                search_access_message = self._search_access_error(exc, status) if search_for_turn else None
                if search_access_message:
                    # Disable only this chat session; do not change .env or other users.
                    self._search_suspended = True
                    reason = "search-dibatasi"
                # While Search tool is enabled, never retry automatically: even an
                # unsuccessful call may have reached/charged the search tool.
                if (not search_for_turn and not chunks and not search_used
                        and self._retryable(exc) and attempt < self.options.max_attempts):
                    self._sleep(min(2 ** (attempt - 1), 4))
                    continue
                suffix = " Respons sebagian tidak dimasukkan ke konteks." if chunks else ""
                if search_access_message is not None:
                    message = search_access_message
                elif reason == "event-completed-tidak-ada":
                    message = "Streaming Gemini terputus tanpa event penyelesaian."
                elif reason == "step-stop-tidak-ada":
                    message = "Streaming Gemini tidak menutup langkah jawaban dengan lengkap."
                elif reason == "output-analisis-terdeteksi":
                    message = "Gemini mengirim format analisis yang tidak ditampilkan. Coba ulang pertanyaan."
                elif reason == "status-selesai-tidak-valid":
                    message = "Gemini melaporkan status penyelesaian yang tidak valid."
                elif reason == "saran-google-tidak-tersedia":
                    message = "Saran Google Search tidak tersedia; hasil tidak dapat ditampilkan di terminal."
                else:
                    message = self._friendly_error(exc)
                diagnostic = self._diagnostic(
                    exc, phase=phase, last_event=last_event, last_delta=last_delta,
                    sse_code=sse_code, reason=reason, attempt=attempt,
                    max_attempts=self.options.max_attempts,
                    elapsed=monotonic() - started_at,
                    partial_chars=sum(len(part) for part in chunks),
                    trace=trace, events_seen=events_seen,
                    open_steps=len(set(steps_by_index) - stopped_steps),
                )
                yield MockEvent("error", message + suffix + "\n" + diagnostic)
                return
