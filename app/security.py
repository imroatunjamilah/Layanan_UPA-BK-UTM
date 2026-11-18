"""Keamanan: hashing password, token sesi admin, token akses obrolan.

Prinsip:
- Password DIHASH dengan PBKDF2-SHA256 (salt acak per user) - tidak pernah disimpan plain.
- Token sesi admin = payload JSON bertanda tangan HMAC-SHA256 (stateless, bermasa aktif).
- Token obrolan mahasiswa = HMAC dari SECRET_KEY terhadap registration_id, sehingga
  mahasiswa hanya dapat mengakses data obrolan/skrining miliknya sendiri.
- Tidak ada password/API key yang ditulis ke log.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

from .config import settings

_ITERATIONS = 390_000  # rekomendasi OWASP untuk PBKDF2-SHA256


# ---------------------------------------------------------------- password
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return (
        f"pbkdf2_sha256${_ITERATIONS}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_b64, hash_b64 = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), base64.b64decode(salt_b64), int(iters)
        )
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- token admin
def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload: str) -> str:
    key = settings.SECRET_KEY.encode("utf-8")
    return _b64e(hmac.new(key, payload.encode("utf-8"), hashlib.sha256).digest())


class TokenError(Exception):
    """Token tidak valid / kedaluwarsa."""


def create_access_token(username: str, role: str, expires_minutes: int | None = None) -> str:
    exp = int(time.time()) + (expires_minutes or settings.TOKEN_EXPIRE_MINUTES) * 60
    payload = {"sub": username, "role": role, "exp": exp}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def decode_access_token(token: str) -> dict:
    try:
        payload, signature = token.split(".")
    except ValueError:
        raise TokenError("format token tidak valid")
    if not hmac.compare_digest(_sign(payload), signature):
        raise TokenError("tanda tangan token tidak valid")
    try:
        data = json.loads(_b64d(payload))
    except (ValueError, TypeError):
        raise TokenError("isi token tidak dapat dibaca")
    if int(data.get("exp", 0)) < time.time():
        raise TokenError("token kedaluwarsa")
    return data


# ---------------------------------------------------------------- token mahasiswa
def make_chat_token(registration_id: int) -> str:
    msg = f"chat-access:{registration_id}".encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:32]


def verify_chat_token(registration_id: int, token: str | None) -> bool:
    if not token:
        return False
    return hmac.compare_digest(make_chat_token(registration_id), token)
