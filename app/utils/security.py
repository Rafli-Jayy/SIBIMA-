
"""Hash password, pembuatan OTP, dan verifikasi kode."""

import re
import secrets

import bcrypt


MAX_BCRYPT_BYTES = 72
MIN_OTP_LENGTH = 4
MAX_OTP_LENGTH = 10


def hash_password(password: str) -> str:
    """Hash password menggunakan bcrypt dan mengembalikan string hash."""
    if not isinstance(password, str):
        raise ValueError("Password harus berupa teks.")

    data = password.encode("utf-8")

    if not data:
        raise ValueError("Password tidak boleh kosong.")

    if len(data) > MAX_BCRYPT_BYTES:
        raise ValueError("Password maksimal 72 byte UTF-8.")

    return bcrypt.hashpw(
        data,
        bcrypt.gensalt(),
    ).decode("utf-8")


def verifikasi_password(password: str, hashed: str) -> bool:
    """Memeriksa password terhadap hash bcrypt."""
    if not isinstance(password, str):
        return False

    if not isinstance(hashed, str) or not hashed:
        return False

    data = password.encode("utf-8")

    if len(data) > MAX_BCRYPT_BYTES:
        return False

    try:
        return bcrypt.checkpw(
            data,
            hashed.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def buat_otp(panjang: int = 6) -> str:
    """Membuat OTP numerik dengan generator acak yang aman."""
    if type(panjang) is not int:
        raise ValueError("Panjang OTP harus berupa bilangan bulat.")

    if not MIN_OTP_LENGTH <= panjang <= MAX_OTP_LENGTH:
        raise ValueError(
            f"Panjang OTP harus {MIN_OTP_LENGTH}-{MAX_OTP_LENGTH} digit."
        )

    return "".join(
        str(secrets.randbelow(10))
        for _ in range(panjang)
    )


def hash_otp(kode: str) -> str:
    """Menyimpan OTP dalam bentuk hash bcrypt, bukan teks asli."""
    if not isinstance(kode, str):
        raise ValueError("Kode OTP harus berupa teks.")

    if not re.fullmatch(r"\d{4,10}", kode):
        raise ValueError("Kode OTP harus terdiri dari 4-10 digit.")

    return bcrypt.hashpw(
        kode.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def verifikasi_otp(kode: str, hashed: str) -> bool:
    """Memeriksa kode OTP terhadap hash yang disimpan."""
    if not isinstance(kode, str) or not isinstance(hashed, str):
        return False

    if not re.fullmatch(r"\d{4,10}", kode):
        return False

    try:
        return bcrypt.checkpw(
            kode.encode("utf-8"),
            hashed.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False