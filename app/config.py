"""Konfigurasi aplikasi. Semua nilai dibaca dari file .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

# OTP
OTP_MODE = os.getenv("OTP_MODE", "simulasi")          # simulasi | email
OTP_EXPIRE_MINUTES = int(os.getenv("OTP_EXPIRE_MINUTES", "5"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "3"))

# Login
MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "3"))
LOCK_MINUTES = int(os.getenv("LOCK_MINUTES", "5"))

# Simulasi pembayaran: persentase keberhasilan (0-100), tanpa transaksi uang nyata.
PAYMENT_SIMULATION_SUCCESS_RATE = int(os.getenv("PAYMENT_SIMULATION_SUCCESS_RATE", "90"))
if not 0 <= PAYMENT_SIMULATION_SUCCESS_RATE <= 100:
    raise ValueError("PAYMENT_SIMULATION_SUCCESS_RATE harus berada di antara 0 dan 100.")

# Email
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Folder keluaran
BUKTI_DIR = BASE_DIR / "bukti"
