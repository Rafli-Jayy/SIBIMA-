from datetime import date, datetime
from decimal import Decimal

from app.utils.csv_safety import nilai_csv_aman


def test_none_and_dates_are_serialized():
    assert nilai_csv_aman(None) == ""
    assert nilai_csv_aman(date(2026, 10, 26)) == "2026-10-26"
    assert nilai_csv_aman(datetime(2026, 10, 26, 9, 30)) == "2026-10-26T09:30:00"


def test_numbers_are_not_treated_as_spreadsheet_formulas():
    assert nilai_csv_aman(125) == "125"
    assert nilai_csv_aman(Decimal("-125.50")) == "-125.50"


def test_formula_like_text_is_neutralized():
    assert nilai_csv_aman("=HYPERLINK(\"https://example.invalid\")").startswith("'=")
    assert nilai_csv_aman(" +SUM(A1:A4)") == "' +SUM(A1:A4)"
    assert nilai_csv_aman("@SUM(A1)") == "'@SUM(A1)"


def test_ordinary_text_is_preserved():
    assert nilai_csv_aman("IPA SMA") == "IPA SMA"
    assert nilai_csv_aman("PENGUMUMAN_DIBUAT") == "PENGUMUMAN_DIBUAT"
