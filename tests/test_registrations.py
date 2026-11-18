"""Pengujian endpoint pendaftaran + penyimpanan database."""
from app.models import Registration


def test_pendaftaran_sukses_tersimpan_di_database(client, db):
    res = client.post("/api/registrations", json={**_valid(), "keluhan": None})
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["registration_id"] > 0
    assert len(data["chat_token"]) >= 16

    reg = db.get(Registration, data["registration_id"])
    assert reg is not None
    assert reg.nama == _valid()["nama"]
    assert reg.nim == _valid()["nim"]
    assert reg.consent_status == "disetujui"
    assert reg.followup is not None
    assert reg.followup.status == "menunggu_ditinjau"
    assert reg.created_at is not None


def _valid():
    return {
        "nama": "Siti Contoh",
        "nim": "2101101888",
        "kontak": "081299900001",
        "jenis_layanan": "Konseling Individu",
        "preferensi_hari": "Selasa",
        "preferensi_waktu": "Siang (11.00-14.00)",
        "keluhan": "Sering panik menghadapi ujian.",
        "setuju_penggunaan_data": True,
    }


def test_pendaftaran_tanpa_persetujuan_ditolak(client, db):
    payload = _valid()
    payload["setuju_penggunaan_data"] = False
    res = client.post("/api/registrations", json=payload)
    assert res.status_code == 422
    assert db.query(Registration).count() == 0


def test_pendaftaran_field_wajib_hilang_ditolak(client):
    for field in ("nama", "nim", "kontak", "jenis_layanan"):
        payload = _valid()
        del payload[field]
        res = client.post("/api/registrations", json=payload)
        assert res.status_code == 422, f"Field {field} seharusnya wajib."


def test_pendaftaran_jenis_layanan_tidak_dikenal_ditolak(client):
    payload = _valid()
    payload["jenis_layanan"] = "LayananImajiner"
    assert client.post("/api/registrations", json=payload).status_code == 422


def test_pendaftaran_preferensi_tidak_dikenal_ditolak(client):
    payload = _valid()
    payload["preferensi_hari"] = "HariBebos"
    assert client.post("/api/registrations", json=payload).status_code == 422


def test_endpoint_opsi_menyediakan_pilihan(client):
    res = client.get("/api/registrations/options")
    assert res.status_code == 200
    data = res.json()
    assert "Konseling Individu" in data["jenis_layanan"]
    assert "Senin" in data["hari"]
    assert any("Pagi" in w for w in data["waktu"])
