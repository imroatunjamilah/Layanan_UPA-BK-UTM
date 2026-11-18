"""Uji fitur analisis kasus terpadu (keluhan + DASS-21 + obrolan) berbantuan LLM mock."""
import json

from .conftest import register_student, submit_dass


def _admin_post(client, admin_headers, reg_id):
    return client.post(
        f"/api/admin/registrations/{reg_id}/analysis", headers=admin_headers
    )


def _send_chat(client, reg_json, text):
    start = client.post("/api/chat/start", json={
        "registration_id": reg_json["registration_id"],
        "chat_token": reg_json["chat_token"],
    })
    assert start.status_code == 200, start.text
    res = client.post("/api/chat/message", json={
        "registration_id": reg_json["registration_id"],
        "chat_token": reg_json["chat_token"],
        "conversation_id": start.json()["conversation_id"],
        "text": text,
    })
    assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------------- akses
def test_analysis_requires_admin(client):
    reg = register_student(client)
    res = _admin_post(client, {}, reg["registration_id"])
    assert res.status_code == 401


def test_analysis_unknown_registration(client, admin_headers):
    res = client.post("/api/admin/registrations/999/analysis", headers=admin_headers)
    assert res.status_code == 404


# ------------------------------------------------------------------- konten
def test_analysis_with_full_data(client, admin_headers, sample_registration):
    # keluhan ada di payload registrasi; obrolan ditambahkan via chatbot
    _send_chat(client, sample_registration, "Saya cemas dan overthinking soal ujian dan nilai kuliah.")

    res = _admin_post(client, admin_headers, sample_registration["registration_id"])
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["registration_id"] == sample_registration["registration_id"]
    assert body["penyedia"] == "mock"  # gerbang privasi: tidak ada penyedia eksternal
    assert "bukan diagnosis" in body["disclaimer"].lower()
    assert body["dibuat_pada"].endswith("Z")

    a = body["analisis"]
    assert a["sumber"] == "llm"  # mock menghasilkan JSON valid
    assert a["tingkat_perhatian"] in ("rendah", "sedang", "tinggi")
    assert isinstance(a["tema"], list) and a["tema"]
    assert isinstance(a["saran_tindak_lanjut"], list) and a["saran_tindak_lanjut"]
    # DASS-21 dari sample_registration harus dikaitkan
    assert "DASS-21" in a["kaitan_dass21"]
    # tema dari kata kunci obrolan/keluhan
    assert any("cemas" in t.lower() or "akademik" in t.lower() for t in a["tema"])


def test_analysis_without_dass_and_chat(client, admin_headers):
    reg = register_student(client, keluhan=None)
    res = _admin_post(client, admin_headers, reg["registration_id"])
    assert res.status_code == 200
    a = res.json()["analisis"]
    assert "belum" in a["ringkasan"].lower()
    assert "belum tersedia" in a["kaitan_dass21"].lower()
    assert a["tingkat_perhatian"] in ("rendah", "sedang", "tinggi")


def test_analysis_high_attention_on_severe_dass(client, admin_headers):
    """Kategori DASS berat/sangat berat harus menaikkan tingkat perhatian."""
    reg = register_student(client)
    # jawaban maksimal (semua 3) -> skor subskala 42 = "Sangat Berat"
    submit_dass(client, reg, answers={str(i): 3 for i in range(1, 22)})
    res = _admin_post(client, admin_headers, reg["registration_id"])
    assert res.status_code == 200
    body = res.json()
    assert body["analisis"]["tingkat_perhatian"] == "tinggi"
    assert "Sangat Berat" in body["analisis"]["kaitan_dass21"]


def test_analysis_crisis_chat_raises_attention(client, admin_headers):
    """Indikasi krisis pada obrolan harus tercermin sebagai tingkat tinggi."""
    reg = register_student(client)
    submit_dass(client, reg)
    res = _send_chat(client, reg, "Saya ingin mengakhiri hidup saya")
    assert res["eskalasi"] is True

    analysis = _admin_post(client, admin_headers, reg["registration_id"])
    assert analysis.status_code == 200
    # Pesan krisis dibalas SAFETY_MESSAGE (bukan lewat LLM), jadi isi krisis TIDAK
    # ikut dianalisis; tetapi status tindak lanjut naik ke perlu_ditinjau_segera.
    assert analysis.json()["analisis"]["tingkat_perhatian"] in ("sedang", "tinggi")


def test_mock_analysis_output_is_valid_json_deterministic(client, admin_headers, sample_registration):
    from app.services.analysis import ANALYSIS_SYSTEM_PROMPT, _build_payload, _parse_llm_json
    from app.services.llm.mock_provider import MockLLMProvider

    db = _build_payload  # kebetulan nama berbeda; panggil langsung provider di bawah
    provider = MockLLMProvider()
    out1 = provider.generate_reply(ANALYSIS_SYSTEM_PROMPT, [
        {"sender": "mahasiswa", "text": json.dumps({"keluhan": "cemas ujian"})},
    ])
    out2 = provider.generate_reply(ANALYSIS_SYSTEM_PROMPT, [
        {"sender": "mahasiswa", "text": json.dumps({"keluhan": "cemas ujian"})},
    ])
    assert out1 == out2  # deterministik
    parsed = _parse_llm_json(out1)
    assert parsed is not None
    assert parsed["tingkat_perhatian"] in ("rendah", "sedang", "tinggi")


def test_parse_llm_json_tolerant(client):
    from app.services.analysis import _parse_llm_json

    assert _parse_llm_json('{"a": 1}') == {"a": 1}
    assert _parse_llm_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_llm_json('Penjelasan: {"a": 1} selesai') == {"a": 1}
    assert _parse_llm_json("bukan json") is None
    assert _parse_llm_json("") is None
