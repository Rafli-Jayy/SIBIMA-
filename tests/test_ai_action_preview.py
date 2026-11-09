from io import StringIO
from rich.console import Console
from app.ui.ai.action_preview import make_preview, ALLOWED_ACTIONS


def test_preview_is_display_only():
    assert ALLOWED_ACTIONS == {"buat_pengumuman_demo"}
    buf = StringIO()
    Console(file=buf, width=85, force_terminal=False).print(make_preview({"action": "buat_pengumuman_demo", "target": "Tutor", "title": "Info", "body": "Materi"}))
    assert "PRATINJAU" in buf.getvalue()
    assert "Info" in buf.getvalue()
