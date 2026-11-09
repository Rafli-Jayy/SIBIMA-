from app.ui.ai.chat_state import ChatState, Message
import pytest


def test_recent_and_pages():
    state = ChatState(role="tutor", max_messages=20)
    for x in range(8):
        state.add(Message("user", str(x)))
    assert [m.content for m in state.recent(3)] == ["5", "6", "7"]
    assert [m.content for m in state.page(0, 3)] == ["5", "6", "7"]
    assert [m.content for m in state.page(1, 3)] == ["2", "3", "4"]
    assert state.page_count(3) == 3
    state.clear()
    assert state.messages == []


def test_bounded_messages():
    state = ChatState(max_messages=3)
    for i in range(5):
        state.add(Message("assistant", str(i)))
    assert [m.content for m in state.messages] == ["2", "3", "4"]


def test_invalid_role_sender_and_page():
    with pytest.raises(ValueError):
        ChatState(role="superadmin")
    with pytest.raises(ValueError):
        Message(sender="system", content="a")
    with pytest.raises(ValueError):
        ChatState().page(-1)
