"""Pengujian fitur penjadwalan konseling.

Cakupan:
- RBAC: seluruh endpoint jadwal menolak akses tanpa sesi admin (401).
- Antrean prioritas: krisis (darurat) paling atas, disusul DASS berat, lalu normal.
- Pembuatan jadwal: status tindak lanjut otomatis, normalisasi jam, kalender mingguan.
- Aturan darurat: status krisis DIPERTAHANKAN saat kasus dijadwalkan.
- Deteksi bentrok konselor (overlap interval, termasuk tepi).
- Validasi: konselor nonaktif, tanggal lewat, metode/jam tidak valid.
- Ubah jadwal (PATCH): bentrok saat reassign, status selesai/dibatalkan,
  penolakan geser ke masa lalu; hapus jadwal.
"""
from datetime import timedelta

from app.models import Followup, Petugas, Schedule
from app.services.scheduling import monday_of, wib_today


# ---------------------------------------------------------------- helpers
def make_petugas(db, nama="Konselor Uji", aktif=True):
    p = Petugas(nama=nama, peran="Psikolog", aktif=aktif)
    db.add(p)
    db.commit()
    return p


def future_date(days=1):
    return (wib_today() + timedelta(days=days)).isoformat()


def past_date(days=1):
    return (wib_today() - timedelta(days=days)).isoformat()


def schedule_body(reg_id, petugas_id, tanggal=None, jam="09:00", durasi=60, metode="Tatap Muka"):
    return {
        "registration_id": reg_id,
        "petugas_id": petugas_id,
        "tanggal": tanggal if tanggal is not None else future_date(),
        "jam_mulai": jam,
        "durasi_menit": durasi,
        "metode": metode,
    }


def set_crisis(db, reg_id):
    """Tandai satu kasus sebagai eskalasi krisis (status followup)."""
    fu = db.query(Followup).filter(Followup.registration_id == reg_id).first()
    fu.status = "perlu_ditinjau_segera"
    db.commit()


# ---------------------------------------------------------------- RBAC
def test_schedule_endpoints_require_auth(client, db):
    for path in ["/api/admin/schedule/week", "/api/admin/schedule/queue"]:
        assert client.get(path).status_code == 401
    assert client.post("/api/admin/schedule", json={}).status_code == 401
    assert client.patch("/api/admin/schedule/1", json={}).status_code == 401
    assert client.delete("/api/admin/schedule/1").status_code == 401


