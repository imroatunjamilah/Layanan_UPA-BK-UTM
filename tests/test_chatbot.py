"""Pengujian chatbot: sesi obrolan, persistensi, krisis, permintaan manusia, akses."""
from sqlalchemy.orm import sessionmaker

from app.models import Conversation, Followup, Message
from app.services.crisis import CRISIS_CONFIG
from app.services.llm.base import LLMProvider
from app.services.llm.manager import get_provider, load_system_prompt
from app.services.llm.mock_provider import MockLLMProvider

from .conftest import register_student, submit_dass


def _mulai_obrolan(client, reg):
    res = client.post("/api/chat/start", json={
        "registration_id": reg["registration_id"], "chat_token": reg["chat_token"]})
    assert res.status_code == 200, res.text
    return res.json()


def test_obrolan_ditolak_sebelum_skrining(client, db):
    reg = register_student(client)
    res = client.post("/api/chat/start", json={
        "registration_id": reg["registration_id"], "chat_token": reg["chat_token"]})
    assert res.status_code == 403
    assert "DASS-21" in res.json()["detail"]


def test_mulai_obrolan_mengembalikan_pembuka_dan_disclaimer(client, db, sample_registration):
    data = _mulai_obrolan(client, sample_registration)
    assert data["conversation_id"] > 0
    assert "Halo" in data["pesan_pembuka"]
    assert "bukan pengganti" in data["disclaimer"].lower() or "BUKAN" in data["disclaimer"]


def test_pesan_tersimpan_dan_dibalas_bot(client, db, sample_registration):
    data = _mulai_obrolan(client, sample_registration)
    res = client.post("/api/chat/message", json={
        "registration_id": sample_registration["registration_id"],
        "chat_token": sample_registration["chat_token"],
        "conversation_id": data["conversation_id"],
        "text": "Halo, saya sedang stres menghadapi ujian akhir.",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["reply"]
    assert body["eskalasi"] is False

    pesan = (db.query(Message)
             .filter(Message.conversation_id == data["conversation_id"])
             .order_by(Message.id).all())
    assert [p.sender for p in pesan] == ["mahasiswa", "bot"]
    assert pesan[0].message_text == "Halo, saya sedang stres menghadapi ujian akhir."


def test_riwayat_tidak_menyertakan_pesan_sistem(client, db, sample_registration):
    data = _mulai_obrolan(client, sample_registration)
    client.post("/api/chat/message", json={
        "registration_id": sample_registration["registration_id"],
        "chat_token": sample_registration["chat_token"],
        "conversation_id": data["conversation_id"],
        "text": "Saya ingin mengakhiri hidup.",
    })
    res = client.get(
        f"/api/chat/history?registration_id={sample_registration['registration_id']}"
        f"&chat_token={sample_registration['chat_token']}")
    assert res.status_code == 200
    riwayat = res.json()["riwayat"]
    assert riwayat, "Riwayat tidak boleh kosong."
    assert all(m["sender"] != "sistem" for m in riwayat)
    # tetap ada di database untuk audit admin
    total_sistem = db.query(Message).filter(Message.sender == "sistem").count()
    assert total_sistem >= 1


def test_deteksi_krisis_memunculkan_pesan_keamanan_dan_eskalasi(client, db, sample_registration):
    data = _mulai_obrolan(client, sample_registration)
    res = client.post("/api/chat/message", json={
        "registration_id": sample_registration["registration_id"],
        "chat_token": sample_registration["chat_token"],
        "conversation_id": data["conversation_id"],
        "text": "Kadang saya merasa ingin mengakhiri hidup saja.",
    })
    body = res.json()
    assert body["eskalasi"] is True
    assert "112" in body["reply"] and "119" in body["reply"]

    # tindak lanjut otomatis naik ke status eskalasi
    followup = db.query(Followup).filter_by(registration_id=sample_registration["registration_id"]).one()
    assert followup.status == CRISIS_CONFIG["STATUS_ESKALASI"]
    assert CRISIS_CONFIG["MARKER_OTOMATIS"] in (followup.catatan_petugas or "")

    # pesan audit sistem tersimpan
    sistem = (db.query(Message)
              .filter(Message.conversation_id == data["conversation_id"],
                      Message.sender == "sistem").all())
    assert len(sistem) == 1
    assert sistem[0].message_text.startswith(CRISIS_CONFIG["MARKER_ESKALASI"])


def test_varian_kata_krisis_juga_terdeteksi(client, db, sample_registration):
    data = _mulai_obrolan(client, sample_registration)
    res = client.post("/api/chat/message", json={
        "registration_id": sample_registration["registration_id"],
        "chat_token": sample_registration["chat_token"],
        "conversation_id": data["conversation_id"],
        "text": "saya pengen mati aja",
    })
    assert res.json()["eskalasi"] is True


def test_permintaan_pendampingan_manusia_dicatat_tanpa_janji_respons_langsung(client, db, sample_registration):
    data = _mulai_obrolan(client, sample_registration)
    res = client.post("/api/chat/message", json={
        "registration_id": sample_registration["registration_id"],
        "chat_token": sample_registration["chat_token"],
        "conversation_id": data["conversation_id"],
        "text": "Saya ingin bicara dengan konselor.",
    })
    body = res.json()
    assert body["eskalasi"] is False
    assert "tidak dapat menjamin" in body["reply"]  # tanpa janji respons manusia langsung

    followup = db.query(Followup).filter_by(registration_id=sample_registration["registration_id"]).one()
    assert "pendampingan manusia" in (followup.catatan_petugas or "")


def test_token_salah_ditolak(client, db, sample_registration):
    res = client.post("/api/chat/message", json={
        "registration_id": sample_registration["registration_id"],
        "chat_token": "token-palsu",
        "conversation_id": None,
        "text": "halo",
    })
    assert res.status_code == 403


def test_pendaftaran_tak_dikenal_404(client, db):
    res = client.post("/api/chat/start", json={"registration_id": 424242, "chat_token": "x" * 32})
    assert res.status_code == 404


def test_pesan_kosong_ditolak(client, db, sample_registration):
    data = _mulai_obrolan(client, sample_registration)
    res = client.post("/api/chat/message", json={
        "registration_id": sample_registration["registration_id"],
        "chat_token": sample_registration["chat_token"],
        "conversation_id": data["conversation_id"],
        "text": "   ",
    })
    assert res.status_code == 422


# ---------------------------------------------------------------- unit provider LLM
def test_provider_mock_merupakan_llm_provider():
    assert isinstance(MockLLMProvider(), LLMProvider)
    assert isinstance(get_provider(), LLMProvider)


def test_provider_mock_merespons_intent_sapaan():
    reply = MockLLMProvider().generate_reply(
        "sys", [{"sender": "mahasiswa", "text": "Halo, selamat siang"}])
    assert "Halo" in reply or "menemani" in reply


def test_provider_mock_merespons_intent_sedih():
    reply = MockLLMProvider().generate_reply(
        "sys", [{"sender": "mahasiswa", "text": "Saya sedih sekali akhir-akhir ini"}])
    assert reply  # balasan empatik ada


def test_system_prompt_dimuat_dari_file_terpisah():
    prompt = load_system_prompt()
    assert "Protokol Krisis" in prompt
    assert "Jangan memberi diagnosis" in prompt or "diagnosis" in prompt.lower()
