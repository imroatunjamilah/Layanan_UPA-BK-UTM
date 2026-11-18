"""Penyedia LLM simulasi (mock) - offline, tanpa biaya, deterministik-per-intent.

Digunakan:
- saat LLM_PROVIDER=mock (default pengembangan),
- sebagai fallback otomatis bila penyedia eksternal tidak tersedia/dinonaktifkan.

Balasan bersifat simulasi pendukung awal yang empatik - BUKAN produksi klinis.
Mendukung dua mode: obrolan mahasiswa dan ANALISIS KASUS (JSON terstruktur).
"""
import itertools
import json

from .base import LLMProvider

_GREETING_KW = ("halo", "hai", "selamat", "assalam", "permisi", "pagi", "siang", "sore")
_SAD_KW = ("sedih", "murung", "menangis", "nangis", "hampa", "tidak berharga", "putus asa")
_ANXIOUS_KW = ("cemas", "khawatir", "takut", "panik", "gelisah", "overthinking", "berdebar")
_ACADEMIC_KW = ("tugas", "skripsi", "ujian", "nilai", "kuliah", "dosen", "uts", "uas",
                "praktikum", "bimbingan", "deadline", "tenggat")
_LONELY_KW = ("kesepian", "sepi", "sendiri", "tidak punya teman", "gak punya teman",
              "nggak punya teman", "ditinggal")
_ANGRY_KW = ("marah", "kesal", "jengkel", "bete", "emosi", "geram")
_THANKS_KW = ("terima kasih", "makasih", "thanks", "thank you")

_DEFAULT_REPLIES = [
    "Saya mendengarkan. Boleh ceritakan lebih detail apa yang sedang Anda rasakan belakangan ini?",
    "Terima kasih sudah berbagi. Bagaimana hal ini memengaruhi aktivitas harian Anda, misalnya tidur, kuliah, atau makan?",
    "Saya coba memahami situasi Anda. Jika diibaratkan skala 1-10, seberapa berat beban yang Anda rasakan hari ini, dan apa yang paling menyumbangnya?",
]

_SAD_REPLIES = [
    "Terima kasih sudah mau terbuka tentang perasaan sedih ini. Menahan perasaan seperti itu tidak mudah. Kapan mulai terasa berat, dan apa yang biasanya muncul saat perasaan itu datang?",
    "Perasaan yang Anda ceritakan terasa menyakitkan, dan Anda berani menyampaikannya di sini - itu langkah yang berarti. Boleh ceritakan apa yang baru-baru ini terjadi dalam hidup Anda?",
]

_ANXIOUS_REPLIES = [
    "Kecemasan seperti itu bisa benar-benar melelahkan. Saat muncul, bagaimana biasanya tubuh Anda merespons? Coba tarik napas perlahan (hitung 4), tahan (4), hembuskan (6), lalu ceritakan lagi apa yang ada di pikiran Anda.",
    "Terdengar seperti pikiran Anda terus berjalan dan sulit dihentikan. Boleh ceritakan, situasi seperti apa yang paling sering memicunya belakangan ini?",
]

_ACADEMIC_REPLIES = [
    "Beban akademik memang bisa terasa menumpuk dan menguras energi. Apa yang paling menekan saat ini: volumenya, ekspektasinya, atau rasa takut akan hasilnya? Kita bisa uraikan perlahan, satu per satu.",
    "Terdengar seperti tuntutan kuliah sedang mengambil banyak ruang di kepala Anda. Bagaimana pola tidur dan istirahat Anda akhir-akhir ini selama menghadapi semua itu?",
]

_LONELY_REPLIES = [
    "Rasa kesepian itu nyata dan menyakitkan, dan mengakuinya butuh keberanian. Bagaimana hubungan Anda dengan orang-orang di sekitar Anda akhir-akhir ini?",
    "Terdengar seperti Anda merasa tidak punya tempat untuk bercerita. Di sini Anda bisa bercerita. Apa yang paling ingin Anda dapatkan dari orang-orang di sekitar Anda saat ini?",
]

_ANGRY_REPLIES = [
    "Kemarahan sering menjadi tanda bahwa ada hal penting yang terluka atau terlanggar. Apa yang memicunya, dan bagaimana biasanya Anda menghadapinya?",
    "Saya bisa mendengar kelelahan di balik emosi itu. Sebelum ini membesar, boleh ceritakan kejadian terakhir yang paling membuat Anda kesal?",
]

_THANKS_REPLIES = [
    "Sama-sama, saya senang bisa mendengarkan. Ingat, obrolan ini bukan pengganti konseling profesional - petugas UPA BK siap mendampingi lebih lanjut jika Anda menginginkannya. Semoga hari Anda membaik.",
]


def _contains(text: str, keywords) -> bool:
    return any(kw in text for kw in keywords)


# ---------------------------------------------------------------- analisis kasus
_TEMA_KW = [
    ("tekanan akademik", ("tugas", "skripsi", "ujian", "nilai", "kuliah", "dosen", "deadline", "tenggat", "uts", "uas")),
    ("kecemasan", ("cemas", "khawatir", "takut", "panik", "gelisah", "overthinking")),
    ("kesedihan/mood rendah", ("sedih", "murung", "menangis", "hampa", "putus asa")),
    ("kesepian/hubungan sosial", ("kesepian", "sepi", "sendiri", "ditinggal", "teman")),
    ("kemarahan/regulasi emosi", ("marah", "kesal", "jengkel", "emosi", "geram")),
]


