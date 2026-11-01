"""Regresi ekspor CSV, tanpa database atau akses jaringan."""

import pytest

from app.utils.csv_safety import nilai_csv_aman


@pytest.mark.parametrize("value", [
    "=1+1", "+SUM(A1:A2)", "-5+2", "@SUM(A1)",
    "   =HYPERLINK(\"https://example.invalid\")",
    "\t=1+1", "\r+2+3", "\n@SUM(A1)",
])
def test_input_formula_dinetralisasi(value):
    assert nilai_csv_aman(value) == "'" + value


@pytest.mark.parametrize("value", ["IPA", "Kelas A", "123 ABC", "  normal"])
def test_teks_biasa_tidak_berubah(value):
    assert nilai_csv_aman(value) == value


def test_angka_negatif_tetap_angka_bukan_formula():
    assert nilai_csv_aman(-2500) == "-2500"


def test_nilai_none_berubah_kosong():
    assert nilai_csv_aman(None) == ""
