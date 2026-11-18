"""Deteksi krisis & permintaan pendampingan manusia untuk lapisan keselamatan obrolan.

PENTING (perlu persetujuan UPA BK):
- Kata kunci & tindakan otomatis di bawah adalah konfigurasi DEFAULT prototipe.
- Lapisan ini sengaja TIDAK bergantung pada penilaian LLM: keselamatan tidak boleh
  bergantung hanya pada model bahasa.
- Protokol eskalasi resmi (nomor kontak kampus, alur petugas, template pesan)
  harus disetujui dan diisi oleh UPA BK sebelum produksi.
"""

from typing import Final

# --- Konfigurasi eskalasi (default prototipe - WAJIB direview UPA BK) ------
CRISIS_CONFIG: Final[dict] = {
    "AUTO_ESCALATE_FOLLOWUP": True,        # tandai tindak lanjut otomatis saat krisis terdeteksi
    "STATUS_ESKALASI": "perlu_ditinjau_segera",
    "MARKER_ESKALASI": "[ESKALASI]",
    "MARKER_OTOMATIS": "[OTOMATIS]",
}

# --- Kata kunci indikasi krisis (Bahasa Indonesia sehari-hari + varian umum) ----
CRISIS_KEYWORDS: Final[tuple[str, ...]] = (
    "bunuh diri", "membunuh diri", "mengakhiri hidup", "akhiri hidup",
    "ingin mati", "pengen mati", "mau mati", "ga ingin hidup", "gak ingin hidup",
    "tidak ingin hidup", "nggak ingin hidup", "gak mau hidup", "nggak mau hidup",
    "tak ingin hidup", "selesai saja hidup", "hilang saja hidup", "mati saja",
    "melukai diri", "menyakiti diri", "menyakitin diri", "mengocek diri",
    "self harm", "self-harm", "suicide", "suicidal", "menyobek pergelangan",
    "menelan pil", "minum pil",
)

# --- Kata kunci permintaan pendampingan manusia -----------------------------
HANDOFF_KEYWORDS: Final[tuple[str, ...]] = (
    "bicara dengan manusia", "ngobrol dengan manusia", "bicara sama manusia",
    "konselor", "konselor asli", "petugas", "tenaga profesional", "psikolog",
    "pendampingan manusia", "ditemani manusia", "bicara langsung",
    "chat dengan konselor", "layanan manusia", "human", "manusia asli",
)

# --- Kontak darurat ----------------------------------------------------------
# 112    : pusat panggilan darurat nasional (publik, 24 jam).
# 119 x8 : layanan Sejiwa, Kementerian Kesehatan RI (publik).
# Kontak langsung UPA BK belum boleh dikarang - diisi oleh UPA BK.
UPA_BK_EMERGENCY_CONTACT: Final[str] = (
    "[Kontak darurat UPA BK UTM - diisi/dikonfirmasi oleh UPA BK]"
)

SAFETY_MESSAGE: Final[str] = (
    "Terima kasih sudah berani menyampaikan hal yang berat ini. Keselamatan Anda "
    "adalah prioritas kami, jadi saya ingin memastikan Anda mendapatkan bantuan "
    "segera dari manusia sungguhan:\n\n"
    "1) Jika Anda dalam bahaya sekarang juga, hubungi 112 (darurat nasional, 24 jam) "
    "atau 119 ext. 8 (layanan Sejiwa, Kementerian Kesehatan).\n"
    f"2) Hubungi atau datang langsung ke UPA BK UTM: {UPA_BK_EMERGENCY_CONTACT}\n"
    "3) Ceritakan kepada orang yang Anda percaya dan mintalah didampingi.\n\n"
    "Permintaan Anda telah ditandai oleh sistem agar petugas UPA BK meninjaunya. "
    "Namun mohon diingat: pesan otomatis ini tidak menjamin respons manusia yang "
    "langsung, jadi untuk kondisi mendesak gunakan nomor darurat di atas. "
    "Anda tidak sendirian, dan bantuan profesional tersedia."
)

HANDOFF_ACKNOWLEDGMENT: Final[str] = (
    "Terima kasih sudah menyampaikan permintaan itu. Permintaan pendampingan dari "
    "petugas/konselor UPA BK telah saya catat untuk ditinjau oleh unit layanan. "
    "Mohon maaf, saya tidak dapat menjamin respons manusia yang langsung lewat "
    "obrolan ini - jika keadaan Anda mendesak, silakan hubungi 112 atau 119 ext. 8, "
    "atau datang langsung ke UPA BK UTM."
)

DISCLAIMER_CHAT: Final[str] = (
    "Asisten obrolan ini membantu mendengarkan dan memberi dukungan awal, namun "
    "BUKAN pengganti konseling profesional. Untuk pendampingan menyeluruh, silakan "
    "ajukan layanan konseling UPA BK."
)


def detect_crisis(text: str) -> bool:
    """Mendeteksi indikasi krisis secara sederhana (kata kunci, tidak peka huruf besar/kecil)."""
    if not text:
        return False
    lowered = " ".join(text.lower().split())
    return any(kw in lowered for kw in CRISIS_KEYWORDS)


def detect_handoff(text: str) -> bool:
    """Mendeteksi permintaan bicara dengan manusia/konselor."""
    if not text:
        return False
    lowered = " ".join(text.lower().split())
    return any(kw in lowered for kw in HANDOFF_KEYWORDS)
