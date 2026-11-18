"""Endpoint skrining DASS-21.

KEBIJAKAN PENTING: hasil (skor/kategori) TIDAK PERNAH dikirim ke mahasiswa.
Respons submit hanya konfirmasi generik. Skor hanya dapat dilihat admin
(see routers/admin.py) dan disimpan dengan penanda scoring_version.
"""
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Dass21Response, Registration
from ..security import verify_chat_token
from ..services.dass21_questions import ANSWER_OPTIONS, INTRO_DASS21, QUESTIONS
from ..services.dass21_scoring import score_answers
from ..utils import utcnow

router = APIRouter(prefix="/api/dass21", tags=["DASS-21"])


class Dass21Submit(BaseModel):
    registration_id: int
    chat_token: str = Field(min_length=16, max_length=64)
    # Kunci JSON datang sebagai string "1".."21" - divalidasi manual di router.
    jawaban: Dict[str, int]


@router.get("/questions")
def get_questions():
    """Daftar 21 pernyataan + opsi jawaban untuk halaman skrining mahasiswa."""
    return {
        "pengantar": INTRO_DASS21,
        "pertanyaan": [{"no": no, "teks": teks} for no, _sub, teks in QUESTIONS],
        "opsi": ANSWER_OPTIONS,
    }


@router.post("/submit")
def submit(payload: Dass21Submit, db: Session = Depends(get_db)):
    reg = db.get(Registration, payload.registration_id)
    if not reg:
        raise HTTPException(404, "Pendaftaran tidak ditemukan.")
    if not verify_chat_token(reg.id, payload.chat_token):
        raise HTTPException(403, "Token akses tidak valid untuk pendaftaran ini.")
    if reg.dass21:
        raise HTTPException(409, "Skrining untuk pendaftaran ini sudah pernah diisi.")

    try:
        jawaban_int = {int(k): int(v) for k, v in payload.jawaban.items()}
    except (TypeError, ValueError):
        raise HTTPException(422, "Nomor/nilai jawaban harus berupa bilangan bulat.")

    try:
        hasil = score_answers(jawaban_int)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    response = Dass21Response(
        registration_id=reg.id,
        **{f"jawaban_{i}": jawaban_int[i] for i in range(1, 22)},
        skor_depresi=hasil["skor_depresi"],
        skor_kecemasan=hasil["skor_kecemasan"],
        skor_stres=hasil["skor_stres"],
        scoring_version=hasil["scoring_version"],
        submitted_at=utcnow(),
    )
    db.add(response)
    db.commit()

    # Sengaja TIDAK mengembalikan skor ke mahasiswa.
    return {
        "status": "tersimpan",
        "pesan": (
            "Terima kasih! Jawaban skrining Anda telah tersimpan dan akan ditinjau "
            "oleh petugas UPA BK. Sesuai kebijakan layanan, hasil tidak ditampilkan "
            "kepada mahasiswa."
        ),
        "langkah_selanjutnya": "/chatbot.html",
    }
