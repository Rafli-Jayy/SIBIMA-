"""Patch 2H: offline tests (no network, no Gemini key, no PostgreSQL)."""
from io import StringIO
from types import SimpleNamespace as NS
from urllib.request import urlopen

from rich.console import Console

from app.services.gemini_client import GeminiClient, GeminiOptions
from app.services.ai_service import AIService
from app.services.search_grounding import citations_from_step, suggestions_from_step
from app.ui.ai.chat_screen import ChatScreen
from app.ui.ai.search_browser import render_grounded_html, SearchBrowser
from app.ui.ai.streaming_renderer import play_stream


def ev(name, **fields):
    return NS(event_type=name, **fields)


def st(index, kind):
    return ev("step.start", index=index, step=NS(type=kind))


def dt(index, value):
    return ev("step.delta", index=index, delta=NS(type="text", text=value))


def stopped(index, step=None):
    return ev("step.stop", index=index, step=step)


class Api:
    def __init__(self, streams):
        self.streams = list(streams)
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        stream = self.streams.pop(0)
        return iter(stream)


class FakeSDK:
    def __init__(self, streams):
        self.interactions = Api(streams)


def make(streams, enabled):
    fake = FakeSDK(streams)
    adapter = GeminiClient(GeminiOptions(api_key="test", model="gemini-3.5-flash-lite",
                                         google_search_enabled=enabled, max_attempts=1), client=fake)
    return AIService("admin", client=adapter), fake


def grounded_stream():
    result = NS(type="google_search_result", result=[NS(search_suggestions='<div><a href="https://google.com/search?q=x">Google</a></div>')])
    output = NS(type="model_output", content=[NS(type="text", annotations=[NS(type="url_citation", url="https://example.org/a", title="Sumber A")])])
    return [
        ev("interaction.created"),
        st(0, "thought"), ev("step.delta", index=0, delta=NS(type="thought_signature", signature="SIG")), stopped(0),
        st(1, "google_search_call"), stopped(1),
        st(2, "google_search_result"), stopped(2, result),
        st(3, "model_output"), dt(3, "Hasil Google: <b>penting</b>."), stopped(3, output),
        ev("interaction.completed", interaction=NS(status="completed")),
    ]


def test_feature_disabled_keeps_normal_stream_and_no_tools():
    svc, fake = make([[st(0, "model_output"), dt(0, "Halo"), stopped(0), ev("interaction.completed")]], False)
    out = list(svc.stream("Halo", "admin"))
    assert [x.kind for x in out] == ["text_chunk", "completed"]
    assert "tools" not in fake.interactions.calls[0]
    assert fake.interactions.calls[0]["store"] is False


def test_feature_enabled_does_not_force_search():
    svc, fake = make([[st(0, "model_output"), dt(0, "Halo"), stopped(0), ev("interaction.completed")]], True)
    out = list(svc.stream("Halo", "admin"))
    assert [x.kind for x in out] == ["text_chunk", "completed"]
    assert fake.interactions.calls[0]["tools"] == [{"type": "google_search"}]


def test_google_search_flow_never_streams_grounded_text_into_cli():
    svc, fake = make([grounded_stream()], True)
    out = list(svc.stream("Cari data terkini", "admin"))
    assert [x.kind for x in out] == ["search_started", "search_finished", "completed"]
    data = out[-1].payload
    assert data["kind"] == "search"
    assert "Hasil Google:" not in data["content"]
    result = data["data"]["search_result"]
    assert result["answer"].startswith("Hasil Google:")
    assert result["citations"] == [{"url": "https://example.org/a", "title": "Sumber A"}]
    assert "Google" in result["search_suggestions"][0]
    assert all(step["type"] not in ("google_search_call", "google_search_result") for step in svc.history)
    assert fake.interactions.calls[0]["store"] is False
    assert "Hasil Google" not in str([e for e in out if e.kind != "completed"])


def test_grounded_result_falls_back_to_completed_interaction_steps():
    stream = grounded_stream()
    stream[-1] = ev("interaction.completed", interaction=NS(status="completed", steps=[
        NS(type="google_search_result", result=[NS(search_suggestions="<div>widget</div>")]),
        NS(type="model_output", content=[NS(type="text", annotations=[NS(type="url_citation", url="https://example.org/z", title="Web")])]),
    ]))
    # Step.stop metadata is also present, duplicate sources should be deduplicated.
    svc, _ = make([stream], True)
    data = list(svc.stream("news", "admin"))[-1].payload["data"]["search_result"]
    assert len(data["citations"]) == 2
    assert "widget" in data["search_suggestions"][-1]


