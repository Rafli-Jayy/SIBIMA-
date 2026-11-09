from app.ui.ai.mock_responder import MockResponder


def test_mock_gives_honest_limited_fallback():
    result = MockResponder().reply("pertanyaan bebas", "siswa")
    assert result["kind"] == "markdown"
    assert "pratinjau" in result["content"].casefold()
    assert "Gemini" not in MockResponder().reply("algoritma", "siswa")["content"]


def test_role_limits_mock_action():
    responder = MockResponder()
    assert responder.reply("buat pengumuman", "siswa")["kind"] == "markdown"
    assert responder.reply("buat pengumuman", "tutor")["kind"] == "action"
    assert responder.reply("buat pengumuman", "admin")["data"]["action"] == "buat_pengumuman_demo"


def test_event_completes_with_structured_data():
    events = list(MockResponder().stream("jadwal", "siswa"))
    assert any(e.kind == "text_chunk" for e in events)
    assert events[-1].kind == "completed"
    assert events[-1].payload["kind"] == "table"
    assert events[-1].payload["data"]["rows"]
    assert "ilustrasi" in events[-1].payload["content"].casefold()


def test_error_scenario():
    assert MockResponder().reply("uji error", "siswa")["kind"] == "error"


def test_material_explanation_is_useful_and_not_overbranded():
    content = MockResponder().reply("jelaskan algoritma", "siswa")["content"]
    assert "Algoritma" in content
    assert "[DEMO]" not in content
