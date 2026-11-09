from io import StringIO
from rich.console import Console
from app.ui.ai.chat_state import ChatState, Message
from app.ui.ai.response_renderer import clean_text, render_chat, render_message, render_table


def test_control_character_removed():
    assert "\x1b" not in clean_text("halo\x1b[31m")
    assert "\x00" not in clean_text("test\x00")


def test_screen_and_rich_table_renderable():
    state = ChatState()
    state.add(Message("user", "Jadwal saya"))
    state.add(Message("assistant", "Data contoh", kind="table", data={"columns": ["Hari"], "rows": [{"Hari": "Senin"}]}))
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=85, color_system=None)
    console.print(render_chat(state))
    assert "SIBIMA AI" in buf.getvalue()
    assert "Senin" in buf.getvalue()


def test_no_raw_markup_user_input():
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=85)
    console.print(render_message(Message("user", "[red]hello[/red]")))
    assert "[red]hello[/red]" in buf.getvalue()


def test_narrow_table_fallback():
    state = ChatState()
    state.add(Message("assistant", "Data DEMO", kind="table", data={"columns":["Hari", "Program", "Jam"], "rows":[{"Hari":"Senin", "Program":"Matematika", "Jam":"15.30"}]}))
    buf=StringIO()
    Console(file=buf, force_terminal=False, width=65).print(render_chat(state, console_width=65))
    assert "Hari:" in buf.getvalue()
    assert "Matematika" in buf.getvalue()