def test_disallowed_search_step_rejected_without_enabled_tool():
    svc, _ = make([[st(0, "google_search_call"), stopped(0), ev("interaction.completed")]], False)
    out = list(svc.stream("halo", "admin"))
    assert out[-1].kind == "error"
    assert "search-tidak-diaktifkan" in out[-1].payload


def test_search_failure_never_retried_even_without_text_output():
    class Temporary(Exception):
        code = 503
    events = [st(0, "google_search_call")]
    class Broken:
        def __iter__(self):
            yield from events
            raise Temporary("503 private server detail")
    fake = FakeSDK([Broken()])
    adapter = GeminiClient(GeminiOptions(api_key="test", google_search_enabled=True, max_attempts=3), client=fake)
    out = list(adapter.stream([], "Pertanyaan rahasia", "Konteks rahasia"))
    assert [x.kind for x in out] == ["search_started", "error"]
    assert len(fake.interactions.calls) == 1
    assert "Pertanyaan rahasia" not in out[-1].payload


def test_sources_filter_unsafe_protocol_and_deduplicate():
    step = NS(content=[NS(type="text", annotations=[
        NS(type="url_citation", url="javascript:alert(1)", title="bad"),
        NS(type="url_citation", url="https://example.org", title="safe"),
    ])])
    assert citations_from_step(step) == [{"url": "https://example.org", "title": "safe"}]
    assert suggestions_from_step(NS(result=[NS(search_suggestions='<div id="x">Widget</div>')])) == ['<div id="x">Widget</div>']
    html = render_grounded_html({"answer": '<script>alert("injection")</script>',
                                 "citations": citations_from_step(step),
                                 "search_suggestions": ['<div id="x">Widget</div>']})
    assert '&lt;script&gt;alert(' in html
    assert 'javascript:alert' not in html
    assert 'srcdoc=' in html
    assert '&lt;div id=&quot;x&quot;&gt;Widget&lt;/div&gt;' in html


def test_ephemeral_browser_loopback_and_no_cache(monkeypatch):
    monkeypatch.setattr('webbrowser.open', lambda url: False)
    viewer = SearchBrowser()
    url, opened = viewer.open({'answer': 'jawaban', 'citations': [], 'search_suggestions': ['<div>Widget</div>']})
    assert url.startswith('http://127.0.0.1:')
    assert opened is False
    with urlopen(url, timeout=2) as response:
        body = response.read().decode('utf-8')
        assert response.headers['Cache-Control'].startswith('no-store')
        assert 'jawaban' in body
        assert 'srcdoc=' in body
    viewer.close()
    assert viewer._pages == {}


def test_ui_keeps_browser_grounded_text_out_of_terminal(monkeypatch):
    from app.ui.ai.mock_responder import MockEvent
    import app.ui.ai.search_browser as browser
    monkeypatch.setattr(browser.webbrowser, 'open', lambda url: False)
    c = Console(file=StringIO(), width=110, force_terminal=False)
    screen = ChatScreen(role='admin', console=c, view_mode='scroll', online=True)
    result = {'kind':'search','content':'placeholder', 'data':{'search_result':{
        'answer':'SENSITIVE_GROUNDED_CONTENT', 'citations':[], 'search_suggestions':['<div>Suggestion</div>']}}}
    output = screen._present_grounded_result(result)
    assert output['kind'] == 'markdown'
    assert 'SENSITIVE_GROUNDED_CONTENT' not in output['content']
    assert '127.0.0.1' in output['content']
    screen._reset_conversation()
    assert screen._search_browser is None


def test_spinner_handles_search_events():
    from app.ui.ai.mock_responder import MockEvent
    c = Console(file=StringIO(), force_terminal=False, width=120)
    out = play_stream(c, [MockEvent('search_started', None), MockEvent('search_finished', None),
                          MockEvent('completed', {'kind':'search', 'content':'Hasil tersedia', 'data':{}})], delay=0)
    assert out['kind'] == 'search'
    assert 'Hasil tersedia' in out['content']


def test_google_search_refuses_to_show_result_without_required_suggestions():
    stream = grounded_stream()
    stream[7] = stopped(2, NS(type="google_search_result", result=[]))
    svc, _ = make([stream], True)
    out = list(svc.stream("Cari", "admin"))
    assert out[-1].kind == "error"
    assert "saran-google-tidak-tersedia" in out[-1].payload
    assert svc.history == []


def test_delta_citations_can_be_recovered():
    stream = grounded_stream()
    stream[9] = ev("step.delta", index=3, delta=NS(type="text", text="Jawaban", annotations=[
        NS(type="url_citation", url="https://another.org/sumber", title="Tambahan")]))
    svc, _ = make([stream], True)
    out = list(svc.stream("Cari", "admin"))
    sources = out[-1].payload["data"]["search_result"]["citations"]
    assert {s["url"] for s in sources} == {"https://example.org/a", "https://another.org/sumber"}
