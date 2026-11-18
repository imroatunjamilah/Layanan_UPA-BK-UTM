"""Konfigurasi aplikasi dibaca dari variabel lingkungan / file .env."""
import os
import warnings
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


class Settings:
    """Pengaturan global aplikasi (diambil dari environment)."""

    APP_NAME = "UPA BK UTM - Layanan Konseling Mahasiswa"
    APP_VERSION = "0.1.0"

    APP_ENV = _get("APP_ENV", "development").lower()
    BASE_DIR = BASE_DIR

    # Keamanan
    SECRET_KEY = _get("SECRET_KEY", "dev-secret-key-CHANGE-ME-please")
    TOKEN_EXPIRE_MINUTES = int(_get("TOKEN_EXPIRE_MINUTES", "480"))

    # Database
    DATABASE_URL = _get("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'upabk.db').as_posix()}")
    # Pengaman: bila DATABASE_URL lingkungan tidak dikenali SQLAlchemy (skema aneh),
    # kembali ke SQLite lokal agar aplikasi tetap bisa berjalan.
    _KNOWN_DB_PREFIXES = ("sqlite", "postgresql", "postgres", "mysql", "mariadb", "oracle", "mssql")
    if not DATABASE_URL.startswith(_KNOWN_DB_PREFIXES):
        warnings.warn(
            f"DATABASE_URL tidak dikenal ('{DATABASE_URL[:24]}...'). Memakai SQLite lokal sebagai gantinya."
        )
        DATABASE_URL = f"sqlite:///{(BASE_DIR / 'upabk.db').as_posix()}"

    # Admin awal pengembangan (dipakai startup dev & seed_data.py)
    ADMIN_USERNAME = _get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = _get("ADMIN_PASSWORD", "admin123")

    # LLM
    LLM_PROVIDER = _get("LLM_PROVIDER", "mock").lower()
    LLM_BASE_URL = _get("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL = _get("LLM_MODEL", "gpt-4o-mini")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
    LLM_TIMEOUT = int(_get("LLM_TIMEOUT_SECONDS", "20"))
    LLM_ALLOW_EXTERNAL = _get("LLM_ALLOW_EXTERNAL", "false").lower() in ("1", "true", "yes")

    # WhatsApp OTP (reset kata sandi admin)
    # WA_PROVIDER: "mock" = kode hanya dicatat di log server (offline, demo/development);
    #              "fonnte" = kirim nyata via API Fonnte (isi WA_API_TOKEN di .env).
    WA_PROVIDER = _get("WA_PROVIDER", "mock").lower()
    WA_API_URL = _get("WA_API_URL", "https://api.fonnte.com/send")
    WA_API_TOKEN = os.getenv("WA_API_TOKEN", "").strip()
    OTP_TTL_MINUTES = int(_get("OTP_TTL_MINUTES", "10"))       # masa berlaku kode
    OTP_MAX_ATTEMPTS = int(_get("OTP_MAX_ATTEMPTS", "5"))      # batas tebak kode
    OTP_RESEND_SECONDS = int(_get("OTP_RESEND_SECONDS", "60"))  # jeda minimal kirim ulang


settings = Settings()

if settings.APP_ENV == "development" and settings.SECRET_KEY.startswith("dev-secret"):
    warnings.warn(
        "SECRET_KEY masih nilai default pengembangan. "
        "Untuk produksi, wajib mengganti lewat variabel lingkungan.",
        stacklevel=1,
    )
