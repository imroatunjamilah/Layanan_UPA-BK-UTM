"""Endpoint chatbot (ruang obrolan mahasiswa).

Alur keamanan & keselamatan pada setiap pesan:
1. Verifikasi identitas akses (registration_id + chat_token) - mencegah akses lintas mahasiswa.
2. Pastikan skrining DASS-21 sudah diisi (urutan layanan: daftar -> skrining -> obrolan).
3. Simpan pesan mahasiswa.
4. Lapisan keselamatan berbasis kata kunci (TIDAK bergantung pada LLM):
   - indikasi krisis -> balas pesan keamanan baku + tandai tindak lanjut (konfigurasi CRISIS_CONFIG);
   - permintaan pendampingan manusia -> konfirmasi dicatat, tanpa janji respons langsung;
   - selain itu -> panggil penyedia LLM (mock/openai-compatible) dengan system prompt terpisah.
5. Log tanpa isi pesan (privasi).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversation, Message, Registration
from ..security import verify_chat_token
from ..services import crisis
from ..services.llm import manager as llm_manager
from ..utils import iso_utc, utcnow

router = APIRouter(prefix="/api/chat", tags=["Chatbot"])
logger = logging.getLogger("app.chat")

_STUDENT_SENDERS = ("mahasiswa", "bot")  # "sistem" hanya untuk audit admin


def _get_verified_registration(db: Session, registration_id: int, chat_token: str) -> Registration:
    reg = db.get(Registration, registration_id)
    if not reg:
        raise HTTPException(404, "Pendaftaran tidak ditemukan.")
    if not verify_chat_token(reg.id, chat_token):
        raise HTTPException(403, "Token akses tidak valid untuk pendaftaran ini.")
    if not reg.dass21:
        raise HTTPException(
            403, "Silakan selesaikan skrining DASS-21 terlebih dahulu di halaman skrining."
        )
    return reg


def _get_or_create_conversation(db: Session, reg: Registration, conversation_id: int | None) -> Conversation:
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if conv and conv.registration_id == reg.id:
            return conv
        raise HTTPException(404, "Percakapan tidak ditemukan.")
    conv = (
        db.query(Conversation)
        .filter(Conversation.registration_id == reg.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .first()
    )
    if not conv:
        conv = Conversation(registration_id=reg.id)
        db.add(conv)
        db.flush()
    return conv


def _serialize(messages, include_sistem: bool = False) -> list[dict]:
    out = []
    for m in messages:
        if not include_sistem and m.sender not in _STUDENT_SENDERS:
            continue
        out.append({"sender": m.sender, "text": m.message_text, "created_at": iso_utc(m.created_at)})
    return out


class ChatStart(BaseModel):
    registration_id: int
    chat_token: str


class ChatMessage(BaseModel):
    registration_id: int
    chat_token: str
    conversation_id: int | None = None
    text: str = Field(min_length=1, max_length=2000)


@router.post("/start")
def start_chat(payload: ChatStart, db: Session = Depends(get_db)):
    reg = _get_verified_registration(db, payload.registration_id, payload.chat_token)
    conv = _get_or_create_conversation(db, reg, None)
    db.commit()
    history = _serialize(conv.messages)
    return {
        "conversation_id": conv.id,
        "nama": reg.nama,
        "pesan_pembuka": (
            f"Halo, {reg.nama}. Selamat datang di ruang obrolan UPA BK. Saya di sini "
            "untuk mendengarkan cerita Anda. Apa yang sedang Anda rasakan belakangan ini?"
        ) if not history else "",
        "disclaimer": crisis.DISCLAIMER_CHAT,
        "riwayat": history,
    }


@router.post("/message")
def send_message(payload: ChatMessage, db: Session = Depends(get_db)):
    reg = _get_verified_registration(db, payload.registration_id, payload.chat_token)
    conv = _get_or_create_conversation(db, reg, payload.conversation_id)

    text = payload.text.strip()
    if not text:
        raise HTTPException(422, "Pesan tidak boleh kosong.")

    # 1) simpan pesan mahasiswa (flush agar ikut terbaca pada history di bawah)
    db.add(Message(conversation_id=conv.id, sender="mahasiswa", message_text=text))
    db.flush()

    # 2) lapisan keselamatan (independen dari LLM)
    if crisis.detect_crisis(text):
        db.add(Message(conversation_id=conv.id, sender="bot", message_text=crisis.SAFETY_MESSAGE))
        db.add(Message(
            conversation_id=conv.id, sender="sistem",
            message_text=f"{crisis.CRISIS_CONFIG['MARKER_ESKALASI']} Potensi krisis terdeteksi pada pesan mahasiswa - mohon verifikasi dan tindak lanjut segera oleh petugas.",
        ))
        followup = reg.followup
        if (
            followup
            and crisis.CRISIS_CONFIG["AUTO_ESCALATE_FOLLOWUP"]
            and followup.status != crisis.CRISIS_CONFIG["STATUS_ESKALASI"]
        ):
            followup.status = crisis.CRISIS_CONFIG["STATUS_ESKALASI"]
            auto_note = (
                f"{crisis.CRISIS_CONFIG['MARKER_OTOMATIS']} Sistem menandai potensi krisis "
                "saat obrolan (sesuai konfigurasi default yang perlu persetujuan UPA BK)."
            )
            followup.catatan_petugas = (
                f"{followup.catatan_petugas}\n{auto_note}" if followup.catatan_petugas else auto_note
            )
        conv.updated_at = utcnow()
        db.commit()
        logger.info("KRISIS: eskalasi dicatat (reg=%s, conv=%s).", reg.id, conv.id)
        return {
            "reply": crisis.SAFETY_MESSAGE,
            "conversation_id": conv.id,
            "eskalasi": True,
        }

    if crisis.detect_handoff(text):
        db.add(Message(conversation_id=conv.id, sender="bot", message_text=crisis.HANDOFF_ACKNOWLEDGMENT))
        followup = reg.followup
        marker = f"{crisis.CRISIS_CONFIG['MARKER_OTOMATIS']} Mahasiswa meminta pendampingan manusia/konselor."
        if followup and (not followup.catatan_petugas or marker not in followup.catatan_petugas):
            followup.catatan_petugas = (
                f"{followup.catatan_petugas}\n{marker}" if followup.catatan_petugas else marker
            )
        conv.updated_at = utcnow()
        db.commit()
        logger.info("HANDOFF: permintaan manusia dicatat (reg=%s, conv=%s).", reg.id, conv.id)
        return {"reply": crisis.HANDOFF_ACKNOWLEDGMENT, "conversation_id": conv.id, "eskalasi": False}

    # 3) LLM
    history = [
        {"sender": m.sender, "text": m.message_text}
        for m in conv.messages if m.sender in _STUDENT_SENDERS
    ]
    reply, error_code = llm_manager.generate_reply(history)
    db.add(Message(conversation_id=conv.id, sender="bot", message_text=reply))
    conv.updated_at = utcnow()
    db.commit()
    if error_code:
        logger.info("LLM fallback dipakai (reg=%s, jenis=%s).", reg.id, error_code)
    logger.info("Pesan obrolan diproses (reg=%s, conv=%s, panjang=%d).", reg.id, conv.id, len(text))
    return {"reply": reply, "conversation_id": conv.id, "eskalasi": False}


@router.get("/history")
def get_history(registration_id: int, chat_token: str, db: Session = Depends(get_db)):
    """Riwayat obrolan milik mahasiswa sendiri (tanpa pesan audit 'sistem')."""
    reg = _get_verified_registration(db, registration_id, chat_token)
    conv = (
        db.query(Conversation)
        .filter(Conversation.registration_id == reg.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .first()
    )
    if not conv:
        return {"conversation_id": None, "riwayat": []}
    return {"conversation_id": conv.id, "riwayat": _serialize(conv.messages)}
