"""Analisis kasus terpadu berbantuan LLM (khusus admin).

Menggabungkan TIGA sumber menjadi satu ringkasan untuk petugas UPA BK:
  1. Keluhan tertulis saat pendaftaran
  2. Hasil skrining DASS-21 (skor + kategori umum)
  3. Isi percakapan chatbox (pesan mahasiswa & asisten)

Prinsip keamanan yang dipertahankan:
- Hanya admin yang dapat memanggil (endpoint berada di router admin).
- Pemilihan penyedia LLM mengikuti gerbang privasi yang sama dengan chatbot:
  LLM_ALLOW_EXTERNAL=false memaksa penyedia mock (tidak ada data keluar).
- Analisis BUKAN diagnosis - hanya ringkasan/hipotesis awal untuk profesional.
- Log audit tidak memuat isi keluhan/obrolan.
"""
import json
import logging

from ..models import Dass21Response, Registration
from ..utils import iso_utc, utcnow
from .dass21_scoring import classify_subscale
from .llm import manager as llm_manager

logger = logging.getLogger("app.analysis")

# Penanda agar penyedia mock mengenali permintaan analisis (bukan obrolan).
ANALYSIS_MARKER = "ANALISIS_KASUS_V1"

# Batas ukuran input agar prompt tetap wajar.
_MAX_KELUHAN_CHARS = 2000
_MAX_MESSAGES = 40
_MAX_MESSAGE_CHARS = 500

DISCLAIMER_ANALYSIS = (
    "Analisis ini adalah ringkasan otomatis berbantuan AI untuk membantu petugas meninjau "
    "kasus lebih cepat. BUKAN diagnosis, BUKAN keputusan klinis, dan tidak ditampilkan "
    "kepada mahasiswa. Keputusan tindak lanjut tetap milik petugas profesional."
)

ANALYSIS_SYSTEM_PROMPT = f"""{ANALYSIS_MARKER}
Anda membantu petugas UPA BK (unit konseling universitas) meninjau satu kasus mahasiswa.
Anda menerima data JSON berisi: keluhan tertulis, hasil skrining DASS-21 (skor dan kategori
umum), serta kutipan percakapan chatbox. Beberapa data bisa tidak tersedia (null/kosong).

Tugas: menghasilkan ringkasan terpadu dalam BAHASA INDONESIA dengan format JSON MURNI
(tanpa teks lain, tanpa blok kode) berstruktur:
{{
  "ringkasan": "1-3 kalimat inti kondisi mahasiswa",
  "tema": ["maksimal 5 tema singkat, mis. 'tekanan akademik'"],
  "tingkat_perhatian": "rendah" | "sedang" | "tinggi",
  "kaitan_dass21": "1-2 kalimat menghubungkan skor DASS-21 dengan cerita mahasiswa",
  "saran_tindak_lanjut": ["2-4 langkah konkret untuk petugas"]
}}

Aturan wajib:
- Naikkan "tingkat_perhatian" bila kategori DASS-21 berat/sangat berat, ada indikasi krisis
  pada percakapan, atau mahasiswa meminta pendampingan manusia.
- Jangan mendiagnosis; gunakan bahasa hati-hati ("mengindikasikan", "berpotensi").
- Jangan mengaruh data yang tidak ada; sebutkan bila keluhan/skrining/obrolan kosong.
- Jangan pernah menyarankan pengiriman data ke pihak eksternal.
"""


def _build_payload(db, reg: Registration) -> dict:
    """Mengumpulkan data kasus untuk dianalisis (dengan pemangkasan ukuran)."""
    dass = db.query(Dass21Response).filter(Dass21Response.registration_id == reg.id).first()
    dass_data = None
    if dass:
        dass_data = {
            "skor": {
                "depresi": dass.skor_depresi,
                "kecemasan": dass.skor_kecemasan,
                "stres": dass.skor_stres,
            },
            "kategori": {
                "depresi": classify_subscale("depresi", dass.skor_depresi),
                "kecemasan": classify_subscale("kecemasan", dass.skor_kecemasan),
                "stres": classify_subscale("stres", dass.skor_stres),
            },
        }

    kutipan: list[dict] = []
    for conv in sorted(reg.conversations, key=lambda c: c.id):
        for m in conv.messages:
            if m.sender not in ("mahasiswa", "bot"):
                continue  # pesan audit 'sistem' tidak ikut dianalisis
            kutipan.append({
                "peran": "mahasiswa" if m.sender == "mahasiswa" else "asisten",
                "teks": (m.message_text or "")[:_MAX_MESSAGE_CHARS],
            })
    if len(kutipan) > _MAX_MESSAGES:
        kutipan = kutipan[-_MAX_MESSAGES:]

    return {
        "jenis_layanan": reg.jenis_layanan,
        "status_tindak_lanjut": reg.followup.status if reg.followup else "menunggu_ditinjau",
        "keluhan": (reg.keluhan or "")[:_MAX_KELUHAN_CHARS] or None,
        "dass21": dass_data,
        "percakapan": kutipan,
    }


