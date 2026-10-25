import pytest

from app.utils.exceptions import DataTidakValid
from app.utils.validators import (
    validasi_email,
    validasi_no_hp,
    validasi_nominal,
    validasi_nilai,
    validasi_password,
    validasi_username,
)


def test_username_valid():
    assert validasi_username("budi01") == "budi01"


@pytest.mark.parametrize("u", ["ab", "budi santoso", "budi@01", "x" * 31])
def test_username_tidak_valid(u):
    with pytest.raises(DataTidakValid):
        validasi_username(u)


def test_email():
    assert validasi_email("budi@email.com") == "budi@email.com"
    with pytest.raises(DataTidakValid):
        validasi_email("bukan-email")


def test_password():
    assert validasi_password("rahasia123") == "rahasia123"
    with pytest.raises(DataTidakValid):
        validasi_password("pendek1")
    with pytest.raises(DataTidakValid):
        validasi_password("hanyahuruf")


def test_no_hp():
    assert validasi_no_hp("0812-3456-7890") == "081234567890"
    with pytest.raises(DataTidakValid):
        validasi_no_hp("12345")


def test_nominal_dan_nilai():
    assert validasi_nominal("450.000") == 450000
    with pytest.raises(DataTidakValid):
        validasi_nominal("-5")
    assert validasi_nilai("88,5") == 88.5
    with pytest.raises(DataTidakValid):
        validasi_nilai("101")
