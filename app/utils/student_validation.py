"""Validasi ringan untuk data profil siswa, tanpa akses database."""

import re


BATAS_PROFIL = {
    "jenjang": 20,
    "sekolah": 100,
    "no_hp": 20,
    "nama_wali": 100,
}


def teks_opsional(value, label: str, maksimum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} harus berupa teks.")
    bersih = value.strip()
    if len(bersih) > maksimum:
        raise ValueError(f"{label} maksimal {maksimum} karakter.")
    if any(ord(char) < 32 and char not in "\t" for char in bersih):
        raise ValueError(f"{label} mengandung karakter yang tidak diperbolehkan.")
    return bersih or None


def nomor_hp_opsional(value: str | None) -> str | None:
    """Nomor HP opsional dengan format seluler Indonesia yang didukung aplikasi."""
    hp = teks_opsional(value, "Nomor HP", BATAS_PROFIL["no_hp"])
    if hp is None:
        return None
    normalized = re.sub(r"[\s-]", "", hp)
    if not re.fullmatch(r"(?:\+62|62|0)8\d{8,11}", normalized):
        raise ValueError("Nomor HP tidak valid, contoh: 081234567890.")
    return normalized


def validasi_profil(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Data profil tidak valid.")
    expected = set(BATAS_PROFIL)
    if set(data) != expected:
        raise ValueError("Data profil tidak lengkap.")
    return {
        "jenjang": teks_opsional(data["jenjang"], "Jenjang", BATAS_PROFIL["jenjang"]),
        "sekolah": teks_opsional(data["sekolah"], "Sekolah", BATAS_PROFIL["sekolah"]),
        "no_hp": nomor_hp_opsional(data["no_hp"]),
        "nama_wali": teks_opsional(data["nama_wali"], "Nama wali", BATAS_PROFIL["nama_wali"]),
    }
