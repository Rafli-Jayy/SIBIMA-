"""State percakapan hanya di memori, tidak dipersist ke disk."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

ALLOWED_ROLES = {"admin", "tutor", "siswa"}
ALLOWED_SENDERS = {"user", "assistant"}
ALLOWED_KINDS = {"markdown", "table", "action", "error"}


@dataclass(frozen=True)
class Message:
    sender: str
    content: str
    kind: str = "markdown"
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.sender not in ALLOWED_SENDERS:
            raise ValueError("Pengirim pesan tidak dikenal")
        if self.kind not in ALLOWED_KINDS:
            raise ValueError("Jenis pesan tidak dikenal")


@dataclass
class ChatState:
    role: str = "siswa"
    messages: List[Message] = field(default_factory=list)
    max_messages: int = 60

    def __post_init__(self) -> None:
        if self.role not in ALLOWED_ROLES:
            raise ValueError("Role demo tidak valid")
        if self.max_messages < 2:
            raise ValueError("max_messages minimal 2")

    def add(self, message: Message) -> None:
        self.messages.append(message)
        if len(self.messages) > self.max_messages:
            del self.messages[: len(self.messages) - self.max_messages]

    def recent(self, limit: int = 4) -> List[Message]:
        return self.messages[-max(0, limit):] if limit > 0 else []

    def clear(self) -> None:
        self.messages.clear()

    def page(self, page: int, page_size: int = 5) -> List[Message]:
        """Page 0 = terbaru; hasil tampil dalam urutan kronologis."""
        if page < 0 or page_size < 1:
            raise ValueError("Parameter halaman tidak valid")
        end = max(0, len(self.messages) - page * page_size)
        start = max(0, end - page_size)
        return self.messages[start:end]

    def page_count(self, page_size: int = 5) -> int:
        return max(1, (len(self.messages) + page_size - 1) // page_size)
