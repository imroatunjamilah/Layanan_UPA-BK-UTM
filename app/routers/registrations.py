"""Endpoint pendaftaran layanan konseling (mahasiswa, tanpa akun)."""
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Followup, Registration
from ..security import make_chat_token
from ..services import options
from ..utils import iso_utc

router = APIRouter(prefix="/api/registrations", tags=["Pendaftaran"])
logger = logging.getLogger("app.registrations")


class RegistrationCreate(BaseModel):
    nama: str = Field(min_length=2, max_length=120)
    nim: str = Field(min_length=4, max_length=30)
    kontak: str = Field(min_length=5, max_length=120)
    jenis_layanan: str = Field(min_length=2, max_length=50)
    preferensi_hari: str = Field(min_length=3, max_length=20)
    preferensi_waktu: str = Field(min_length=3, max_length=30)
    keluhan: str | None = Field(default=None, max_length=4000)
    setuju_penggunaan_data: bool


@router.get("/options")
def get_options():
    """Opsi pilihan untuk form pendaftaran."""
    return {
        "jenis_layanan": options.JENIS_LAYANAN,
        "hari": options.HARI,
        "waktu": options.WAKTU,
    }


@router.post("", status_code=201)
def create_registration(payload: RegistrationCreate, db: Session = Depends(get_db)):
    """Mendaftarkan layanan konseling.

    - Setiap pendaftaran otomatis membuat baris tindak lanjut (menunggu_ditinjau).
    - Preferensi hari/waktu HANYA preferensi awal, bukan jadwal terkonfirmasi.
    - Mengembalikan chat_token yang menjadi "kunci akses" mahasiswa atas datanya sendiri.
    """
    if not payload.setuju_penggunaan_data:
        raise HTTPException(422, "Persetujuan penggunaan data wajib diberikan (consent).")
    if payload.jenis_layanan not in options.JENIS_LAYANAN:
        raise HTTPException(422, "Jenis layanan tidak dikenal.")
    if payload.preferensi_hari not in options.HARI:
        raise HTTPException(422, "Preferensi hari tidak dikenal.")
    if payload.preferensi_waktu not in options.WAKTU:
        raise HTTPException(422, "Preferensi waktu tidak dikenal.")

    reg = Registration(
        nama=payload.nama.strip(),
        nim=payload.nim.strip(),
        kontak=payload.kontak.strip(),
        jenis_layanan=payload.jenis_layanan,
        preferensi_hari=payload.preferensi_hari,
        preferensi_waktu=payload.preferensi_waktu,
        keluhan=(payload.keluhan.strip() or None) if payload.keluhan else None,
        consent_status="disetujui",
    )
    db.add(reg)
    db.flush()  # dapatkan reg.id untuk followup & token

    db.add(Followup(registration_id=reg.id, status="menunggu_ditinjau"))
    db.commit()

    logger.info("Pendaftaran baru dibuat (id=%s, layanan=%s).", reg.id, reg.jenis_layanan)
    return {
        "registration_id": reg.id,
        "chat_token": make_chat_token(reg.id),
        "nama": reg.nama,
        "pesan": (
            "Pendaftaran berhasil. Preferensi jadwal Anda akan dikonfirmasi terpisah "
            "oleh petugas UPA BK - ini bukan jadwal terkonfirmasi."
        ),
        "langkah_selanjutnya": "/dass21.html",
        "created_at": iso_utc(reg.created_at),
    }
