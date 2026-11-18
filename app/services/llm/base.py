"""Antarmuka dasar penyedia LLM + keluarga pengecualian.

Semua penyedia (mock, OpenAI-compatible, model lokal di masa depan) mengimplementasikan
LLMProvider sehingga router obrolan tidak perlu tahu detail penyedianya.
"""
from abc import ABC, abstractmethod


class LLMError(Exception):
    """Kesalahan umum pemanggilan LLM (tanpa detail sensitif di pesan)."""


class LLMAuthError(LLMError):
    """API key salah/kosong atau akses ditolak."""


class LLMRateLimitError(LLMError):
    """Batas permintaan penyedia tercapai."""


class LLMTimeoutError(LLMError):
    """Penyedia tidak merespons dalam batas waktu."""


class LLMConnectionError(LLMError):
    """Gagal terhubung ke penyedia."""


class LLMProvider(ABC):
    """Kontrak penyedia model bahasa."""

    name: str = "base"

    @abstractmethod
    def generate_reply(self, system_prompt: str, history: list[dict]) -> str:
        """Menghasilkan balasan asisten.

        history: daftar pesan {"sender": "mahasiswa"|"bot", "text": str}
                 dalam urutan kronologis (pesan terbaru terakhir).
        Mengembalikan teks balasan (str).
        Melempar LLMError turunannya bila gagal.
        """
