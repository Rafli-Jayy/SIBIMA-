"""Validasi input. Melempar DataTidakValid jika input salah."""
"""Validasi input aplikasi SIBIMA."""

import math
import re

from email_validator import EmailNotValidError, validate_email

from app.utils.exceptions import DataTidakValid


def validasi_username(username: str) -> str:
    """Username harus 4-30 karakter, tanpa spasi."""
    if not isinstance(username, str):
        raise DataTidakValid("Username harus berupa teks.")

    username = username.strip()

    if not re.fullmatch(r"[A-Za-z0-9_]{4,30}", username):
        raise DataTidakValid(
            "Username 4-30 karakter: huruf, angka, atau underscore."
        )

    return username


def validasi_email(email: str) -> str:
    """Memvalidasi dan menormalisasi alamat email."""
    if not isinstance(email, str) or not email.strip():
        raise DataTidakValid("Email wajib diisi.")

    try:
        return validate_email(
            email.strip(),
            check_deliverability=False,
        ).normalized
    except EmailNotValidError as exc:
        raise DataTidakValid("Format email tidak valid.") from exc


def validasi_password(password: str) -> str:
    """Memeriksa panjang dan komposisi password."""
    if not isinstance(password, str):
        raise DataTidakValid("Password harus berupa teks.")

    if not 8 <= len(password) <= 64:
        raise DataTidakValid(
            "Password harus terdiri dari 8-64 karakter."
        )

    if len(password.encode("utf-8")) > 72:
        raise DataTidakValid(
            "Password terlalu panjang dalam UTF-8 untuk bcrypt "
            "(maksimal 72 byte)."
        )

    if not re.search(r"[A-Za-z]", password):
        raise DataTidakValid(
            "Password harus mengandung minimal satu huruf."
        )

    if not re.search(r"[0-9]", password):
        raise DataTidakValid(
            "Password harus mengandung minimal satu angka."
        )

    return password


def validasi_no_hp(no_hp: str) -> str:
    """Memvalidasi nomor telepon seluler Indonesia."""
    if not isinstance(no_hp, str):
        raise DataTidakValid("Nomor HP harus berupa teks.")

    bersih = re.sub(r"[\s-]", "", no_hp)

    if not re.fullmatch(r"(?:\+62|62|0)8\d{8,11}", bersih):
        raise DataTidakValid(
            "Nomor HP tidak valid, contoh: 081234567890."
        )

    return bersih


def validasi_nominal(teks) -> int:
    """Memvalidasi nominal bilangan bulat positif."""
    bersih = re.sub(r"[.\s]", "", str(teks).strip())

    if not re.fullmatch(r"[0-9]+", bersih):
        raise DataTidakValid("Nominal harus berupa angka bulat.")

    nilai = int(bersih)

    if nilai <= 0:
        raise DataTidakValid("Nominal harus lebih dari 0.")

    return nilai


def validasi_nilai(teks) -> float:
    """Memvalidasi nilai akademik dari 0 sampai 100."""
    try:
        nilai = float(str(teks).replace(",", ".").strip())
    except (ValueError, TypeError):
        raise DataTidakValid("Nilai harus berupa angka.")

    if not math.isfinite(nilai) or not 0 <= nilai <= 100:
        raise DataTidakValid(
            "Nilai harus berupa angka antara 0 sampai 100."
        )

    return nilai