def _fallback_analysis(payload: dict, alasan: str) -> dict:
    """Analisis cadangan tanpa LLM (mis. penyedia gagal) - tetap terstruktur."""
    dass = payload.get("dass21")
    tema: list[str] = []
    if payload.get("keluhan"):
        tema.append("keluhan tertulis mahasiswa")
    if payload.get("percakapan"):
        tema.append("percakapan chatbox")
    if dass:
        tema.append("hasil skrining DASS-21")

    if not tema:
        ringkasan = "Belum ada data yang dapat dianalisis (keluhan, skrining, dan obrolan kosong)."
        tingkat = "rendah"
        kaitan = "Skrining DASS-21 belum tersedia."
    else:
        ringkasan = "Ringkasan otomatis tidak tersedia (" + alasan + "). Tinjau data sumber berikut: " \
            + ", ".join(tema) + "."
        kategori = (dass or {}).get("kategori", {})
        ada_berat = any(k in ("Berat", "Sangat Berat") for k in kategori.values())
        tingkat = "tinggi" if ada_berat else ("sedang" if kategori else "rendah")
        if kategori:
            kaitan = (
                f"Kategori umum DASS-21: depresi {kategori.get('depresi')}, "
                f"kecemasan {kategori.get('kecemasan')}, stres {kategori.get('stres')}."
            )
        else:
            kaitan = "Skrining DASS-21 belum tersedia."

    return {
        "ringkasan": ringkasan,
        "tema": tema or ["belum ada data"],
        "tingkat_perhatian": tingkat,
        "kaitan_dass21": kaitan,
        "saran_tindak_lanjut": [
            "Verifikasi manual: baca keluhan dan kutipan obrolan pada panel detail.",
            "Perbarui status tindak lanjut dan tetapkan petugas penangani bila belum.",
        ],
        "sumber": "fallback",
    }


def _parse_llm_json(text: str) -> dict | None:
    """Mengurai keluaran JSON LLM; toleran terhadap blok kode & teks liar."""
    if not text:
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, ValueError):
        # cari objek JSON pertama yang valid di dalam teks
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(candidate[start:end + 1])
                return data if isinstance(data, dict) else None
            except (json.JSONDecodeError, ValueError):
                return None
    return None


def generate_case_analysis(db, reg: Registration) -> dict:
    """Menghasilkan analisis terpadu satu kasus; tidak pernah melempar LLMError."""
    payload = _build_payload(db, reg)
    user_content = json.dumps(payload, ensure_ascii=False)

    provider = llm_manager.get_provider()
    try:
        raw = provider.generate_reply(ANALYSIS_SYSTEM_PROMPT, [
            {"sender": "mahasiswa", "text": user_content},
        ])
    except Exception as exc:  # aman: fallback, tanpa detail sensitif di response
        logger.error("ANALISIS gagal (reg=%s, jenis=%s)", reg.id, type(exc).__name__)
        analisis = _fallback_analysis(payload, "penyedia LLM tidak merespons")
        provider_name = provider.name
    else:
        parsed = _parse_llm_json(raw)
        if parsed:
            analisis = parsed
            analisis["sumber"] = "llm"
        else:
            analisis = _fallback_analysis(payload, "keluaran LLM tidak dapat diurai")
        provider_name = provider.name

    # Normalisasi minimal agar UI tidak pernah error
    analisis.setdefault("tema", [])
    if not isinstance(analisis.get("tema"), list):
        analisis["tema"] = [str(analisis["tema"])]
    if analisis.get("tingkat_perhatian") not in ("rendah", "sedang", "tinggi"):
        analisis["tingkat_perhatian"] = "sedang"
    if not isinstance(analisis.get("saran_tindak_lanjut"), list):
        analisis["saran_tindak_lanjut"] = [str(analisis.get("saran_tindak_lanjut") or "-")]

    logger.info("ANALISIS dibuat (reg=%s, penyedia=%s).", reg.id, provider_name)
    return {
        "registration_id": reg.id,
        "penyedia": provider_name,
        "dibuat_pada": iso_utc(utcnow()),
        "analisis": analisis,
        "disclaimer": DISCLAIMER_ANALYSIS,
    }
