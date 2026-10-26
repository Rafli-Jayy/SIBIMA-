"""Validasi murni untuk operasi akademik tutor; tidak mengakses database."""

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import re

JENIS_NILAI = ("tugas", "kuis", "uts", "uas")
STATUS_ABSENSI = {"H", "I", "S", "A"}


def id_positif(value, label="ID") -> int:
    if type(value) is int:
        result = value
    elif isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        result = int(value.strip())
    else:
        raise ValueError(f"{label} harus berupa angka bulat.")
    if result <= 0:
        raise ValueError(f"{label} harus lebih besar dari nol.")
    return result


def jenis_nilai(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Jenis nilai tidak valid.")
    result = value.strip().lower()
    if result not in JENIS_NILAI:
        raise ValueError("Jenis nilai harus tugas, kuis, uts, atau uas.")
    return result


def nilai_angka(value) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("Nilai harus berupa angka dari 0 sampai 100.")
    try:
        result = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValueError("Nilai harus berupa angka dari 0 sampai 100.") from None
    if not result.is_finite() or result < Decimal("0") or result > Decimal("100"):
        raise ValueError("Nilai harus berada di antara 0 dan 100.")
    try:
        return result.quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError("Nilai memiliki presisi yang terlalu panjang.") from None


def status_absensi(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Status absensi tidak valid.")
    result = value.strip().upper()
    if result not in STATUS_ABSENSI:
        raise ValueError("Status absensi harus H, I, S, atau A.")
    return result


def teks_catatan(value, label: str, batas: int | None = None, wajib: bool = False) -> str | None:
    if not isinstance(value, str):
        raise ValueError(f"{label} harus berupa teks.")
    result = value.strip()
    if wajib and not result:
        raise ValueError(f"{label} wajib diisi.")
    if batas is not None and len(result) > batas:
        raise ValueError(f"{label} maksimal {batas} karakter.")
    return result or None


def tanggal_valid(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise ValueError("Tanggal harus menggunakan format YYYY-MM-DD.")
