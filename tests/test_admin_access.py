"""Pengujian akses admin: statistik, daftar+filter+prioritas, detail, tindak lanjut, ekspor."""
from app.models import Dass21Response, Followup

from .conftest import full_answers, register_student, submit_dass


def _buat_tiga_pendaftar(client, admin_headers):
    """A: biasa (menunggu), B: eskalasi krisis via obrolan, C: diselesaikan."""
    a = register_student(client, nama="Ani Biasa", nim="2111100001")
    b = register_student(client, nama="Bima Krisis", nim="2111100002")
    c = register_student(client, nama="Cici Selesai", nim="2111100003")
    submit_dass(client, a)
    submit_dass(client, b)
    submit_dass(client, c)

    # B menuliskan pesan krisis -> otomatis perlu_ditinjau_segera
    start = client.post("/api/chat/start", json={
        "registration_id": b["registration_id"], "chat_token": b["chat_token"]})
    conv_id = start.json()["conversation_id"]
    res = client.post("/api/chat/message", json={
        "registration_id": b["registration_id"], "chat_token": b["chat_token"],
        "conversation_id": conv_id, "text": "Saya ingin mengakhiri hidup saja.",
    })
    assert res.json()["eskalasi"] is True

    # C diselesaikan oleh admin
    client.patch(f"/api/admin/registrations/{c['registration_id']}/followup",
                 json={"status": "selesai", "catatan_petugas": "Selesai"},
                 headers=admin_headers)
    return a, b, c


def test_stats_bentuk_dan_isi(client, db, admin_headers):
    reg = register_student(client)
    submit_dass(client, reg)
    res = client.get("/api/admin/stats", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_registrasi"] == 1
    assert data["total_skrining_dass21"] == 1
    assert data["per_status"]["menunggu_ditinjau"] == 1
    assert set(data["per_status"]) == {
        "menunggu_ditinjau", "sedang_diproses", "dijadwalkan", "selesai", "perlu_ditinjau_segera",
    }


def test_urutan_prioritas_eskalasi_di_atas(client, db, admin_headers):
    a, b, c = _buat_tiga_pendaftar(client, admin_headers)
    res = client.get("/api/admin/registrations?sort=priority", headers=admin_headers)
    urutan = [item["id"] for item in res.json()["items"]]
    assert urutan == [b["registration_id"], a["registration_id"], c["registration_id"]]


def test_filter_status_dan_pencarian(client, db, admin_headers):
    a, b, c = _buat_tiga_pendaftar(client, admin_headers)

    res = client.get("/api/admin/registrations?status=perlu_ditinjau_segera", headers=admin_headers)
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["nim"] == "2111100002"

    res = client.get("/api/admin/registrations?search=Ani", headers=admin_headers)
    items = res.json()["items"]
    assert len(items) == 1 and items[0]["nama"] == "Ani Biasa"

    res = client.get("/api/admin/registrations?search=2111100003", headers=admin_headers)
    assert len(res.json()["items"]) == 1

    res = client.get("/api/admin/registrations?jenis_layanan=Konsultasi Karier", headers=admin_headers)
    assert res.json()["total"] == 0


def test_detail_memuat_semua_data_sensitif(client, db, admin_headers):
    reg = register_student(client)
    submit_dass(client, reg)
    res = client.get(f"/api/admin/registrations/{reg['registration_id']}", headers=admin_headers)
    assert res.status_code == 200
    d = res.json()
    assert d["keluhan"]  # keluhan terlihat admin
    assert d["dass21"]["skor"]["depresi"] is not None
    assert len(d["dass21"]["jawaban"]) == 21
    assert "kategori_umum" in d["dass21"]
    assert "Bukan kategori resmi UPA BK" in d["dass21"]["catatan_kategori"]
    assert d["followup"]["status"] == "menunggu_ditinjau"


def test_detail_tak_ditemukan_404(client, db, admin_headers):
    res = client.get("/api/admin/registrations/99999", headers=admin_headers)
    assert res.status_code == 404


def test_update_tindak_lanjut_mencatat_admin(client, db, admin_headers):
    reg = register_student(client)
    res = client.patch(
        f"/api/admin/registrations/{reg['registration_id']}/followup",
        json={"status": "dijadwalkan", "catatan_petugas": "Sesi 1 dijadwalkan Senin pagi."},
        headers=admin_headers,
    )
    assert res.status_code == 200
    followup = db.query(Followup).filter_by(registration_id=reg["registration_id"]).one()
    assert followup.status == "dijadwalkan"
    assert followup.assigned_admin_id is not None
    assert followup.catatan_petugas == "Sesi 1 dijadwalkan Senin pagi."


def test_update_status_tak_kenal_422(client, db, admin_headers):
    reg = register_student(client)
    res = client.patch(f"/api/admin/registrations/{reg['registration_id']}/followup",
                       json={"status": "statusaneh"}, headers=admin_headers)
    assert res.status_code == 422


def test_token_mahasiswa_tidak_bisa_akses_admin(client, db, admin_headers):
    reg = register_student(client)
    # token obrolan mahasiswa dipakai sebagai bearer -> harus ditolak
    res = client.get("/api/admin/stats",
                     headers={"Authorization": f"Bearer {reg['chat_token']}"})
    assert res.status_code == 401


def test_ekspor_csv_standar_tanpa_kolom_sensitif(client, db, admin_headers):
    reg = register_student(client)
    submit_dass(client, reg)
    res = client.get("/api/admin/export/registrations.csv", headers=admin_headers)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    csv_text = res.text
    assert "nama" in csv_text and "nim" in csv_text
    assert "keluhan" not in csv_text.lower() or "keluhan" not in csv_text.splitlines()[0]
    first_line = csv_text.splitlines()[0]
    assert "skor_depresi" not in first_line


def test_ekspor_csv_sensitif_memuat_keluhan_dan_skor(client, db, admin_headers):
    reg = register_student(client, keluhan="Cemas berat menjelang sidang.")
    submit_dass(client, reg)
    res = client.get("/api/admin/export/registrations.csv?include_sensitive=true", headers=admin_headers)
    assert res.status_code == 200
    lines = res.text.splitlines()
    header = lines[0]
    assert "keluhan" in header and "skor_depresi" in header
    assert "Cemas berat menjelang sidang." in res.text


def test_daftar_memuat_ringkasan_skor_untuk_admin(client, db, admin_headers):
    reg = register_student(client)
    submit_dass(client, reg)
    items = client.get("/api/admin/registrations", headers=admin_headers).json()["items"]
    assert items[0]["sudah_skrining"] is True
    assert items[0]["skor_depresi"] is not None
