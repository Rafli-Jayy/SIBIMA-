"""Extract Google Search references without logging or persisting provider results.

The required Search Suggestions are not safe to render as ANSI / Rich markup.
They are displayed alongside the answer by a local, in-memory browser viewer.
"""
from __future__ import annotations

from urllib.parse import urlsplit
from typing import Any


def get_field(item: Any, key: str, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default) if item is not None else default


def valid_source_url(value: Any) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        p = urlsplit(value)
        return p.scheme in {"https", "http"} and bool(p.netloc) and not p.username and not p.password
    except ValueError:
        return False


def citations_from_step(step: Any) -> list[dict[str, str]]:
    citations = []
    for block in get_field(step, "content", []) or []:
        if get_field(block, "type") != "text":
            continue
        for anno in get_field(block, "annotations", []) or []:
            if get_field(anno, "type") not in {None, "url_citation"}:
                continue
            url = get_field(anno, "url") or get_field(anno, "uri")
            if not valid_source_url(url):
                continue
            title = get_field(anno, "title") or urlsplit(url).netloc
            citations.append({"url": url, "title": str(title)[:160]})
    return citations


def suggestions_from_step(step: Any) -> list[str]:
    suggestions = []
    # Modern SDK: GoogleSearchResultStep.result is a list of result items.
    for item in get_field(step, "result", []) or []:
        html = get_field(item, "search_suggestions")
        if isinstance(html, str) and html.strip() and len(html) <= 200_000:
            suggestions.append(html)
    return suggestions[:5]


def deduplicate_citations(items: list[dict]) -> list[dict]:
    seen = set()
    output = []
    for item in items:
        url = item.get("url")
        if valid_source_url(url) and url not in seen:
            output.append({"url": url, "title": str(item.get("title", url))[:160]})
            seen.add(url)
        if len(output) >= 15:
            break
    return output
