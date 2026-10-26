import pytest

from app.utils.student_validation import nomor_hp_opsional, teks_opsional, validasi_profil


def test_teks_opsional_normalisasi_dan_kosong():
    assert teks_opsional("  SMA  ", "Jenjang", 20) == "SMA"
    assert teks_opsional("   ", "Jenjang", 20) is None
    assert teks_opsional(None, "Jenjang", 20) is None


def test_teks_opsional_menolak_panjang_berlebih():
    with pytest.raises(ValueError, match="maksimal"):
        teks_opsional("X" * 21, "Jenjang", 20)


def test_teks_opsional_menolak_tipe_tidak_valid():
    with pytest.raises(ValueError, match="teks"):
        teks_opsional(42, "Sekolah", 100)


def test_nomor_hp_opsional_normalisasi_format_indonesia():
    assert nomor_hp_opsional("0812 3456 7890") == "081234567890"
    assert nomor_hp_opsional("+6281234567890") == "+6281234567890"
    assert nomor_hp_opsional("") is None


def test_nomor_hp_opsional_menolak_format_salah():
    with pytest.raises(ValueError, match="Nomor HP tidak valid"):
        nomor_hp_opsional("123456")


def test_validasi_profil_mempertahankan_field_yang_diizinkan():
    result = validasi_profil({
        "jenjang": "SMA", "sekolah": "SMA Negeri Glenmore",
        "no_hp": "081234567890", "nama_wali": "Bapak Rafli",
    })
    assert result == {
        "jenjang": "SMA", "sekolah": "SMA Negeri Glenmore",
        "no_hp": "081234567890", "nama_wali": "Bapak Rafli",
    }


def test_validasi_profil_menolak_field_ekstra():
    with pytest.raises(ValueError, match="tidak lengkap"):
        validasi_profil({"jenjang": "SMA", "nama_lengkap": "ubah nama akun"})
