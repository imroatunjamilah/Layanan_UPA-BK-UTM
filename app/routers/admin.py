"""Endpoint dashboard admin UPA BK.

Seluruh endpoint di bawah dilindungi RBAC (get_current_admin), KECUALI
forgot-password/reset-password yang memang untuk akun yang terkunci.
Fitur: login/logout (dengan blokir akun nonaktif & masa aktif berakhir),
ganti/reset password (mandiri via OTP WhatsApp + reset langsung oleh admin),
manajemen akun admin (profil nama/NIM/fakultas, aktif/nonaktif, masa aktif),
statistik, daftar + pencarian/filter + urutan prioritas, detail lengkap
(pendaftaran, DASS-21, keluhan, obrolan, tindak lanjut), pembaruan tindak
lanjut, pengelolaan petugas penangani, penugasan penanggung jawab per kasus,
dan ekspor CSV terbatas.

Kebijakan akses & privasi:
- Data skrining/keluhan/obrolan hanya untuk petugas berwenang.
- Log audit tidak pernah memuat isi keluhan, isi pesan, atau kredensial.
- Kode OTP disimpan sebagai hash, kedaluwarsa, dan dibatasi percobaannya.
"""
import csv
import hashlib
import hmac
import io
import logging
import secrets
import time
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import (
    Conversation,
    Dass21Response,
    Followup,
    Message,
    Petugas,
    Registration,
    ScheduleReminder,
    User,
)
from ..security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from ..models import Schedule
from ..services import analysis as analysis_service
from ..services import scheduling as sched_service
from ..services import wa as wa_service
from ..services.crisis import CRISIS_CONFIG
from ..services.dass21_scoring import (
    SEVERITY_DISCLAIMER,
    classify_subscale,
)
from ..utils import iso_utc, utcnow
from .deps import (
    SESSION_COOKIE,
    account_status,
    ensure_account_usable,
    get_current_admin,
)

router = APIRouter(prefix="/api/admin", tags=["Admin"])
logger = logging.getLogger("app.admin")

STATUS_LIST = [
    "menunggu_ditinjau",
    "sedang_diproses",
    "dijadwalkan",
    "selesai",
    "perlu_ditinjau_segera",
]
STATUS_LABELS = {
    "menunggu_ditinjau": "Menunggu Ditinjau",
    "sedang_diproses": "Sedang Diproses",
    "dijadwalkan": "Dijadwalkan",
    "selesai": "Selesai",
    "perlu_ditinjau_segera": "Perlu Ditinjau Segera",
}
# Urutan antrean prioritas: eskalasi krisis paling atas, selesai paling bawah.
_PRIORITY_CASE = case(
    (Followup.status == "perlu_ditinjau_segera", 0),
    (Followup.status == "menunggu_ditinjau", 1),
    (Followup.status == "sedang_diproses", 2),
    (Followup.status == "dijadwalkan", 3),
    (Followup.status == "selesai", 4),
    else_=5,
)

# ---------------------------------------------------------------- rate limit login
_LOGIN_WINDOW_SECONDS = 900
_LOGIN_MAX_ATTEMPTS = 5
_login_attempts: dict[str, list[float]] = {}


def _login_rate_limited(username: str) -> bool:
    now = time.time()
    recent = [t for t in _login_attempts.get(username, []) if now - t < _LOGIN_WINDOW_SECONDS]
    _login_attempts[username] = recent
    return len(recent) >= _LOGIN_MAX_ATTEMPTS


def _record_login_failure(username: str) -> None:
    _login_attempts.setdefault(username, []).append(time.time())


# ---------------------------------------------------------------- skema request
class AdminLogin(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class PasswordChange(BaseModel):
    password_lama: str = Field(min_length=1, max_length=128)
    password_baru: str = Field(min_length=8, max_length=128)


class FollowupUpdate(BaseModel):
    status: str
    catatan_petugas: str | None = Field(default=None, max_length=4000)


class PetugasCreate(BaseModel):
    nama: str = Field(min_length=2, max_length=120)
    peran: str = Field(default="Konselor", min_length=2, max_length=50)
    kontak: str | None = Field(default=None, max_length=120)


class PetugasUpdate(BaseModel):
    nama: str | None = Field(default=None, min_length=2, max_length=120)
    peran: str | None = Field(default=None, min_length=2, max_length=50)
    kontak: str | None = Field(default=None, max_length=120)
    aktif: bool | None = None


class AssignPetugas(BaseModel):
    """petugas_id None berarti melepas penugasan (belum ada penangani)."""

    petugas_id: int | None = None


class ScheduleCreate(BaseModel):
    """Buat sesi konseling terkonfirmasi (jadwal final, bukan preferensi)."""

    registration_id: int
    petugas_id: int
    tanggal: date
    jam_mulai: str = Field(pattern=r"^\d{1,2}:\d{2}$")
    durasi_menit: int = Field(default=60, ge=15, le=480)
    metode: str = Field(default="Tatap Muka", max_length=30)
    lokasi: str | None = Field(default=None, max_length=200)
    catatan: str | None = Field(default=None, max_length=2000)


class ScheduleUpdate(BaseModel):
    """Ubah jadwal sesi - hanya kolom yang dikirim yang diubah."""

    petugas_id: int | None = None
    tanggal: date | None = None
    jam_mulai: str | None = Field(default=None, pattern=r"^\d{1,2}:\d{2}$")
    durasi_menit: int | None = Field(default=None, ge=15, le=480)
    metode: str | None = Field(default=None, max_length=30)
    lokasi: str | None = Field(default=None, max_length=200)
    catatan: str | None = Field(default=None, max_length=2000)
    status: str | None = None


class ScheduleRemindPayload(BaseModel):
    """Kirim pengingat sesi via WhatsApp.

    target : mahasiswa | petugas | keduanya (default keduanya).
    jenis  : manual (default, dikirim admin) | h1_hari | h1_jam.
    """

    target: str = Field(default="keduanya", max_length=20)
    jenis: str = Field(default="manual", max_length=20)


class AdminCreate(BaseModel):
    """Akun admin baru - profil wajib lengkap (nama, NIM, fakultas, no. WA)."""

    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    nama_lengkap: str = Field(min_length=2, max_length=120)
    nim: str = Field(min_length=1, max_length=30)
    fakultas: str = Field(min_length=2, max_length=120)
    no_whatsapp: str = Field(min_length=9, max_length=25)
    masa_aktif_akhir: date | None = None  # None = selamanya


class AdminUpdate(BaseModel):
    """Pembaruan sebagian; kolom yang tidak dikirim tidak diubah."""

    nama_lengkap: str | None = Field(default=None, min_length=2, max_length=120)
    nim: str | None = Field(default=None, min_length=1, max_length=30)
    fakultas: str | None = Field(default=None, min_length=2, max_length=120)
    no_whatsapp: str | None = Field(default=None, min_length=9, max_length=25)
    is_active: bool | None = None
    masa_aktif_akhir: date | None = None  # kirim null eksplisit untuk menghapus batas


class AdminResetPassword(BaseModel):
    """Reset sandi langsung oleh admin lain (tanpa OTP)."""

    password_baru: str = Field(min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class ResetPasswordRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    kode: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]+$")
    password_baru: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------- auth
@router.post("/login")
def login(payload: AdminLogin, response: Response, db: Session = Depends(get_db)):
    if _login_rate_limited(payload.username):
        logger.info("LOGIN ditolak rate-limit (username=%s).", payload.username)
        raise HTTPException(429, "Terlalu banyak percobaan. Coba lagi dalam 15 menit.")

    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        _record_login_failure(payload.username)
        logger.info("LOGIN gagal (username=%s).", payload.username)
        raise HTTPException(401, "Username atau password salah.")

    # Kredensial benar, tapi akun bisa saja sudah dinonaktifkan / kedaluwarsa.
    ensure_account_usable(user)

    token = create_access_token(user.username, user.role)
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax",
        max_age=60 * 60 * 12, path="/",
    )
    logger.info("LOGIN sukses (username=%s).", user.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user.username,
        "role": user.role,
    }


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "ok"}


