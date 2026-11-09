"""Ephemeral localhost browser companion for Google-grounded answers.

No disk files, database, cookies or access logs. Grounded content and Google's
Search Suggestions remain in memory until the AI menu is closed.
"""
from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from secrets import token_urlsafe
from threading import Thread
from urllib.parse import urlsplit
import webbrowser

from app.services.search_grounding import deduplicate_citations


def render_grounded_html(payload: dict) -> str:
    answer = escape(str(payload.get("answer", "")), quote=False)
    citations = deduplicate_citations(payload.get("citations", []))
    sources = "".join(
        f'<li><a href="{escape(item["url"], quote=True)}" rel="noopener noreferrer" '
        f'target="_blank">{escape(item["title"])}</a></li>' for item in citations
    )
    # Search Suggestions are provided as HTML/CSS by Google. Render them
    # unmodified inside a sandboxed iframe, NOT as a rewritten text list.
    suggestions = "".join(
        '<iframe title="Saran penelusuran Google" loading="eager" '
        'referrerpolicy="no-referrer" sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox" '
        f'srcdoc="{escape(item, quote=True)}"></iframe>'
        for item in payload.get("search_suggestions", [])[:5] if isinstance(item, str)
    )
    return f'''<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><title>SIBIMA-AI • Hasil Google Search</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;max-width:850px;margin:2rem auto;padding:0 1rem;
background:#101724;color:#edf2f9}}h1{{font-size:1.4rem}}a{{color:#95cafa}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;border-left:3px solid #6cb3e9;
padding:1rem;background:#192539}}li{{overflow-wrap:anywhere}}iframe{{border:0;display:block;
width:100%;min-height:120px;background:white;margin:1rem 0}}</style></head><body>
<h1>✦ SIBIMA-AI — Hasil Google Search</h1>
<section aria-label="Jawaban"><pre>{answer}</pre></section>
<section><h2>Sumber</h2><ol>{sources}</ol></section>
<section><h2>Google Search Suggestions</h2>{suggestions}</section>
<p><small>Hasil ini hanya tersedia selama sesi SIBIMA-AI berlangsung.</small></p></body></html>'''


class SearchBrowser:
    def __init__(self):
        self._pages: dict[str, str] = {}
        self._server = None
        self._thread = None

    def open(self, payload: dict) -> tuple[str, bool]:
        if self._server is None:
            owner = self
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass  # Do not log grounded results or request URLs.

                def do_GET(self):
                    path = urlsplit(self.path).path
                    html = owner._pages.get(path)
                    if html is None:
                        self.send_response(404)
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        return
                    data = html.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store, private, max-age=0")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
            self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            self._thread = Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
        token = token_urlsafe(18)
        path = "/" + token
        self._pages[path] = render_grounded_html(payload)
        url = f"http://127.0.0.1:{self._server.server_port}{path}"
        try:
            opened = bool(webbrowser.open(url))
        except Exception:
            opened = False
        return url, opened

    def close(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            if self._thread is not None:
                self._thread.join(timeout=2)
            self._server = None
            self._thread = None
        self._pages.clear()
