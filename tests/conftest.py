"""Tutup resource DB yang dibuka test suite sebelum Python shutdown."""

import sys


def pytest_unconfigure(config):
    """Cegah psycopg_pool worker tertinggal saat proses pytest berakhir."""
    db_module = sys.modules.get("app.db")
    if db_module is None:
        return
    close_pool = getattr(db_module, "tutup_pool", None)
    if callable(close_pool):
        close_pool()
