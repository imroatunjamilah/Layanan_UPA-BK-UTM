"""Manajer LLM: memilih penyedia, memuat system prompt terpisah, menangani error.

- System prompt disimpan pada file terpisah (app/prompts/chatbot_system_prompt.md),
  TIDAK ditanam di kode frontend (sesuai kebutuhan).
- Tanpa API key / penyedia eksternal dinonaktifkan -> otomatis fallback ke mock
  sehingga aplikasi tetap bisa dijalankan dan diuji tanpa biaya.
- Error LLM ditelan dengan rapi: pengguna menerima pesan pelayanan yang sopan;
  detail teknis hanya ke log (tanpa isi pesan mahasiswa, tanpa API key).
"""
import logging
from pathlib import Path

from .base import LLMError, LLMProvider
from .mock_provider import MockLLMProvider
from .openai_compat import OpenAICompatibleProvider
from ...config import settings

logger = logging.getLogger("app.llm")

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "chatbot_system_prompt.md"

_FALLBACK_REPLY = (
    "Maaf, sedang terjadi kendala teknis pada layanan obrolan sehingga saya belum bisa "
    "merespons dengan baik. Silakan coba beberapa saat lagi. Jika kondisi Anda mendesak, "
    "hubungi 112 atau 119 ext. 8, atau datang langsung ke UPA BK UTM."
)

_cached_prompt: str | None = None


def load_system_prompt() -> str:
    """Membaca system prompt dari file terpisah (di-cache setelah pembacaan pertama)."""
    global _cached_prompt
    if _cached_prompt is None:
        _cached_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    return _cached_prompt


def get_provider() -> LLMProvider:
    """Memilih penyedia LLM sesuai konfigurasi, dengan fallback aman ke mock."""
    if settings.LLM_PROVIDER == "openai_compatible":
        if not settings.LLM_ALLOW_EXTERNAL:
            logger.warning(
                "LLM_PROVIDER=openai_compatible tetapi LLM_ALLOW_EXTERNAL=false; "
                "memakai penyedia mock (pengaman privasi)."
            )
            return MockLLMProvider()
        if not settings.LLM_API_KEY:
            logger.warning(
                "LLM_PROVIDER=openai_compatible tetapi LLM_API_KEY kosong; "
                "memakai penyedia mock (fallback tanpa biaya)."
            )
            return MockLLMProvider()
        return OpenAICompatibleProvider(
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            timeout_seconds=settings.LLM_TIMEOUT,
        )
    return MockLLMProvider()


def generate_reply(history: list[dict]) -> tuple[str, str | None]:
    """Menghasilkan balasan asisten; mengembalikan (balasan, kode_error|None).

    Tidak pernah melempar LLMError ke pemanggil - error ditangani di sini.
    """
    provider = get_provider()
    try:
        reply = provider.generate_reply(load_system_prompt(), history)
        return reply, None
    except LLMError as exc:
        logger.error("LLM gagal (provider=%s, jenis=%s)", provider.name, type(exc).__name__)
        return _FALLBACK_REPLY, type(exc).__name__
