"""Penilaian (scoring) DASS-21.

Aturan baku DASS-21 (Lovibond & Lovibond, 1995):
- 21 item, masing-masing 0-3.
- Setiap subskala terdiri atas 7 item, jumlah item Dikalikan 2 agar setara DASS-42.
  - Depresi  : item 3, 5, 10, 13, 16, 17, 21
  - Kecemasan: item 2, 4, 7, 9, 15, 19, 20
  - Stres    : item 1, 6, 8, 11, 12, 14, 18

PERINGATAN KLINIS (WAJIB DIPATUHI):
- Skor ini ALAT SKRINING, bukan diagnosis.
- Kategori tingkat keparahan di bawah adalah cut-off publikasi umum DASS-21 dan
  BUKAN kategori resmi UPA BK. Kategori ini tidak boleh disamakan dengan
  kategori risiko resmi institusi kecuali UPA BK menyetujuinya secara resmi.
- Skor/kategori TIDAK PERNAH ditampilkan kepada mahasiswa (hanya admin/petugas).
"""

from typing import Dict

SCORING_VERSION = "DASS21-ID-STD-1.0"

SUBSCALE_ITEMS: dict[str, list[int]] = {
    "depresi": [3, 5, 10, 13, 16, 17, 21],
    "kecemasan": [2, 4, 7, 9, 15, 19, 20],
    "stres": [1, 6, 8, 11, 12, 14, 18],
}

# Cut-off publikasi umum (Lovibond & Lovibond, 1995) - LIHAT PERINGATAN DI ATAS.
SEVERITY_BANDS: dict[str, list[tuple[int, int, str]]] = {
    "depresi": [
        (0, 9, "Normal"), (10, 13, "Ringan"), (14, 20, "Sedang"),
        (21, 27, "Berat"), (28, 10**9, "Sangat Berat"),
    ],
    "kecemasan": [
        (0, 7, "Normal"), (8, 9, "Ringan"), (10, 14, "Sedang"),
        (15, 19, "Berat"), (20, 10**9, "Sangat Berat"),
    ],
    "stres": [
        (0, 14, "Normal"), (15, 18, "Ringan"), (19, 25, "Sedang"),
        (26, 33, "Berat"), (34, 10**9, "Sangat Berat"),
    ],
}

SEVERITY_DISCLAIMER = (
    "Kategori umum berdasarkan cut-off publikasi DASS-21 (Lovibond & Lovibond, 1995). "
    "Bukan kategori resmi UPA BK, bukan diagnosis, dan tidak ditampilkan kepada mahasiswa."
)


def validate_answers(jawaban: Dict[int, int]) -> None:
    """Memastikan jawaban lengkap 1..21 dengan nilai integer 0..3.

    Melempar ValueError dengan pesan jelas bila tidak valid.
    """
    if not isinstance(jawaban, dict):
        raise ValueError("Jawaban harus berupa objek {nomor: nilai}.")

    missing = [i for i in range(1, 22) if i not in jawaban]
    if missing:
        raise ValueError(f"Jawaban belum lengkap, nomor yang hilang: {missing}")

    extra = [k for k in jawaban if not (isinstance(k, int) and 1 <= k <= 21)]
    if extra:
        raise ValueError(f"Nomor pertanyaan tidak dikenal: {extra}")

    for i, v in jawaban.items():
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 3:
            raise ValueError(f"Nilai jawaban nomor {i} harus bilangan bulat 0-3 (diterima: {v!r}).")


def score_answers(jawaban: Dict[int, int]) -> Dict[str, object]:
    """Menghitung skor tiga subskala DASS-21 (jumlah item x 2).

    Mengembalikan dict: skor_depresi, skor_kecemasan, skor_stres, scoring_version.
    """
    validate_answers(jawaban)
    hasil: dict[str, object] = {}
    for subscale, items in SUBSCALE_ITEMS.items():
        total = sum(jawaban[i] for i in items) * 2
        key = {"depresi": "skor_depresi", "kecemasan": "skor_kecemasan", "stres": "skor_stres"}[subscale]
        hasil[key] = int(total)
    hasil["scoring_version"] = SCORING_VERSION
    return hasil


def classify_subscale(subscale: str, score: int) -> str:
    """Kategori tingkat keparahan umum (hanya untuk petugas - LIHAT PERINGATAN)."""
    if subscale not in SEVERITY_BANDS:
        raise ValueError(f"Subskala tidak dikenal: {subscale}")
    for low, high, label in SEVERITY_BANDS[subscale]:
        if low <= score <= high:
            return label
    return "Tidak terkategori"
