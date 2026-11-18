"""Penyedia LLM kompatibel OpenAI (OpenAI, Azure OpenAI, Ollama, vLLM, dll.).

Catatan privasi:
- Penyedia eksternal hanya boleh diaktifkan setelah review privasi dan persetujuan
  kebijakan data UPA BK (lihat LLM_ALLOW_EXTERNAL pada .env.example dan dokumen
  docs/prototype-limitations.md). Data obrolan kesehatan mental TIDAK boleh
  dikirim ke layanan eksternal tanpa perlindungan yang memadai.
- API key tidak pernah dicatat ke log dan tidak pernah disertakan dalam pesan error.
"""
import httpx

from .base import (
    LLMAuthError,
    LLMConnectionError,
    LLMError,
    LLMProvider,
    LLMRateLimitError,
    LLMTimeoutError,
)

_MAX_HISTORY_MESSAGES = 20


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(self, base_url: str, model: str, api_key: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def generate_reply(self, system_prompt: str, history: list[dict]) -> str:
        if not self.api_key:
            raise LLMAuthError("LLM_API_KEY kosong - atur lewat variabel lingkungan.")

        # Kirim maksimal N pesan terakhir agar konteks tetap terkendali.
        trimmed = history[-_MAX_HISTORY_MESSAGES:]
        messages = [{"role": "system", "content": system_prompt}]
        for msg in trimmed:
            role = "assistant" if msg.get("sender") == "bot" else "user"
            messages.append({"role": role, "content": str(msg.get("text", ""))})

        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 400,
        }

        try:
            response = httpx.post(
                url, headers=headers, json=payload, timeout=self.timeout_seconds
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Penyedia LLM tidak merespons dalam {self.timeout_seconds} detik."
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMConnectionError("Gagal terhubung ke penyedia LLM.") from exc

        if response.status_code in (401, 403):
            raise LLMAuthError("Autentikasi ke penyedia LLM ditolak. Periksa LLM_API_KEY.")
        if response.status_code == 429:
            raise LLMRateLimitError("Batas permintaan penyedia LLM tercapai, coba lagi nanti.")
        if response.status_code >= 400:
            raise LLMError(f"Penyedia LLM mengembalikan status HTTP {response.status_code}.")

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError("Format jawaban penyedia LLM tidak dikenali.") from exc

        return (content or "").strip() or "Maaf, saya belum bisa merespons. Coba ulangi."
