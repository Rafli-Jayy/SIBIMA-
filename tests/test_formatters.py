from datetime import date

from app.utils.formatters import persen, rupiah, tanggal


def test_rupiah():
    assert rupiah(450000) == "Rp 450.000"
    assert rupiah(0) == "Rp 0"


def test_tanggal():
    assert tanggal(date(2026, 10, 21)) == "21 Okt 2026"


def test_persen():
    assert persen(91.04) == "91.0%"
