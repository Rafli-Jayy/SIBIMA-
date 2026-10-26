from decimal import Decimal

import pytest

from app.utils.academic_validation import (
    id_positif,
    jenis_nilai,
    nilai_angka,
    status_absensi,
    teks_catatan,
    tanggal_valid,
)


@pytest.mark.parametrize(("value", "expected"), [(1, 1), ("2", 2), (" 17 ", 17)])
def test_id_positif_menerima_integer_positif(value, expected):
    assert id_positif(value) == expected


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "1.5", "abc", None])
def test_id_positif_menolak_input_invalid(value):
    with pytest.raises(ValueError):
        id_positif(value)


@pytest.mark.parametrize("value", ["tugas", " KUIS ", "uts", "uas"])
def test_jenis_nilai_menerima_jenis_yang_didukung(value):
    assert jenis_nilai(value).strip() in {"tugas", "kuis", "uts", "uas"}


@pytest.mark.parametrize("value", ["ujian", "ujian_ai", "", None, 1])
def test_jenis_nilai_menolak_jenis_lain(value):
    with pytest.raises(ValueError):
        jenis_nilai(value)


def test_nilai_angka_menerima_comma_decimal():
    assert nilai_angka("87,5") == Decimal("87.50")


@pytest.mark.parametrize("value", ["-0.1", "100.01", "NaN", "Infinity", True, None, "bukan angka"])
def test_nilai_angka_menolak_input_invalid(value):
    with pytest.raises(ValueError):
        nilai_angka(value)


@pytest.mark.parametrize(("value", "expected"), [("h", "H"), (" I ", "I"), ("s", "S"), ("A", "A")])
def test_status_absensi_normalisasi(value, expected):
    assert status_absensi(value) == expected


@pytest.mark.parametrize("value", ["M", "hadir", "", None, 4])
def test_status_absensi_menolak_status_invalid(value):
    with pytest.raises(ValueError):
        status_absensi(value)


def test_teks_catatan_opsional_dan_wajib():
    assert teks_catatan("   ", "Judul", 20) is None
    assert teks_catatan("  Materi  ", "Topik", 20, wajib=True) == "Materi"
    with pytest.raises(ValueError):
        teks_catatan("", "Topik", 20, wajib=True)
    with pytest.raises(ValueError):
        teks_catatan("x" * 21, "Topik", 20)


def test_tanggal_valid():
    assert str(tanggal_valid("2026-10-26")) == "2026-10-26"
    assert tanggal_valid(None) is None
    with pytest.raises(ValueError):
        tanggal_valid("26-10-2026")
