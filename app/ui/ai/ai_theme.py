"""Tema dan geometri ChatGPT-inspired SIBIMA-AI CLI.

Semua elemen memakai satu *workspace* dengan lebar terbatas dan terpusat.
Questionary memakai gutter yang sama agar input tidak kembali ke kolom paling kiri.
"""
from rich.console import Console

BORDER = "cyan"
MUTED = "dim"
SUCCESS = "green"
WARN = "yellow"
ERROR = "red"
WORKSPACE_MAX = 94
USER_BUBBLE_MAX = 62
AI_BUBBLE_MAX = 88
PREVIEW_MAX = 78


def fit_width(console_width: int, cap: int = WORKSPACE_MAX) -> int:
    """Workspace tidak memenuhi layar, termasuk ketika terminal diperkecil."""
    available = max(1, int(console_width) - 4)
    return min(cap, available)


def workspace_left(console_width: int) -> int:
    """Gutter kiri sehingga Rich dan Questionary mulai pada kolom serupa."""
    return max(0, (int(console_width) - fit_width(console_width)) // 2)


def prompt_prefix(console_width: int) -> str:
    """Prefix untuk qmark Questionary: indentasi mengikuti workspace Rich."""
    return " " * workspace_left(console_width) + "›"


def make_console() -> Console:
    return Console(highlight=False, soft_wrap=False)


def question_style():
    from questionary import Style
    return Style([
        ("qmark", "fg:#57C9DC bold"),
        ("question", "fg:#CED5DE"),
        ("answer", "fg:#F2F4F7"),
        ("pointer", "fg:#57C9DC bold"),
        ("highlighted", "fg:#57C9DC bold"),
        ("selected", "fg:#57C9DC"),
        ("instruction", "fg:#8A929E"),
        ("text", "fg:#CED5DE"),
    ])
