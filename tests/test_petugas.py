"""Uji fitur pengelolaan petugas penangani & penugasan penanggung jawab."""
import pytest

from .conftest import register_student


def _create_petugas(client, admin_headers, nama="Dra. Ratna Wulandari, M.Psi", peran="Psikolog Klinis"):
    res = client.post(
        "/api/admin/petugas",
        json={"nama": nama, "peran": peran, "kontak": "ratna@contoh.ac.id"},
        headers=admin_headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


# ------------------------------------------------------------------- akses
def test_petugas_endpoints_require_admin(client):
    res = client.get("/api/admin/petugas")
    assert res.status_code == 401
    res = client.post("/api/admin/petugas", json={"nama": "Si A", "peran": "Konselor"})
    assert res.status_code == 401


# ------------------------------------------------------------------- CRUD petugas
def test_create_and_list_petugas(client, admin_headers):
    created = _create_petugas(client, admin_headers)
    assert created["aktif"] is True
    assert created["jumlah_kasus"] == 0

    res = client.get("/api/admin/petugas", headers=admin_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["nama"] == "Dra. Ratna Wulandari, M.Psi"
    assert items[0]["peran"] == "Psikolog Klinis"


def test_create_petugas_validation(client, admin_headers):
    res = client.post("/api/admin/petugas", json={"nama": "A", "peran": "Konselor"}, headers=admin_headers)
    assert res.status_code == 422  # nama terlalu pendek


def test_update_petugas_rename_and_deactivate(client, admin_headers):
    p = _create_petugas(client, admin_headers)

    res = client.patch(f"/api/admin/petugas/{p['id']}", json={"nama": "Ratna W.", "aktif": False}, headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["nama"] == "Ratna W."
    assert body["aktif"] is False

    res = client.patch("/api/admin/petugas/999", json={"aktif": True}, headers=admin_headers)
    assert res.status_code == 404


def test_delete_petugas_releases_assignment(client, admin_headers, db):
    from app.models import Followup

    p = _create_petugas(client, admin_headers)
    reg = register_student(client)
    reg_id = reg["registration_id"]

    res = client.put(f"/api/admin/registrations/{reg_id}/assign", json={"petugas_id": p["id"]}, headers=admin_headers)
    assert res.status_code == 200

    res = client.delete(f"/api/admin/petugas/{p['id']}", headers=admin_headers)
    assert res.status_code == 200

    # kasus tetap ada, penugasannya lepas
    fu = db.query(Followup).filter(Followup.registration_id == reg_id).first()
    assert fu is not None
    assert fu.petugas_id is None

    res = client.delete(f"/api/admin/petugas/{p['id']}", headers=admin_headers)
    assert res.status_code == 404


# ------------------------------------------------------------------- penugasan
def test_assign_and_unassign_petugas(client, admin_headers, db):
    from app.models import Followup

    p = _create_petugas(client, admin_headers)
    reg = register_student(client)
    reg_id = reg["registration_id"]

    res = client.put(f"/api/admin/registrations/{reg_id}/assign", json={"petugas_id": p["id"]}, headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["petugas"]["nama"] == p["nama"]

    # tersimpan di DB dan tampil di detail
    fu = db.query(Followup).filter(Followup.registration_id == reg_id).first()
    assert fu.petugas_id == p["id"]
    detail = client.get(f"/api/admin/registrations/{reg_id}", headers=admin_headers).json()
    assert detail["followup"]["petugas"]["id"] == p["id"]

    # daftar pendaftar juga menampilkan petugas
    items = client.get("/api/admin/registrations", headers=admin_headers).json()["items"]
    target = next(i for i in items if i["id"] == reg_id)
    assert target["petugas"]["nama"] == p["nama"]

    # lepas penugasan
    res = client.put(f"/api/admin/registrations/{reg_id}/assign", json={"petugas_id": None}, headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["petugas"] is None
    detail = client.get(f"/api/admin/registrations/{reg_id}", headers=admin_headers).json()
    assert detail["followup"]["petugas"] is None


def test_assign_unknown_petugas_and_registration(client, admin_headers):
    reg = register_student(client)
    reg_id = reg["registration_id"]

    res = client.put(f"/api/admin/registrations/{reg_id}/assign", json={"petugas_id": 999}, headers=admin_headers)
    assert res.status_code == 404

    res = client.put("/api/admin/registrations/999/assign", json={"petugas_id": None}, headers=admin_headers)
    assert res.status_code == 404


def test_list_filter_by_assignment(client, admin_headers):
    p = _create_petugas(client, admin_headers)
    reg_a = register_student(client, nama="Siswa A", nim="2101100001")
    reg_b = register_student(client, nama="Siswa B", nim="2101100002")

    client.put(
        f"/api/admin/registrations/{reg_a['registration_id']}/assign",
        json={"petugas_id": p["id"]}, headers=admin_headers,
    )

    ya = client.get("/api/admin/registrations?assigned=ya", headers=admin_headers).json()["items"]
    assert [i["id"] for i in ya] == [reg_a["registration_id"]]

    tidak = client.get("/api/admin/registrations?assigned=tidak", headers=admin_headers).json()["items"]
    assert reg_b["registration_id"] in [i["id"] for i in tidak]
    assert reg_a["registration_id"] not in [i["id"] for i in tidak]

    per_petugas = client.get(
        f"/api/admin/registrations?assigned=ya&petugas_id={p['id']}", headers=admin_headers
    ).json()["items"]
    assert [i["id"] for i in per_petugas] == [reg_a["registration_id"]]


# ------------------------------------------------------------------- statistik & ekspor
def test_stats_per_petugas(client, admin_headers):
    p = _create_petugas(client, admin_headers)
    reg = register_student(client)
    client.put(
        f"/api/admin/registrations/{reg['registration_id']}/assign",
        json={"petugas_id": p["id"]}, headers=admin_headers,
    )

    stats = client.get("/api/admin/stats", headers=admin_headers).json()
    assert stats["per_petugas"].get(p["nama"]) == 1


def test_csv_export_contains_petugas_column(client, admin_headers):
    p = _create_petugas(client, admin_headers)
    reg = register_student(client)
    client.put(
        f"/api/admin/registrations/{reg['registration_id']}/assign",
        json={"petugas_id": p["id"]}, headers=admin_headers,
    )

    res = client.get("/api/admin/export/registrations.csv", headers=admin_headers)
    assert res.status_code == 200
    text = res.text
    assert "petugas_penangani" in text.splitlines()[0]
    assert p["nama"] in text