@router.get("/me")
def me(admin: User = Depends(get_current_admin)):
    return {
        "username": admin.username,
        "role": admin.role,
        "nama_lengkap": admin.nama_lengkap,
        "nim": admin.nim,
        "fakultas": admin.fakultas,
    }


@router.patch("/password")
def change_password(
    payload: PasswordChange,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.password_lama, admin.password_hash):
        raise HTTPException(400, "Password lama tidak sesuai.")
    admin.password_hash = hash_password(payload.password_baru)
    db.commit()
    logger.info("PASSWORD diubah (username=%s).", admin.username)
    return {"status": "ok", "pesan": "Password berhasil diperbarui."}


# ------------------------------------------------------- reset sandi via OTP WA
def _hash_otp(code: str) -> str:
    """Kode OTP disimpan sebagai hash (bukan plain text) dengan pepper SECRET_KEY."""
    return hashlib.sha256(f"otp:{code}:{settings.SECRET_KEY}".encode("utf-8")).hexdigest()


_GENERIC_RESET_MSG = (
    "Jika akun terdaftar dan aktif, kode reset telah dikirim melalui WhatsApp ke "
    "nomor yang terdaftar pada akun tersebut."
)


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Minta kode OTP reset sandi (dikirim ke nomor WhatsApp terdaftar).

    Anti-enumerasi: respons selalu generik, baik untuk username tak dikenal,
    akun nonaktif, maupun akun tanpa nomor WhatsApp (hanya log yang berbeda).
    """
    user = db.query(User).filter(User.username == payload.username.strip()).first()

    if not user or user.role != "admin":
        logger.info("RESET diminta untuk username tak dikenal.")
        return {"status": "ok", "pesan": _GENERIC_RESET_MSG}
    if account_status(user) != "aktif":
        logger.info("RESET ditolak: akun tidak aktif/kedaluwarsa (username=%s).", user.username)
        return {"status": "ok", "pesan": _GENERIC_RESET_MSG}
    if not user.no_whatsapp:
        logger.warning(
            "RESET gagal: akun %s belum punya nomor WhatsApp terdaftar.", user.username
        )
        return {"status": "ok", "pesan": _GENERIC_RESET_MSG}
    if user.otp_sent_at and (utcnow() - user.otp_sent_at).total_seconds() < settings.OTP_RESEND_SECONDS:
        raise HTTPException(
            429,
            f"Tunggu {settings.OTP_RESEND_SECONDS} detik sebelum meminta kode baru.",
        )

    code = f"{secrets.randbelow(1_000_000):06d}"
    user.otp_hash = _hash_otp(code)
    user.otp_expires_at = utcnow() + timedelta(minutes=settings.OTP_TTL_MINUTES)
    user.otp_attempts = 0
    user.otp_sent_at = utcnow()

    if not wa_service.send_whatsapp(
        user.no_whatsapp, wa_service.build_otp_message(code, settings.OTP_TTL_MINUTES)
    ):
        db.rollback()  # buang OTP yang sudah tersimpan agar tidak menggantung
        raise HTTPException(502, "Gagal mengirim kode via WhatsApp. Coba lagi nanti.")

    db.commit()
    logger.info(
        "OTP reset dikirim (username=%s, tujuan=%s****).", user.username, user.no_whatsapp[:6]
    )
    resp: dict = {"status": "ok", "pesan": _GENERIC_RESET_MSG}
    if settings.APP_ENV != "production":
        # Hanya lingkungan non-produksi: memudahkan demo/uji saat belum ada gateway WA.
        resp["debug_code"] = code
    return resp


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Verifikasi kode OTP lalu pasang kata sandi baru."""
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not user or not user.otp_hash or not user.otp_expires_at:
        raise HTTPException(400, "Kode tidak valid atau sudah kedaluwarsa. Minta kode baru.")
    if utcnow() > user.otp_expires_at:
        raise HTTPException(400, "Kode sudah kedaluwarsa. Minta kode baru.")
    if user.otp_attempts >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "Terlalu banyak percobaan. Minta kode baru.")

    if not hmac.compare_digest(_hash_otp(payload.kode), user.otp_hash):
        user.otp_attempts += 1
        db.commit()
        logger.info("OTP salah (username=%s, percobaan=%s).", user.username, user.otp_attempts)
        raise HTTPException(400, "Kode verifikasi salah.")

    if account_status(user) != "aktif":
        raise HTTPException(403, "Akun tidak dapat direset karena dinonaktifkan/masa aktif berakhir.")

    user.password_hash = hash_password(payload.password_baru)
    user.otp_hash = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    user.otp_sent_at = None
    db.commit()
    logger.info("PASSWORD direset via OTP WA (username=%s).", user.username)
    return {
        "status": "ok",
        "pesan": "Kata sandi berhasil diubah. Silakan login dengan kata sandi baru.",
    }


