"""Pengiriman pesan WhatsApp untuk OTP reset kata sandi admin.

Dua penyedia, dipilih lewat WA_PROVIDER (lihat app.config):
- "mock"   : DEFAULT. Tidak ada koneksi keluar - kode hanya dicatat di log server.
             Cocok untuk demo/pengembangan; alur uji tetap utuh end-to-end.
- "fonnte" : kirim nyata via API Fonnte (https://fonnte.com). Isi WA_API_TOKEN
             di file .env; penyedia lain mudah ditambahkan dengan pola yang sama.

Prinsip privasi: yang dikirim HANYA nomor tujuan dan teks OTP - tidak ada data
kasus, keluhan, atau obrolan yang pernah keluar lewat layanan ini.
"""
import logging
import re

import httpx

from ..config import settings

logger = logging.getLogger("app.wa")

_RE_NON_DIGIT = re.compile(r"\D")


def normalize_wa(raw: str | None) -> str | None:
    """Rapikan nomor WhatsApp ke format internasional '62...'.

    Menerima: 08123456789, 8123456789, 628123456789, +62 812-3456-789.
    Mengembalikan None bila nomor tidak masuk akal (terlalu pendek/panjang).
    """
    if not raw:
        return None
    digits = _RE_NON_DIGIT.sub("", raw)
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits
    # awalan "62" dibiarkan apa adanya
    if not (9 <= len(digits) <= 15) or not digits.isdigit():
        return None
    return digits


def build_otp_message(code: str, ttl_minutes: int) -> str:
    """Teks pesan WhatsApp berisi kode OTP (Bahasa Indonesia)."""
    return (
        f"UPA BK UTM: kode reset kata sandi Anda adalah {code}. "
        f"Berlaku {ttl_minutes} menit. JANGAN bagikan kode ini kepada siapa pun, "
        f"termasuk pihak yang mengaku petugas. Jika Anda tidak meminta kode ini, "
        f"abaikan pesan ini."
    )


def _send_via_fonnte(phone: str, message: str) -> bool:
    """Kirim pesan lewat API Fonnte. Mengembalikan True bila berhasil."""
    if not settings.WA_API_TOKEN:
        logger.error("WA_PROVIDER=fonnte tapi WA_API_TOKEN kosong - pesan tidak terkirim.")
        return False
    try:
        resp = httpx.post(
            settings.WA_API_URL,
            headers={"Authorization": settings.WA_API_TOKEN},
            data={"target": phone, "message": message, "countryCode": "62"},
            timeout=15.0,
        )
        if resp.status_code == 200:
            return True
        logger.error("Fonnte merespons %s: %s", resp.status_code, resp.text[:200])
        return False
    except httpx.HTTPError as exc:
        logger.error("Gagal menghubungi gateway Fonnte: %s", exc)
        return False


def send_whatsapp(phone: str, message: str) -> bool:
    """Kirim satu pesan WhatsApp memakai penyedia aktif. True = terkirim."""
    if settings.WA_PROVIDER == "fonnte":
        return _send_via_fonnte(phone, message)
    # Provider "mock" (default): tanpa koneksi keluar, cukup catat di log server.
    logger.info("WA[mock] -> %s : %s", phone, message)
    return True