def _mock_case_analysis(system_prompt: str, history: list[dict]) -> str:
    """Analisis deterministik dari payload JSON (tanpa jaringan, tanpa biaya)."""
    payload = {}
    for msg in reversed(history):
        if msg.get("sender") == "mahasiswa":
            try:
                payload = json.loads(msg.get("text") or "{}")
            except (json.JSONDecodeError, ValueError):
                payload = {}
            break

    gabungan = " ".join([
        str(payload.get("keluhan") or ""),
        " ".join(c.get("teks", "") for c in payload.get("percakapan", []) if c.get("peran") == "mahasiswa"),
    ]).lower()

    tema = [label for label, kws in _TEMA_KW if _contains(gabungan, kws)][:5]
    dass = payload.get("dass21") or {}
    kategori = (dass.get("kategori") or {})

    ada_berat = any(k in ("Berat", "Sangat Berat") for k in kategori.values())
    ada_sedang = any(k == "Sedang" for k in kategori.values())
    minta_manusia = _contains(gabungan, ("ketemu", "pendampingan manusia", "konselor", "bertemu petugas"))

    if ada_berat or minta_manusia:
        tingkat = "tinggi"
    elif ada_sedang or tema:
        tingkat = "sedang"
    else:
        tingkat = "rendah"

    if kategori:
        kaitan = (
            f"Skrining DASS-21 menunjukkan kategori umum: depresi {kategori.get('depresi')}, "
            f"kecemasan {kategori.get('kecemasan')}, stres {kategori.get('stres')} "
            "(cut-off publikasi, bukan diagnosis)."
        )
    else:
        kaitan = "Skrining DASS-21 belum tersedia sehingga analisis bertumpu pada keluhan dan obrolan."

    if payload.get("keluhan") and payload.get("percakapan"):
        sumber_cerita = "keluhan tertulis maupun obrolan chatbox"
    elif payload.get("keluhan"):
        sumber_cerita = "keluhan tertulis saat pendaftaran"
    elif payload.get("percakapan"):
        sumber_cerita = "obrolan chatbox"
    else:
        sumber_cerita = ""

    if sumber_cerita:
        ringkasan = (
            f"Mahasiswa mendaftar untuk {payload.get('jenis_layanan', 'layanan konseling')} dengan "
            f"keluhan yang tampak pada {sumber_cerita}."
            + (" Tema yang menonjol: " + ", ".join(tema) + "." if tema else "")
            + (" Skrining menunjukkan indikasi tingkat berat sehingga perlu prioritas tinjauan." if ada_berat else "")
        )
    else:
        ringkasan = "Belum ada keluhan tertulis maupun percakapan yang dapat dianalisis."

    saran = []
    if tingkat == "tinggi":
        saran.append("Tinjau kasus segera; verifikasi indikasi krisis dan jadwalkan kontak awal.")
    elif not payload.get("percakapan"):
        saran.append("Undang mahasiswa mengisi obrolan pendahuluan untuk memperkaya data.")
    if not dass:
        saran.append("Ingatkan mahasiswa menyelesaikan skrining DASS-21 bila belum.")
    saran.append("Konfirmasi preferensi jadwal dan tetapkan petugas penangani.")
    saran.append("Dokumentasikan hasil tinjauan pada catatan tindak lanjut.")

    return json.dumps({
        "ringkasan": ringkasan,
        "tema": tema or ["belum ada tema yang teridentifikasi"],
        "tingkat_perhatian": tingkat,
        "kaitan_dass21": kaitan,
        "saran_tindak_lanjut": saran[:4],
    }, ensure_ascii=False)


class MockLLMProvider(LLMProvider):
    """Penyedia simulasi berbasis aturan sederhana (tanpa jaringan)."""

    name = "mock"

    def __init__(self) -> None:
        self._default_cycle = itertools.cycle(_DEFAULT_REPLIES)

    def generate_reply(self, system_prompt: str, history: list[dict]) -> str:
        # Mode analisis kasus (dipanggil admin, bukan obrolan mahasiswa)
        if "ANALISIS_KASUS_V1" in system_prompt:
            return _mock_case_analysis(system_prompt, history)

        last_user = ""
        for msg in reversed(history):
            if msg.get("sender") == "mahasiswa":
                last_user = (msg.get("text") or "").lower()
                break

        if _contains(last_user, _THANKS_KW):
            return _THANKS_REPLIES[0]
        if _contains(last_user, _SAD_KW):
            return _SAD_REPLIES[len(history) % len(_SAD_REPLIES)]
        if _contains(last_user, _ANXIOUS_KW):
            return _ANXIOUS_REPLIES[len(history) % len(_ANXIOUS_REPLIES)]
        if _contains(last_user, _ACADEMIC_KW):
            return _ACADEMIC_REPLIES[len(history) % len(_ACADEMIC_REPLIES)]
        if _contains(last_user, _LONELY_KW):
            return _LONELY_REPLIES[len(history) % len(_LONELY_REPLIES)]
        if _contains(last_user, _ANGRY_KW):
            return _ANGRY_REPLIES[len(history) % len(_ANGRY_REPLIES)]
        if last_user and _contains(last_user, _GREETING_KW) and len(last_user.split()) <= 8:
            return (
                "Halo! Senang bisa menemani Anda di sini. Ada yang sedang Anda rasakan "
                "atau pikirkan akhir-akhir ini yang ingin Anda ceritakan?"
            )
        return next(self._default_cycle)
