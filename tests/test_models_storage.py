"""Pengujian penyimpanan database: FK, constraint unik, cascade, indeks, timestamps."""
import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Conversation,
    Dass21Response,
    Followup,
    Message,
    Registration,
    User,
)
from app.security import hash_password


def _buat_registration(db, nim="2101107777") -> Registration:
    reg = Registration(
        nama="Uji Basis Data", nim=nim, kontak="uji@mail.contoh.ac.id",
        jenis_layanan="Konseling Individu", preferensi_hari="Senin",
        preferensi_waktu="Pagi (08.00-11.00)", keluhan=None, consent_status="disetujui",
    )
    db.add(reg)
    db.flush()
    return reg


def test_foreign_key_ditegakkan_message_tanpa_conversation(client, db):
    db.add(Message(conversation_id=999999, sender="bot", message_text="x"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_foreign_key_ditegakkan_dass_tanpa_registration(client, db):
    data = {f"jawaban_{i}": 0 for i in range(1, 22)}
    db.add(Dass21Response(
        registration_id=999999, scoring_version="x",
        skor_depresi=0, skor_kecemasan=0, skor_stres=0, **data,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_username_admin_harus_unik(client, db):
    db.add(User(username="sama", password_hash=hash_password("sandi12345"), role="admin"))
    db.commit()
    db.add(User(username="sama", password_hash=hash_password("sandi67890"), role="admin"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_satu_dass_per_pendaftaran(client, db):
    reg = _buat_registration(db)
    data = {f"jawaban_{i}": 0 for i in range(1, 22)}
    db.add(Dass21Response(
        registration_id=reg.id, scoring_version="v1",
        skor_depresi=0, skor_kecemasan=0, skor_stres=0, **data,
    ))
    db.commit()
    db.add(Dass21Response(
        registration_id=reg.id, scoring_version="v1",
        skor_depresi=1, skor_kecemasan=1, skor_stres=1, **data,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_satu_followup_per_pendaftaran(client, db):
    reg = _buat_registration(db)
    db.add(Followup(registration_id=reg.id, status="menunggu_ditinjau"))
    db.commit()
    db.add(Followup(registration_id=reg.id, status="selesai"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_hapus_pendaftaran_menghapus_data_terkait_cascade(client, db):
    reg = _buat_registration(db)
    data = {f"jawaban_{i}": 1 for i in range(1, 22)}
    db.add(Dass21Response(
        registration_id=reg.id, scoring_version="v1",
        skor_depresi=2, skor_kecemasan=4, skor_stres=6, **data,
    ))
    db.add(Followup(registration_id=reg.id, status="menunggu_ditinjau"))
    conv = Conversation(registration_id=reg.id)
    db.add(conv)
    db.flush()
    db.add(Message(conversation_id=conv.id, sender="mahasiswa", message_text="tes"))
    db.commit()

    reg_id = reg.id
    db.delete(reg)
    db.commit()

    assert db.get(Registration, reg_id) is None
    assert db.query(Dass21Response).filter_by(registration_id=reg_id).count() == 0
    assert db.query(Followup).filter_by(registration_id=reg_id).count() == 0
    assert db.query(Conversation).filter_by(registration_id=reg_id).count() == 0
    assert db.query(Message).filter(Message.conversation_id == conv.id).count() == 0


def test_indeks_penting_tersedia(client, db):
    insp = inspect(db.bind)
    idx_reg = {i["name"] for i in insp.get_indexes("registrations")}
    assert "ix_registrations_nim" in idx_reg
    assert "ix_registrations_created_at" in idx_reg
    idx_dass = {i["name"] for i in insp.get_indexes("dass21_responses")}
    assert "ix_dass21_responses_registration_id" in idx_dass
    idx_msg = {i["name"] for i in insp.get_indexes("messages")}
    assert "ix_messages_conversation_id" in idx_msg
    # unique index username
    idx_user = {i["name"] for i in insp.get_indexes("users")}
    assert "ix_users_username" in idx_user


def test_timestamp_otomatis_dan_updated_at_followup(client, db):
    reg = _buat_registration(db)
    followup = Followup(registration_id=reg.id, status="menunggu_ditinjau")
    db.add(followup)
    db.commit()
    assert reg.created_at is not None
    assert followup.created_at is not None

    lama = followup.updated_at
    followup.status = "dijadwalkan"
    db.commit()
    db.refresh(followup)
    assert followup.updated_at >= lama


def test_jumlah_pesan_per_percakapan_query_agregat(client, db):
    reg = _buat_registration(db)
    conv = Conversation(registration_id=reg.id)
    db.add(conv)
    db.flush()
    for i in range(4):
        db.add(Message(conversation_id=conv.id, sender="mahasiswa" if i % 2 == 0 else "bot",
                       message_text=f"pesan {i}"))
    db.commit()

    total = (
        db.execute(
            select(func.count(Message.id))
            .select_from(Message)
            .where(Message.conversation_id == conv.id)
        ).scalar()
    )
    assert total == 4
