"""Pengujian API skrining DASS-21: penyimpanan skor + kebijakan tanpa skor ke mahasiswa."""
import json

from app.models import Dass21Response
from app.services.dass21_scoring import SUBSCALE_ITEMS

from .conftest import full_answers, register_student


def test_submit_sukses_skor_tersimpan_tapi_tidak_dikirim_ke_mahasiswa(client, db):
    reg = register_student(client)
    res = client.post("/api/dass21/submit", json={
        "registration_id": reg["registration_id"],
        "chat_token": reg["chat_token"],
        "jawaban": full_answers(),
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "tersimpan"

    # KRITIS: respons mahasiswa tidak boleh memuat skor/kategori/subskala.
    text = json.dumps(body).lower()
    for forbidden in ("skor", "depresi", "kecemasan", "stres", "kategori", "normal", "berat"):
        assert forbidden not in text, f"Respons mahasiswa membocorkan: {forbidden}"

    # Skor tersimpan di database sesuai algoritma.
    dass = db.query(Dass21Response).filter_by(registration_id=reg["registration_id"]).one()
    expected = {
        k: sum(int(full_answers()[str(i)]) for i in items) * 2
        for k, items in SUBSCALE_ITEMS.items()
    }
    assert dass.skor_depresi == expected["depresi"]
    assert dass.skor_kecemasan == expected["kecemasan"]
    assert dass.skor_stres == expected["stres"]
    assert dass.scoring_version
    assert dass.submitted_at is not None
    # 21 jawaban tersimpan per kolom
    for i in range(1, 22):
        assert getattr(dass, f"jawaban_{i}") == int(full_answers()[str(i)])


def test_submit_dengan_token_salah_ditolak(client, sample_registration):
    res = client.post("/api/dass21/submit", json={
        "registration_id": sample_registration["registration_id"],
        "chat_token": "token-palsu-tidak-valid",
        "jawaban": full_answers(),
    })
    assert res.status_code == 403


def test_submit_pendaftaran_tak_dikenal_404(client):
    res = client.post("/api/dass21/submit", json={
        "registration_id": 99999,
        "chat_token": "x" * 32,
        "jawaban": full_answers(),
    })
    assert res.status_code == 404


def test_submit_jawaban_kurang_ditolak(client, db):
    reg = register_student(client)
    jawaban = full_answers()
    del jawaban["14"]
    res = client.post("/api/dass21/submit", json={
        "registration_id": reg["registration_id"],
        "chat_token": reg["chat_token"],
        "jawaban": jawaban,
    })
    assert res.status_code == 422
    assert "14" in res.json()["detail"]


def test_submit_nilai_di_luar_rentang_ditolak(client, db):
    reg = register_student(client)
    jawaban = full_answers()
    jawaban["3"] = 5
    res = client.post("/api/dass21/submit", json={
        "registration_id": reg["registration_id"],
        "chat_token": reg["chat_token"],
        "jawaban": jawaban,
    })
    assert res.status_code == 422


def test_submit_ganda_ditolak_409(client, sample_registration):
    res = client.post("/api/dass21/submit", json={
        "registration_id": sample_registration["registration_id"],
        "chat_token": sample_registration["chat_token"],
        "jawaban": full_answers(),
    })
    assert res.status_code == 409


def test_endpoint_pertanyaan_mengembalikan_21_item(client):
    res = client.get("/api/dass21/questions")
    assert res.status_code == 200
    data = res.json()
    assert len(data["pertanyaan"]) == 21
    assert [o["nilai"] for o in data["opsi"]] == [0, 1, 2, 3]
    assert data["pengantar"]