# ---------------------------------------------------------------- statistik
@router.get("/stats")
def stats(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    per_status = dict(
        db.query(Followup.status, func.count(Followup.id)).group_by(Followup.status).all()
    )
    per_layanan = dict(
        db.query(Registration.jenis_layanan, func.count(Registration.id))
        .group_by(Registration.jenis_layanan)
        .all()
    )
    return {
        "total_registrasi": db.query(Registration).count(),
        "total_skrining_dass21": db.query(Dass21Response).count(),
        "total_percakapan": db.query(Conversation).count(),
        "total_pesan": db.query(Message).count(),
        "perlu_ditinjau_segera": per_status.get("perlu_ditinjau_segera", 0),
        "eskalasi_otomatis": db.query(Message)
        .filter(
            Message.sender == "sistem",
            Message.message_text.like(f"{CRISIS_CONFIG['MARKER_ESKALASI']}%"),
        )
        .count(),
        "per_status": {s: per_status.get(s, 0) for s in STATUS_LIST},
        "per_jenis_layanan": per_layanan,
        "per_petugas": dict(
            db.query(Petugas.nama, func.count(Followup.id))
            .join(Followup, Followup.petugas_id == Petugas.id)
            .group_by(Petugas.nama)
            .all()
        ),
    }


# ---------------------------------------------------------------- daftar pendaftar
@router.get("/registrations")
def list_registrations(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None),
    jenis_layanan: str | None = Query(default=None, max_length=50),
    assigned: str | None = Query(default=None, pattern="^(ya|tidak)$"),
    petugas_id: int | None = Query(default=None),
    date_from: str | None = Query(default=None, description="YYYY-MM-DD"),
    date_to: str | None = Query(default=None, description="YYYY-MM-DD"),
    sort: str = Query(default="priority", pattern="^(priority|terbaru|terlama)$"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
):
    query = (
        db.query(Registration, Followup, Dass21Response, Petugas)
        .outerjoin(Followup, Followup.registration_id == Registration.id)
        .outerjoin(Dass21Response, Dass21Response.registration_id == Registration.id)
        .outerjoin(Petugas, Petugas.id == Followup.petugas_id)
    )

    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            or_(Registration.nama.ilike(like), Registration.nim.ilike(like))
        )
    if status:
        if status not in STATUS_LIST:
            raise HTTPException(422, "Status tidak dikenal.")
        query = query.filter(Followup.status == status)
    if jenis_layanan:
        query = query.filter(Registration.jenis_layanan == jenis_layanan)
    if assigned == "ya":
        query = query.filter(Followup.petugas_id.isnot(None))
    elif assigned == "tidak":
        query = query.filter(or_(Followup.id.is_(None), Followup.petugas_id.is_(None)))
    if petugas_id is not None:
        query = query.filter(Followup.petugas_id == petugas_id)
    try:
        if date_from:
            query = query.filter(Registration.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        if date_to:
            query = query.filter(
                Registration.created_at < datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            )
    except ValueError:
        raise HTTPException(422, "Format tanggal harus YYYY-MM-DD.")

    total = query.count()
    if sort == "priority":
        query = query.order_by(_PRIORITY_CASE.asc(), Registration.created_at.asc())
    elif sort == "terbaru":
        query = query.order_by(Registration.created_at.desc())
    else:
        query = query.order_by(Registration.created_at.asc())

    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    items = []
    for reg, followup, dass, petugas in rows:
        items.append({
            "id": reg.id,
            "nama": reg.nama,
            "nim": reg.nim,
            "kontak": reg.kontak,
            "jenis_layanan": reg.jenis_layanan,
            "preferensi_hari": reg.preferensi_hari,
            "preferensi_waktu": reg.preferensi_waktu,
            "punya_keluhan": bool(reg.keluhan),
            "status": followup.status if followup else "menunggu_ditinjau",
            "status_label": STATUS_LABELS.get(followup.status, followup.status) if followup else "Menunggu Ditinjau",
            "petugas": (
                {"id": petugas.id, "nama": petugas.nama, "peran": petugas.peran}
                if petugas else None
            ),
            "skor_depresi": dass.skor_depresi if dass else None,
            "skor_kecemasan": dass.skor_kecemasan if dass else None,
            "skor_stres": dass.skor_stres if dass else None,
            "sudah_skrining": dass is not None,
            "created_at": iso_utc(reg.created_at),
        })
    return {"total": total, "page": page, "per_page": per_page, "items": items}


# ---------------------------------------------------------------- detail
@router.get("/registrations/{registration_id}")
def registration_detail(
    registration_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    reg = db.get(Registration, registration_id)
    if not reg:
        raise HTTPException(404, "Pendaftaran tidak ditemukan.")

    dass = reg.dass21
    dass_payload = None
    if dass:
        jawaban = {str(i): getattr(dass, f"jawaban_{i}") for i in range(1, 22)}
        dass_payload = {
            "submitted_at": iso_utc(dass.submitted_at),
            "scoring_version": dass.scoring_version,
            "skor": {
                "depresi": dass.skor_depresi,
                "kecemasan": dass.skor_kecemasan,
                "stres": dass.skor_stres,
            },
            "kategori_umum": {
                "depresi": classify_subscale("depresi", dass.skor_depresi),
                "kecemasan": classify_subscale("kecemasan", dass.skor_kecemasan),
                "stres": classify_subscale("stres", dass.skor_stres),
            },
            "catatan_kategori": SEVERITY_DISCLAIMER,
            "jawaban": jawaban,
        }

    conversations = []
    for conv in sorted(reg.conversations, key=lambda c: c.id):
        conversations.append({
            "id": conv.id,
            "created_at": iso_utc(conv.created_at),
            "messages": [
                {
                    "sender": m.sender,  # termasuk 'sistem' (audit) untuk admin
                    "text": m.message_text,
                    "created_at": iso_utc(m.created_at),
                }
                for m in conv.messages
            ],
        })

    followup = reg.followup
    urgensi, alasan_urgensi = sched_service.hitung_urgensi(followup, dass)
    jadwal_items = [
        sched_service.serialize_schedule(
            s,
            followup.status if followup else None,
            urgensi,
        )
        for s in reg.schedules
    ]
    return {
        "id": reg.id,
        "nama": reg.nama,
        "nim": reg.nim,
        "kontak": reg.kontak,
        "jenis_layanan": reg.jenis_layanan,
        "preferensi_hari": reg.preferensi_hari,
        "preferensi_waktu": reg.preferensi_waktu,
        "keluhan": reg.keluhan,
        "consent_status": reg.consent_status,
        "created_at": iso_utc(reg.created_at),
        "dass21": dass_payload,
        "conversations": conversations,
        "jadwal": jadwal_items,
        "prioritas_penjadwalan": {"urgensi": urgensi, "alasan": alasan_urgensi},
        "followup": {
            "status": followup.status if followup else "menunggu_ditinjau",
            "status_label": STATUS_LABELS.get(followup.status, "-") if followup else "Menunggu Ditinjau",
            "catatan_petugas": followup.catatan_petugas if followup else None,
            "assigned_admin": followup.assigned_admin.username if followup and followup.assigned_admin else None,
            "petugas": (
                {
                    "id": followup.petugas.id,
                    "nama": followup.petugas.nama,
                    "peran": followup.petugas.peran,
                }
                if followup and followup.petugas else None
            ),
            "updated_at": iso_utc(followup.updated_at) if followup else None,
        },
        "meta_akses": (
            "Data sensitif (skrining, keluhan, obrolan) hanya untuk petugas berwenang. "
            "Pesan 'sistem' adalah catatan audit otomatis, tidak dikirim ke mahasiswa."
        ),
    }


# ---------------------------------------------------------------- tindak lanjut
@router.patch("/registrations/{registration_id}/followup")
def update_followup(
    registration_id: int,
    payload: FollowupUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if payload.status not in STATUS_LIST:
        raise HTTPException(422, "Status tindak lanjut tidak dikenal.")
    followup = db.query(Followup).filter(Followup.registration_id == registration_id).first()
    if not followup:
        raise HTTPException(404, "Tindak lanjut tidak ditemukan.")
    followup.status = payload.status
    if payload.catatan_petugas is not None:
        followup.catatan_petugas = payload.catatan_petugas.strip() or None
    followup.assigned_admin_id = admin.id
    followup.updated_at = utcnow()
    db.commit()
    logger.info("FOLLOWUP diperbarui (reg=%s, status=%s, oleh=%s).", registration_id, payload.status, admin.username)
    return {
        "status": followup.status,
        "status_label": STATUS_LABELS[followup.status],
        "catatan_petugas": followup.catatan_petugas,
        "assigned_admin": admin.username,
        "updated_at": iso_utc(followup.updated_at),
    }


# ---------------------------------------------------------------- petugas penangani
@router.get("/petugas")
def list_petugas(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Direktori petugas penangani + jumlah kasus yang ditanggung masing-masing."""
    counts = dict(
        db.query(Followup.petugas_id, func.count(Followup.id))
        .filter(Followup.petugas_id.isnot(None))
        .group_by(Followup.petugas_id)
        .all()
    )
    rows = db.query(Petugas).order_by(Petugas.aktif.desc(), Petugas.nama.asc()).all()
    return {
        "items": [
            {
                "id": p.id,
                "nama": p.nama,
                "peran": p.peran,
                "kontak": p.kontak,
                "aktif": p.aktif,
                "jumlah_kasus": counts.get(p.id, 0),
            }
            for p in rows
        ]
    }


@router.post("/petugas", status_code=201)
def create_petugas(
    payload: PetugasCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    petugas = Petugas(
        nama=payload.nama.strip(),
        peran=payload.peran.strip(),
        kontak=(payload.kontak.strip() or None) if payload.kontak else None,
    )
    db.add(petugas)
    db.commit()
    logger.info("PETUGAS ditambahkan (id=%s, oleh=%s).", petugas.id, admin.username)
    return {
        "id": petugas.id, "nama": petugas.nama, "peran": petugas.peran,
        "kontak": petugas.kontak, "aktif": petugas.aktif, "jumlah_kasus": 0,
    }


@router.patch("/petugas/{petugas_id}")
def update_petugas(
    petugas_id: int,
    payload: PetugasUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    petugas = db.get(Petugas, petugas_id)
    if not petugas:
        raise HTTPException(404, "Petugas tidak ditemukan.")
    if payload.nama is not None:
        petugas.nama = payload.nama.strip()
    if payload.peran is not None:
        petugas.peran = payload.peran.strip()
    if payload.kontak is not None:
        petugas.kontak = payload.kontak.strip() or None
    if payload.aktif is not None:
        petugas.aktif = payload.aktif
    db.commit()
    logger.info("PETUGAS diperbarui (id=%s, oleh=%s).", petugas_id, admin.username)
    return {
        "id": petugas.id, "nama": petugas.nama, "peran": petugas.peran,
        "kontak": petugas.kontak, "aktif": petugas.aktif,
    }


@router.delete("/petugas/{petugas_id}")
def delete_petugas(
    petugas_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    petugas = db.get(Petugas, petugas_id)
    if not petugas:
        raise HTTPException(404, "Petugas tidak ditemukan.")
    # Lepas penugasan pada kasus yang memakai petugas ini (jangan hapus kasusnya).
    db.query(Followup).filter(Followup.petugas_id == petugas_id).update(
        {"petugas_id": None}, synchronize_session=False
    )
    db.delete(petugas)
    db.commit()
    logger.info("PETUGAS dihapus (id=%s, oleh=%s).", petugas_id, admin.username)
    return {"status": "ok", "pesan": "Petugas dihapus; penugasan pada kasus dilepas."}


# ---------------------------------------------------------------- penjadwalan
@router.get("/schedule/queue")
def schedule_queue(
    limit: int = Query(default=25, ge=1, le=100),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Antrean penjadwalan TERURUT PRIORITAS: darurat (krisis) paling atas.

    Sistem hanya mengurutkan dan memberi alasan; admin tetap memilih konselor
    dan slot secara manual. Kasus yang sudah punya sesi aktif atau sudah selesai
    tidak ditampilkan.
    """
    items = sched_service.antrean_penjadwalan(db, limit=limit)
    ringkas = {"darurat": 0, "tinggi": 0, "normal": 0}
    for it in items:
        ringkas[it["urgensi"]] += 1
    return {
        "total": len(items),
        "ringkasan": ringkas,
        "items": items,
        "meta": (
            "Kasus eskalasi krisis selalu di atas. Urutan kelas berikutnya mempertimbangkan "
            "kategori skrining DASS-21 dan lama menunggu. Keputusan penugasan konselor tetap milik admin."
        ),
    }


@router.get("/schedule/week")
def schedule_week(
    start: str | None = Query(
        default=None, description="YYYY-MM-DD (hari apa pun pada minggu target; default minggu berjalan)"
    ),
    petugas_id: int | None = Query(default=None),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Jadwal satu minggu (Senin s.d. Minggu, waktu WIB) untuk tampilan kalender.

    Parameter `start` boleh jatuh pada hari apa pun; sistem menormalkannya ke
    Senin minggu tersebut. Filter `petugas_id` menampilkan sesi satu konselor saja.
    """
    today = sched_service.wib_today()
    if start:
        try:
            anchor = datetime.strptime(start, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(422, "Format start harus YYYY-MM-DD (contoh: 2025-11-17).")
    else:
        anchor = today

    monday = sched_service.monday_of(anchor)
    sunday = monday + timedelta(days=6)

    query = (
        db.query(Schedule, Followup, Dass21Response)
        .outerjoin(Followup, Followup.registration_id == Schedule.registration_id)
        .outerjoin(Dass21Response, Dass21Response.registration_id == Schedule.registration_id)
        .filter(Schedule.tanggal >= monday, Schedule.tanggal <= sunday)
    )
    if petugas_id is not None:
        query = query.filter(Schedule.petugas_id == petugas_id)
    rows = query.order_by(Schedule.tanggal.asc(), Schedule.jam_mulai.asc()).all()

    per_day: dict[date, list] = {monday + timedelta(days=i): [] for i in range(7)}
    urgensi_darurat = 0
    for sched, followup, dass in rows:
        urgensi, _ = sched_service.hitung_urgensi(followup, dass)
        if urgensi == "darurat":
            urgensi_darurat += 1
        per_day[sched.tanggal].append(
            sched_service.serialize_schedule(sched, followup.status if followup else None, urgensi)
        )

    days = [
        {
            "tanggal": d.isoformat(),
            "hari": sched_service.HARI_INDONESIA[d.weekday()],
            "is_today": d == today,
            "items": per_day[d],
        }
        for d in sorted(per_day)
    ]
    return {
        "start": monday.isoformat(),
        "end": sunday.isoformat(),
        "hari_ini": today.isoformat(),
        "total": sum(len(v) for v in per_day.values()),
        "total_darurat": urgensi_darurat,
        "days": days,
    }


@router.post("/schedule", status_code=201)
def create_schedule(
    payload: ScheduleCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Buat sesi konseling terkonfirmasi untuk satu kasus.

    Aturan:
    - Konselor WAJIB dipilih admin (kontrol penuh siapa menangani), harus aktif.
    - Tanggal tidak boleh di masa lalu (menurut WIB).
    - Sesi konselor yang sama tidak boleh tumpang tindih (bentrok -> HTTP 409).
    - Kasus dengan status `menunggu_ditinjau`/`sedang_diproses` otomatis menjadi
      `dijadwalkan`; status `perlu_ditinjau_segera` DIPERTAHANKAN agar penanda
      krisis tidak hilang sebelum petugas menyelesaikannya secara sadar.
    """
    reg = db.get(Registration, payload.registration_id)
    if not reg:
        raise HTTPException(404, "Pendaftaran tidak ditemukan.")

    petugas = db.get(Petugas, payload.petugas_id)
    if not petugas:
        raise HTTPException(404, "Petugas/konselor tidak ditemukan.")
    if not petugas.aktif:
        raise HTTPException(422, f"Konselor '{petugas.nama}' berstatus nonaktif dan tidak dapat dijadwalkan.")

    if payload.metode not in sched_service.METODE_JADWAL:
        raise HTTPException(422, "Metode harus salah satu dari: " + ", ".join(sched_service.METODE_JADWAL) + ".")

    try:
        jam_norm = sched_service.menit_ke_hhmm(sched_service.parse_hhmm(payload.jam_mulai))
    except ValueError as e:
        raise HTTPException(422, str(e))

    if payload.tanggal < sched_service.wib_today():
        raise HTTPException(422, "Tanggal sesi sudah lewat. Pilih tanggal hari ini atau setelahnya (waktu WIB).")

    bentrok = sched_service.cari_bentrok(
        db, payload.petugas_id, payload.tanggal, jam_norm, payload.durasi_menit
    )
    if bentrok:
        nama_lain = bentrok.registration.nama if bentrok.registration else "kasus lain"
        raise HTTPException(
            409,
            f"Bentrok: '{petugas.nama}' sudah menjalani sesi {nama_lain} pada "
            f"{bentrok.tanggal.isoformat()} pukul {bentrok.jam_mulai}-{sched_service.menit_ke_hhmm(sched_service.parse_hhmm(bentrok.jam_mulai) + int(bentrok.durasi_menit or 0))} WIB. "
            "Pilih jam/konselor lain.",
        )

    sched = Schedule(
        registration_id=payload.registration_id,
        petugas_id=payload.petugas_id,
        tanggal=payload.tanggal,
        jam_mulai=jam_norm,
        durasi_menit=payload.durasi_menit,
        metode=payload.metode,
        lokasi=(payload.lokasi.strip() or None) if payload.lokasi else None,
        catatan=(payload.catatan.strip() or None) if payload.catatan else None,
        status="terjadwal",
        created_by=admin.id,
    )
    db.add(sched)
    db.flush()

    # Sinkronkan status tindak lanjut (lihat docstring untuk pengecualian krisis).
    followup = db.query(Followup).filter(Followup.registration_id == payload.registration_id).first()
    if not followup:
        followup = Followup(registration_id=payload.registration_id, status="dijadwalkan")
        db.add(followup)
    elif followup.status in ("menunggu_ditinjau", "sedang_diproses"):
        followup.status = "dijadwalkan"
    followup.assigned_admin_id = admin.id
    followup.updated_at = utcnow()

    db.commit()
    logger.info(
        "JADWAL dibuat (reg=%s, tanggal=%s %s WIB, petugas=%s, oleh=%s).",
        payload.registration_id, payload.tanggal.isoformat(), jam_norm,
        petugas.id, admin.username,
    )
    return sched_service.serialize_schedule(sched, followup.status)


@router.patch("/schedule/{schedule_id}")
def update_schedule(
    schedule_id: int,
    payload: ScheduleUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Ubah jadwal sesi: geser tanggal/jam/konselor, ubah status, catatan, dsb.

    Perubahan slot tetap diperiksa bentroknya terhadap sesi aktif lain milik
    konselor terkait (sesi yang sedang diedit dikecualikan).
    """
    sched = db.get(Schedule, schedule_id)
    if not sched:
        raise HTTPException(404, "Jadwal tidak ditemukan.")

    if payload.status is not None:
        if payload.status not in sched_service.STATUS_JADWAL:
            raise HTTPException(422, "Status jadwal harus: " + ", ".join(sched_service.STATUS_JADWAL) + ".")

    if payload.petugas_id is not None and payload.petugas_id != sched.petugas_id:
        petugas = db.get(Petugas, payload.petugas_id)
        if not petugas:
            raise HTTPException(404, "Petugas/konselor tidak ditemukan.")
        if not petugas.aktif:
            raise HTTPException(422, f"Konselor '{petugas.nama}' berstatus nonaktif.")
        sched.petugas_id = payload.petugas_id

    if payload.metode is not None:
        if payload.metode not in sched_service.METODE_JADWAL:
            raise HTTPException(422, "Metode harus salah satu dari: " + ", ".join(sched_service.METODE_JADWAL) + ".")
        sched.metode = payload.metode

    if payload.jam_mulai is not None:
        try:
            sched.jam_mulai = sched_service.menit_ke_hhmm(sched_service.parse_hhmm(payload.jam_mulai))
        except ValueError as e:
            raise HTTPException(422, str(e))
    if payload.durasi_menit is not None:
        sched.durasi_menit = payload.durasi_menit
    if payload.tanggal is not None:
        sched.tanggal = payload.tanggal
    if payload.lokasi is not None:
        sched.lokasi = payload.lokasi.strip() or None
    if payload.catatan is not None:
        sched.catatan = payload.catatan.strip() or None
    if payload.status is not None:
        sched.status = payload.status

    if sched.tanggal < sched_service.wib_today() and sched.status == "terjadwal":
        raise HTTPException(422, "Tanggal sesi sudah lewat; tandai sebagai selesai/dibatalkan alih-alih menggeser ke masa lalu.")

    status_aktif = sched.status in sched_service.STATUS_AKTIF_JADWAL
    if status_aktif and sched.petugas_id:
        bentrok = sched_service.cari_bentrok(
            db, sched.petugas_id, sched.tanggal, sched.jam_mulai,
            sched.durasi_menit, exclude_id=sched.id,
        )
        if bentrok:
            nama_lain = bentrok.registration.nama if bentrok.registration else "kasus lain"
            raise HTTPException(
                409,
                f"Bentrok: sesi '{nama_lain}' ({bentrok.tanggal.isoformat()} pukul {bentrok.jam_mulai} WIB) "
                "sudah memakai slot konselor ini. Pilih jam/konselor lain.",
            )

    sched.updated_at = utcnow()
    db.commit()
    logger.info(
        "JADWAL diubah (id=%s, reg=%s, status=%s, oleh=%s).",
        sched.id, sched.registration_id, sched.status, admin.username,
    )
    followup = db.query(Followup).filter(Followup.registration_id == sched.registration_id).first()
    return sched_service.serialize_schedule(sched, followup.status if followup else None)


@router.delete("/schedule/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Hapus permanen satu jadwal (untuk salah input).

    Untuk pembatalan yang perlu tercatat, gunakan PATCH status='dibatalkan'.
    """
    sched = db.get(Schedule, schedule_id)
    if not sched:
        raise HTTPException(404, "Jadwal tidak ditemukan.")
    reg_id = sched.registration_id
    db.delete(sched)
    db.commit()
    logger.info(
        "JADWAL dihapus (id=%s, reg=%s, oleh=%s).", schedule_id, reg_id, admin.username
    )
    return {"status": "ok", "pesan": "Jadwal dihapus."}


@router.get("/schedule/month")
def schedule_month(
    month: str | None = Query(
        default=None, description="YYYY-MM; default bulan berjalan (WIB)"
    ),
    petugas_id: int | None = Query(default=None),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Jadwal satu BULAN sebagai grid kalender (minggu mulai Senin, waktu WIB).

    Mengembalikan 5-6 minggu; hari di luar bulan tetap ikut agar grid kalender
    utuh seperti kalender umum. Filter `petugas_id` menampilkan sesi satu
    konselor saja.
    """
    today = sched_service.wib_today()
    if month:
        try:
            year_s, mon_s = month.split("-")
            year, mon = int(year_s), int(mon_s)
            if not (2000 <= year <= 2100 and 1 <= mon <= 12):
                raise ValueError
        except ValueError:
            raise HTTPException(422, "Format month harus YYYY-MM (contoh: 2025-11).")
    else:
        year, mon = today.year, today.month

    start, end = sched_service.month_grid_bounds(year, mon)
    query = (
        db.query(Schedule, Followup, Dass21Response)
        .outerjoin(Followup, Followup.registration_id == Schedule.registration_id)
        .outerjoin(Dass21Response, Dass21Response.registration_id == Schedule.registration_id)
        .filter(Schedule.tanggal >= start, Schedule.tanggal <= end)
    )
    if petugas_id is not None:
        query = query.filter(Schedule.petugas_id == petugas_id)
    rows = query.order_by(Schedule.tanggal.asc(), Schedule.jam_mulai.asc()).all()

    per_day: dict[date, list] = {}
    total_darurat = 0
    for sched, followup, dass in rows:
        urgensi, _ = sched_service.hitung_urgensi(followup, dass)
        if urgensi == "darurat":
            total_darurat += 1
        per_day.setdefault(sched.tanggal, []).append(
            sched_service.serialize_schedule(sched, followup.status if followup else None, urgensi)
        )

    weeks = [
        {
            "days": [
                {
                    "tanggal": d.isoformat(),
                    "hari": sched_service.HARI_INDONESIA[d.weekday()],
                    "is_today": d == today,
                    "in_month": d.month == mon,
                    "items": per_day.get(d, []),
                }
                for d in wk
            ]
        }
        for wk in sched_service.week_rows(start, end)
    ]
    return {
        "month": f"{year:04d}-{mon:02d}",
        "label": f"{sched_service.NAMA_BULAN[mon - 1]} {year}",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "hari_ini": today.isoformat(),
        "total": sum(len(v) for v in per_day.values()),
        "total_darurat": total_darurat,
        "weeks": weeks,
    }


@router.get("/schedule/reminders")
def schedule_reminders(
    days: int = Query(default=7, ge=1, le=30, description="Jangka hari ke depan"),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Daftar sesi AKTIF dalam `days` hari ke depan + status pengingatnya.

    - pengingat_due      : jenis pengingat yang JATUH TEMPO tapi BELUM terkirim
                           (h1_hari bila sesi <= 24 jam lagi; h1_jam bila <= 60
                           menit lagi). Dipakai untuk badge lonceng dashboard.
    - pengingat_terkirim : jenis pengingat yang sudah berhasil dikirim.
    - nomor_wa           : nomor tujuan valid (62...); null bila kontak bukan
                           nomor WhatsApp sehingga WA tidak bisa dikirim.
    Notifikasi aplikasi (browser) di dashboard admin muncul otomatis untuk sesi
    yang masuk masa H-1 jam; WA dikirim manual oleh admin dari panel pengingat.
    """
    items = sched_service.upcoming_sessions(db, days_ahead=days)
    total_due = sum(1 for it in items if it["pengingat_due"])
    return {
        "hari_ini": sched_service.wib_today().isoformat(),
        "days_ahead": days,
        "total": len(items),
        "total_due": total_due,
        "items": items,
        "meta": (
            "Pengingat H-1 hari jatuh tempo <= 24 jam sebelum sesi; H-1 jam <= 60 menit. "
            "Kirim WA dari panel pengingat; seluruh pengiriman tercatat untuk audit."
        ),
    }


@router.post("/schedule/{schedule_id}/remind")
def send_schedule_reminder(
    schedule_id: int,
    payload: ScheduleRemindPayload,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Kirim pengingat WhatsApp untuk satu sesi (ke mahasiswa dan/atau konselor).

    - Hanya sesi berstatus `terjadwal`/`ditunda` yang belum berlangsung.
    - Kontak dinormalisasi ke 62...; kontak email/kosong dicatat GAGAL dengan
      keterangan jelas (tidak diam-diam dilewati).
    - Setiap percobaan dicatat pada tabel schedule_reminders (audit + anti
      duplikat). Isi pesan hanya info jadwal - tanpa data sensitif kasus.
    """
    sched = db.get(Schedule, schedule_id)
    if not sched:
        raise HTTPException(404, "Jadwal tidak ditemukan.")
    if payload.target not in sched_service.TARGET_PENGINGAT:
        raise HTTPException(422, "target harus salah satu dari: " + ", ".join(sched_service.TARGET_PENGINGAT) + ".")
    if payload.jenis not in sched_service.JENIS_PENGINGAT:
        raise HTTPException(422, "jenis harus salah satu dari: " + ", ".join(sched_service.JENIS_PENGINGAT) + ".")
    if sched.status not in sched_service.STATUS_AKTIF_JADWAL:
        raise HTTPException(422, "Pengingat hanya untuk sesi berstatus terjadwal/ditunda.")
    if sched_service.selisih_menit(sched) <= 0:
        raise HTTPException(422, "Waktu sesi sudah berlalu; pengingat tidak diperlukan.")

    reg = sched.registration
    petugas = sched.petugas
    kandidat: list[tuple[str, str | None]] = []
    if payload.target in ("mahasiswa", "keduanya"):
        kandidat.append(("mahasiswa", reg.kontak if reg else None))
    if payload.target in ("petugas", "keduanya"):
        kandidat.append(("petugas", petugas.kontak if petugas else None))

    hasil = []
    for label, raw in kandidat:
        nomor = wa_service.normalize_wa(raw)
        if not nomor:
            db.add(ScheduleReminder(
                schedule_id=sched.id, jenis=payload.jenis, channel="wa",
                target=label, nomor_tujuan=None, status="gagal",
                keterangan="Kontak kosong atau bukan nomor WhatsApp.",
                created_by=admin.id,
            ))
            hasil.append({
                "target": label, "status": "gagal", "nomor": None,
                "keterangan": "Kontak kosong atau bukan nomor WhatsApp (mis. email). Isi nomor WA agar pengingat dapat dikirim.",
            })
            continue
        ok = wa_service.send_whatsapp(nomor, sched_service.build_reminder_message(sched, label))
        db.add(ScheduleReminder(
            schedule_id=sched.id, jenis=payload.jenis, channel="wa",
            target=label, nomor_tujuan=nomor,
            status="terkirim" if ok else "gagal",
            keterangan=None if ok else "Gateway WhatsApp gagal mengirim (cek WA_PROVIDER/WA_API_TOKEN).",
            created_by=admin.id,
        ))
        hasil.append({
            "target": label,
            "status": "terkirim" if ok else "gagal",
            "nomor": nomor,
            "keterangan": None if ok else "Gateway WhatsApp gagal mengirim.",
        })

    db.commit()
    logger.info(
        "PENGINGAT dikirim (jadwal=%s, target=%s, jenis=%s, oleh=%s).",
        schedule_id, payload.target, payload.jenis, admin.username,
    )
    return {
        "status": "ok",
        "schedule_id": sched.id,
        "hasil": hasil,
        "meta": "Pada WA_PROVIDER=mock pesan hanya dicatat di log server (mode demo). Isi nomor WA mahasiswa/konselor agar terkirim nyata.",
    }


# ------------------------------------------------------- manajemen akun admin
def _serialize_admin(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "nama_lengkap": u.nama_lengkap,
        "nim": u.nim,
        "fakultas": u.fakultas,
        "no_whatsapp": u.no_whatsapp,
        "is_active": u.is_active,
        "masa_aktif_akhir": u.masa_aktif_akhir.isoformat() if u.masa_aktif_akhir else None,
        "status": account_status(u),  # aktif | nonaktif | kedaluwarsa
        "created_at": iso_utc(u.created_at),
    }


def _is_currently_active(u: User) -> bool:
    return account_status(u) == "aktif"


def _active_admin_count(db: Session, exclude_id: int | None = None) -> int:
    """Jumlah admin yang statusnya benar-benar bisa login saat ini."""
    rows = db.query(User).filter(User.role == "admin", User.is_active == True).all()  # noqa: E712
    return sum(
        1
        for u in rows
        if u.id != exclude_id and (u.masa_aktif_akhir is None or u.masa_aktif_akhir >= date.today())
    )


@router.get("/admins")
def list_admins(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Daftar seluruh akun admin + status aksesnya (untuk dashboard)."""
    rows = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).all()
    return {"items": [_serialize_admin(u) for u in rows]}


@router.post("/admins", status_code=201)
def create_admin_account(
    payload: AdminCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Buat akun admin baru dengan profil wajib (nama, NIM, fakultas, no. WA)."""
    uname = payload.username.strip()
    if db.query(User).filter(User.username == uname).first():
        raise HTTPException(400, "Username sudah dipakai.")
    wa = wa_service.normalize_wa(payload.no_whatsapp)
    if not wa:
        raise HTTPException(422, "Nomor WhatsApp tidak valid. Contoh: 08123456789 / 628123456789.")

    user = User(
        username=uname,
        password_hash=hash_password(payload.password),
        role="admin",
        nama_lengkap=payload.nama_lengkap.strip(),
        nim=payload.nim.strip(),
        fakultas=payload.fakultas.strip(),
        no_whatsapp=wa,
        is_active=True,
        masa_aktif_akhir=payload.masa_aktif_akhir,
    )
    db.add(user)
    db.commit()
    logger.info("ADMIN dibuat (id=%s username=%s oleh=%s).", user.id, user.username, admin.username)
    return _serialize_admin(user)


@router.put("/admins/{user_id}")
def update_admin_account(
    user_id: int,
    payload: AdminUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Perbarui profil/atur akses satu akun admin (hanya kolom yang dikirim)."""
    user = db.query(User).filter(User.id == user_id, User.role == "admin").first()
    if not user:
        raise HTTPException(404, "Akun admin tidak ditemukan.")

    fset = payload.model_fields_set
    if payload.nama_lengkap is not None:
        user.nama_lengkap = payload.nama_lengkap.strip()
    if payload.nim is not None:
        user.nim = payload.nim.strip()
    if payload.fakultas is not None:
        user.fakultas = payload.fakultas.strip()
    if "no_whatsapp" in fset and payload.no_whatsapp is not None:
        wa = wa_service.normalize_wa(payload.no_whatsapp)
        if not wa:
            raise HTTPException(422, "Nomor WhatsApp tidak valid. Contoh: 08123456789.")
        user.no_whatsapp = wa
    if "masa_aktif_akhir" in fset:
        # Nilai null eksplisit berarti menghapus batas masa aktif (selamanya).
        user.masa_aktif_akhir = payload.masa_aktif_akhir
    if payload.is_active is not None and payload.is_active != user.is_active:
        if payload.is_active is False:
            if user.id == admin.id:
                raise HTTPException(400, "Tidak bisa menonaktifkan akun sendiri.")
            if _is_currently_active(user) and _active_admin_count(db, exclude_id=user.id) == 0:
                raise HTTPException(400, "Minimal harus ada satu admin yang aktif.")
        user.is_active = payload.is_active

    db.commit()
    logger.info("ADMIN diperbarui (id=%s username=%s oleh=%s).", user.id, user.username, admin.username)
    return _serialize_admin(user)


@router.delete("/admins/{user_id}")
def delete_admin_account(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Hapus permanen satu akun admin (jejak assigned_admin_id dilepas, bukan ikut terhapus)."""
    user = db.query(User).filter(User.id == user_id, User.role == "admin").first()
    if not user:
        raise HTTPException(404, "Akun admin tidak ditemukan.")
    if user.id == admin.id:
        raise HTTPException(400, "Tidak bisa menghapus akun sendiri.")
    if _is_currently_active(user) and _active_admin_count(db, exclude_id=user.id) == 0:
        raise HTTPException(400, "Minimal harus ada satu admin yang aktif.")

    db.query(Followup).filter(Followup.assigned_admin_id == user.id).update(
        {"assigned_admin_id": None}, synchronize_session=False
    )
    db.delete(user)
    db.commit()
    logger.info("ADMIN dihapus (id=%s username=%s oleh=%s).", user_id, user.username, admin.username)
    return {"status": "ok", "pesan": f"Akun '{user.username}' telah dihapus."}


@router.post("/admins/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    payload: AdminResetPassword,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Reset kata sandi langsung oleh admin (mis. nomor WA target tidak tersedia)."""
    user = db.query(User).filter(User.id == user_id, User.role == "admin").first()
    if not user:
        raise HTTPException(404, "Akun admin tidak ditemukan.")
    user.password_hash = hash_password(payload.password_baru)
    user.otp_hash = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    user.otp_sent_at = None
    db.commit()
    logger.info(
        "PASSWORD direset admin (target=%s oleh=%s).", user.username, admin.username
    )
    return {"status": "ok", "pesan": f"Kata sandi untuk '{user.username}' telah direset."}


@router.put("/registrations/{registration_id}/assign")
def assign_petugas(
    registration_id: int,
    payload: AssignPetugas,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Menetapkan/melepas petugas penangani untuk satu pendaftaran."""
    reg = db.get(Registration, registration_id)
    if not reg:
        raise HTTPException(404, "Pendaftaran tidak ditemukan.")

    if payload.petugas_id is not None:
        petugas = db.get(Petugas, payload.petugas_id)
        if not petugas:
            raise HTTPException(404, "Petugas tidak ditemukan.")

    followup = db.query(Followup).filter(Followup.registration_id == registration_id).first()
    if not followup:
        followup = Followup(registration_id=registration_id, status="menunggu_ditinjau")
        db.add(followup)
        db.flush()

    followup.petugas_id = payload.petugas_id
    followup.assigned_admin_id = admin.id
    followup.updated_at = utcnow()
    db.commit()
    logger.info(
        "PENUGASAN kasus reg=%s -> petugas=%s (oleh=%s).",
        registration_id, payload.petugas_id, admin.username,
    )
    return {
        "status": followup.status,
        "status_label": STATUS_LABELS.get(followup.status, followup.status),
        "petugas": (
            {"id": followup.petugas.id, "nama": followup.petugas.nama, "peran": followup.petugas.peran}
            if followup.petugas else None
        ),
        "updated_at": iso_utc(followup.updated_at),
    }


# ---------------------------------------------------------------- analisis AI terpadu
@router.post("/registrations/{registration_id}/analysis")
def analyze_registration(
    registration_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Analisis kasus terpadu berbantuan LLM: keluhan + DASS-21 + obrolan.

    - Hanya admin (RBAC). Analisis dibuat on-demand saat diminta, tidak disimpan.
    - Penyedia LLM mengikuti gerbang privasi LLM_ALLOW_EXTERNAL (default: mock, offline).
    - Hasil BUKAN diagnosis; log audit hanya mencatat akses tanpa isi data.
    """
    reg = db.get(Registration, registration_id)
    if not reg:
        raise HTTPException(404, "Pendaftaran tidak ditemukan.")
    return analysis_service.generate_case_analysis(db, reg)


# ---------------------------------------------------------------- ekspor CSV
@router.get("/export/registrations.csv")
def export_registrations_csv(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    include_sensitive: bool = Query(default=False, description="true = sertakan keluhan & skor DASS-21"),
):
    """Ekspor CSV pendaftaran.

    Default hanya kolom non-sensitif. Kolom sensitif (keluhan + skor DASS-21)
    hanya disertakan bila include_sensitive=true, dan setiap ekspor dicatat ke log
    audit (tanpa isi data).
    """
    rows = (
        db.query(Registration, Followup, Dass21Response, Petugas)
        .outerjoin(Followup, Followup.registration_id == Registration.id)
        .outerjoin(Dass21Response, Dass21Response.registration_id == Registration.id)
        .outerjoin(Petugas, Petugas.id == Followup.petugas_id)
        .order_by(Registration.created_at.asc())
        .all()
    )

    basic_header = [
        "id", "tanggal_daftar", "nama", "nim", "kontak", "jenis_layanan",
        "preferensi_hari", "preferensi_waktu", "status", "petugas_penangani", "catatan_petugas",
    ]
    sensitive_header = ["keluhan", "skor_depresi", "skor_kecemasan", "skor_stres", "scoring_version"]

    buffer = io.StringIO()
    buffer.write("\ufeff")  # BOM agar Excel membaca UTF-8 dengan benar
    writer = csv.writer(buffer)
    writer.writerow(basic_header + (sensitive_header if include_sensitive else []))

    for reg, followup, dass, petugas in rows:
        row = [
            reg.id,
            iso_utc(reg.created_at),
            reg.nama,
            reg.nim,
            reg.kontak,
            reg.jenis_layanan,
            reg.preferensi_hari,
            reg.preferensi_waktu,
            followup.status if followup else "",
            (petugas.nama if petugas else ""),
            (followup.catatan_petugas or "").replace("\n", " ") if followup else "",
        ]
        if include_sensitive:
            row += [
                (reg.keluhan or "").replace("\n", " "),
                dass.skor_depresi if dass else "",
                dass.skor_kecemasan if dass else "",
                dass.skor_stres if dass else "",
                dass.scoring_version if dass else "",
            ]
        writer.writerow(row)

    logger.info(
        "EKSPOR CSV oleh=%s sensitif=%s jumlah_baris=%d", admin.username, include_sensitive, len(rows)
    )
    filename = "registrations_sensitive.csv" if include_sensitive else "registrations.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
