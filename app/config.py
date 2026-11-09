
"""Konfigurasi aplikasi. Semua nilai dibaca dari file .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Pilih database aktif: local atau supabase
DB_TARGET = os.getenv("DB_TARGET", "local").strip().lower()

if DB_TARGET not in ("local", "supabase"):
    raise ValueError(
        "DB_TARGET harus bernilai 'local' atau 'supabase'."
    )

if DB_TARGET == "local":
    # Tetap menggunakan nama variabel lokal SIBIMA yang lama.
    DB_CONFIG = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
        "dbname": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "sslmode": os.getenv("DB_SSLMODE", "prefer"),
    }
else:
    DB_CONFIG = {
        "host": os.getenv("SUPABASE_DB_HOST"),
        "port": os.getenv("SUPABASE_DB_PORT", "5432"),
        "dbname": os.getenv("SUPABASE_DB_NAME"),
        "user": os.getenv("SUPABASE_DB_USER"),
        "password": os.getenv("SUPABASE_DB_PASSWORD"),
        "sslmode": os.getenv("SUPABASE_DB_SSLMODE", "require"),
    }

# OTP
OTP_MODE = os.getenv("OTP_MODE", "simulasi")
OTP_EXPIRE_MINUTES = int(os.getenv("OTP_EXPIRE_MINUTES", "5"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "3"))

# Login
MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "3"))
LOCK_MINUTES = int(os.getenv("LOCK_MINUTES", "5"))

# Simulasi pembayaran
PAYMENT_SIMULATION_SUCCESS_RATE = int(
    os.getenv("PAYMENT_SIMULATION_SUCCESS_RATE", "90")
)
if not 0 <= PAYMENT_SIMULATION_SUCCESS_RATE <= 100:
    raise ValueError(
        "PAYMENT_SIMULATION_SUCCESS_RATE harus berada di antara 0 dan 100."
    )

# Email
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "medium").strip().lower()
GEMINI_MAX_ATTEMPTS = int(os.getenv("GEMINI_MAX_ATTEMPTS", "3"))
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "60"))
# Search is opt-in: it may require a Paid Tier project and a browser to
# display the Search Suggestions required by Google's Grounding terms.
GEMINI_GOOGLE_SEARCH_ENABLED = os.getenv("GEMINI_GOOGLE_SEARCH_ENABLED", "false").strip().lower() == "true"

# Folder keluaran
BUKTI_DIR = BASE_DIR / "bukti"