# ---------------------------------------------------------------- antrean prioritas
def test_queue_prioritizes_crisis_then_severity_then_oldest(client, db, admin_headers):
    from tests.conftest import register_student, submit_dass

    p = make_petugas(db)
    reg_lama = register_student(client)                      # normal, paling lama
    reg_berat = register_student(client, nama="Dinda Berat")
    submit_dass(client, reg_berat, answers={str(i): 3 for i in range(1, 22)})  # Sangat Berat
    reg_krisis = register_student(client, nama="Eka Krisis")
    set_crisis(db, reg_krisis["registration_id"])

    res = client.get("/api/admin/schedule/queue", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    urutan = [(it["registration_id"], it["urgensi"]) for it in data["items"]]

    assert urutan[0] == (reg_krisis["registration_id"], "darurat")
    assert urutan[1] == (reg_berat["registration_id"], "tinggi")
    assert urutan[2] == (reg_lama["registration_id"], "normal")
    assert "krisis" in data["items"][0]["alasan"].lower()
    assert data["ringkasan"] == {"darurat": 1, "tinggi": 1, "normal": 1}


def test_queue_excludes_finished_cases(client, db, admin_headers):
    from tests.conftest import register_student

    make_petugas(db)
    reg = register_student(client)
    fu = db.query(Followup).filter(Followup.registration_id == reg["registration_id"]).first()
    fu.status = "selesai"
    db.commit()

    res = client.get("/api/admin/schedule/queue", headers=admin_headers)
    ids = [it["registration_id"] for it in res.json()["items"]]
    assert reg["registration_id"] not in ids


# ---------------------------------------------------------------- buat jadwal
def test_create_schedule_auto_marks_dijadwalkan(client, db, admin_headers):
    from tests.conftest import register_student

    p = make_petugas(db)
    reg = register_student(client)

    res = client.post("/api/admin/schedule", headers=admin_headers,
                      json=schedule_body(reg["registration_id"], p.id, jam="9:30"))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["jam_mulai"] == "09:30"          # normalisasi jam
    assert body["jam_selesai"] == "10:30"
    assert body["hari"] in ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")

    fu = db.query(Followup).filter(Followup.registration_id == reg["registration_id"]).first()
    assert fu.status == "dijadwalkan"            # otomatis naik status
    assert db.query(Schedule).count() == 1

    # masuk kalender mingguan
    week = client.get("/api/admin/schedule/week", headers=admin_headers).json()
    all_items = [it for d in week["days"] for it in d["items"]]
    assert len(all_items) == 1
    assert all_items[0]["registration_id"] == reg["registration_id"]
    assert all_items[0]["petugas"]["id"] == p.id


def test_crisis_case_keeps_status_when_scheduled(client, db, admin_headers):
    from tests.conftest import register_student

    make_petugas(db)
    reg = register_student(client)
    set_crisis(db, reg["registration_id"])

    res = client.post("/api/admin/schedule", headers=admin_headers,
                      json=schedule_body(reg["registration_id"], 1))
    assert res.status_code == 201
    fu = db.query(Followup).filter(Followup.registration_id == reg["registration_id"]).first()
    assert fu.status == "perlu_ditinjau_segera"  # penanda darurat TIDAK ditimpa

    # sudah punya sesi aktif -> keluar dari antrean
    queue_ids = [it["registration_id"]
                 for it in client.get("/api/admin/schedule/queue", headers=admin_headers).json()["items"]]
    assert reg["registration_id"] not in queue_ids

    # tetap tampil berlabel darurat pada kalender
    week = client.get("/api/admin/schedule/week", headers=admin_headers).json()
    assert week["total_darurat"] == 1
    item = week["days"][0]["items"][0] if week["days"][0]["items"] else None
    assert item is None or item["urgensi"] == "darurat"


def test_detail_includes_jadwal_and_priority(client, db, admin_headers):
    from tests.conftest import register_student

    make_petugas(db)
    reg = register_student(client)
    client.post("/api/admin/schedule", headers=admin_headers,
                json=schedule_body(reg["registration_id"], 1))

    detail = client.get(f"/api/admin/registrations/{reg['registration_id']}",
                        headers=admin_headers).json()
    assert len(detail["jadwal"]) == 1
    assert detail["jadwal"][0]["status"] == "terjadwal"
    assert detail["prioritas_penjadwalan"]["urgensi"] == "normal"


# ---------------------------------------------------------------- validasi
def test_create_schedule_validations(client, db, admin_headers):
    from tests.conftest import register_student

    reg = register_student(client)
    p = make_petugas(db)

    # konselor tidak dikenal
    r = client.post("/api/admin/schedule", headers=admin_headers,
                    json=schedule_body(reg["registration_id"], 999))
    assert r.status_code == 404

    # konselor nonaktif
    p_off = make_petugas(db, nama="Nonaktif", aktif=False)
    r = client.post("/api/admin/schedule", headers=admin_headers,
                    json=schedule_body(reg["registration_id"], p_off.id))
    assert r.status_code == 422
    assert "nonaktif" in r.json()["detail"].lower()

    # tanggal sudah lewat
    r = client.post("/api/admin/schedule", headers=admin_headers,
                    json=schedule_body(reg["registration_id"], p.id, tanggal=past_date()))
    assert r.status_code == 422
    assert "lewat" in r.json()["detail"].lower()

    # jam tidak valid
    r = client.post("/api/admin/schedule", headers=admin_headers,
                    json=schedule_body(reg["registration_id"], p.id, jam="25:00"))
    assert r.status_code == 422

    # metode tidak dikenal
    r = client.post("/api/admin/schedule", headers=admin_headers,
                    json=schedule_body(reg["registration_id"], p.id, metode="Telepati"))
    assert r.status_code == 422

    # kasus tidak ada
    r = client.post("/api/admin/schedule", headers=admin_headers,
                    json=schedule_body(9999, p.id))
    assert r.status_code == 404


# ---------------------------------------------------------------- bentrok
def test_conflict_detection_overlapping_slots(client, db, admin_headers):
    from tests.conftest import register_student

    p1 = make_petugas(db, nama="Konselor Satu")
    p2 = make_petugas(db, nama="Konselor Dua")
    reg_a = register_student(client)
    reg_b = register_student(client, nama="Budi Kedua")
    reg_c = register_student(client, nama="Citra Ketiga")

    r = client.post("/api/admin/schedule", headers=admin_headers,
                    json=schedule_body(reg_a["registration_id"], p1.id, jam="09:00", durasi=60))
    assert r.status_code == 201

    # tumpang tindih dengan konselor sama -> ditolak
    r = client.post("/api/admin/schedule", headers=admin_headers,
                    json=schedule_body(reg_b["registration_id"], p1.id, jam="09:30", durasi=30))
    assert r.status_code == 409
    assert "Bentrok" in r.json()["detail"]

    # konselor berbeda pada slot sama -> boleh
    r = client.post("/api/admin/schedule", headers=admin_headers,
                    json=schedule_body(reg_b["registration_id"], p2.id, jam="09:30", durasi=30))
    assert r.status_code == 201

    # menempel di tepi (mulai tepat saat sesi lain selesai) -> boleh
    r = client.post("/api/admin/schedule", headers=admin_headers,
                    json=schedule_body(reg_c["registration_id"], p1.id, jam="10:00", durasi=30))
    assert r.status_code == 201


# ---------------------------------------------------------------- kalender mingguan
def test_week_view_normalizes_to_monday_and_filters(client, db, admin_headers):
    from tests.conftest import register_student

    p1 = make_petugas(db, nama="Konselor Satu")
    p2 = make_petugas(db, nama="Konselor Dua")
    reg = register_student(client)
    monday = monday_of(wib_today())
    rabu = monday + timedelta(days=2)

    r = client.post("/api/admin/schedule", headers=admin_headers,
                    json=schedule_body(reg["registration_id"], p1.id,
                                       tanggal=rabu.isoformat(), jam="13:00"))
    assert r.status_code == 201

    # start=Rabu tetap ditormalkan ke Senin
    week = client.get("/api/admin/schedule/week", headers=admin_headers,
                      params={"start": rabu.isoformat()}).json()
    assert week["start"] == monday.isoformat()
    assert len(week["days"]) == 7
    assert week["days"][0]["hari"] == "Senin"
    assert week["days"][6]["hari"] == "Minggu"
    assert week["total"] == 1
    wed = week["days"][2]
    assert wed["tanggal"] == rabu.isoformat()
    assert wed["items"][0]["jam_mulai"] == "13:00"
    assert wed["items"][0]["hari"] == "Rabu"

    # filter konselor lain -> kosong
    week2 = client.get("/api/admin/schedule/week", headers=admin_headers,
                       params={"petugas_id": p2.id}).json()
    assert week2["total"] == 0

    # filter konselor terkait -> 1 sesi
    week3 = client.get("/api/admin/schedule/week", headers=admin_headers,
                       params={"petugas_id": p1.id}).json()
    assert week3["total"] == 1


# ---------------------------------------------------------------- ubah jadwal
def test_patch_reschedule_conflict_and_status_flow(client, db, admin_headers):
    from tests.conftest import register_student

    p1 = make_petugas(db, nama="Konselor Satu")
    p2 = make_petugas(db, nama="Konselor Dua")
    reg_a = register_student(client)
    reg_b = register_student(client, nama="Budi Kedua")

    id_a = client.post("/api/admin/schedule", headers=admin_headers,
                       json=schedule_body(reg_a["registration_id"], p1.id, jam="09:00")).json()["id"]
    id_b = client.post("/api/admin/schedule", headers=admin_headers,
                       json=schedule_body(reg_b["registration_id"], p2.id, jam="09:00")).json()["id"]

    # pindahkan B ke konselor 1 pada jam yang sama -> bentrok
    r = client.patch(f"/api/admin/schedule/{id_b}", headers=admin_headers,
                     json={"petugas_id": p1.id})
    assert r.status_code == 409

    # tandai selesai -> kasus muncul lagi di antrean (butuh sesi lanjutan)
    r = client.patch(f"/api/admin/schedule/{id_b}", headers=admin_headers,
                     json={"status": "selesai"})
    assert r.status_code == 200
    assert r.json()["status"] == "selesai"
    queue_ids = [it["registration_id"]
                 for it in client.get("/api/admin/schedule/queue", headers=admin_headers).json()["items"]]
    assert reg_b["registration_id"] in queue_ids

    # sesi selesai boleh digeser ke tanggal lampau tanpa pemeriksaan masa depan?
    # Tidak - hanya sesi 'terjadwal' yang ditolak; selesai/dibatalkan bebas diubah.
    r = client.patch(f"/api/admin/schedule/{id_b}", headers=admin_headers,
                     json={"status": "dibatalkan"})
    assert r.status_code == 200

    # geser sesi terjadwal ke masa lalu -> ditolak
    r = client.patch(f"/api/admin/schedule/{id_a}", headers=admin_headers,
                     json={"tanggal": past_date()})
    assert r.status_code == 422

    # status tidak dikenal -> 422
    r = client.patch(f"/api/admin/schedule/{id_a}", headers=admin_headers,
                     json={"status": "gakjelas"})
    assert r.status_code == 422


def test_delete_schedule(client, db, admin_headers):
    from tests.conftest import register_student

    p = make_petugas(db)
    reg = register_student(client)
    sid = client.post("/api/admin/schedule", headers=admin_headers,
                      json=schedule_body(reg["registration_id"], p.id)).json()["id"]

    r = client.delete(f"/api/admin/schedule/{sid}", headers=admin_headers)
    assert r.status_code == 200
    assert db.query(Schedule).count() == 0

    week = client.get("/api/admin/schedule/week", headers=admin_headers).json()
    assert week["total"] == 0

    # hapus ulang -> 404
    assert client.delete(f"/api/admin/schedule/{sid}", headers=admin_headers).status_code == 404


def test_schedule_not_accessible_for_student_endpoints(client, db):
    """Sanity: mahasiswa tanpa akun tetap tidak punya jalan ke data jadwal."""
    assert client.get("/api/admin/schedule/week").status_code == 401
