"""Pengujian manajemen akun admin & reset kata sandi via OTP WhatsApp.

Mencakup:
- Pembuatan akun admin dengan profil wajib (nama, NIM, fakultas, no. WA).
- Blokir login akun nonaktif / masa aktif berakhir (termasuk sesi lama).
- Perlindungan diri: tidak bisa menonaktifkan/menghapus akun sendiri.
- Alur lupa sandi: kirim OTP (mock) -> verifikasi -> sandi baru.
- Keamanan OTP: kode salah, kedaluwarsa, jeda kirim ulang.
- Reset sandi langsung oleh admin lain.
"""
from datetime import date, timedelta

from app.utils import utcnow


def _payload_admin(username: str = "konselor01", **overrides) -> dict:
    payload = {
        "username": username,
        "password": "sandiAman123",
        "nama_lengkap": "Ratna Wulandari",
        "nim": "2101101999",
        "fakultas": "Fakultas Psikologi",
        "no_whatsapp": "08123456789",
    }
    payload.update(overrides)
    return payload


def _create(client, headers, username: str = "konselor01", **overrides):
    return client.post(
        "/api/admin/admins", json=_payload_admin(username, **overrides), headers=headers
    )


def _give_wa(db, username: str = "admin", wa: str = "6281234567890") -> None:
    from app.models import User

    u = db.query(User).filter(User.username == username).first()
    u.no_whatsapp = wa
    db.commit()


# ------------------------------------------------------- pembuatan akun admin
def test_create_admin_requires_profile(client, admin_headers):
    res = _create(client, admin_headers, nim="")  # NIM kosong -> ditolak validasi
    assert res.status_code == 422
    res = _create(client, admin_headers, fakultas="")  # fakultas kosong -> ditolak
    assert res.status_code == 422


def test_create_admin_invalid_whatsapp(client, admin_headers):
    res = _create(client, admin_headers, no_whatsapp="abc123")
    assert res.status_code == 422


def test_create_admin_success_and_login(client, admin_headers):
    res = _create(client, admin_headers)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["nama_lengkap"] == "Ratna Wulandari"
    assert data["nim"] == "2101101999"
    assert data["fakultas"] == "Fakultas Psikologi"
    assert data["no_whatsapp"] == "628123456789"  # dinormalisasi dari 08...
    assert data["status"] == "aktif"

    # Akun baru langsung bisa login dan identitasnya terbaca di /me.
    login = client.post(
        "/api/admin/login", json={"username": "konselor01", "password": "sandiAman123"}
    )
    assert login.status_code == 200, login.text
    token = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = client.get("/api/admin/me", headers=token)
    assert me.status_code == 200
    assert me.json()["nama_lengkap"] == "Ratna Wulandari"


def test_create_admin_duplicate_username(client, admin_headers):
    assert _create(client, admin_headers).status_code == 201
    res = _create(client, admin_headers)
    assert res.status_code == 400
    assert "sudah dipakai" in res.json()["detail"]


def test_list_admins_shows_status_and_masa_aktif(client, admin_headers):
    masa = (date.today() + timedelta(days=90)).isoformat()
    assert _create(client, admin_headers, masa_aktif_akhir=masa).status_code == 201
    res = client.get("/api/admin/admins", headers=admin_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    by_name = {u["username"]: u for u in items}
    assert "admin" in by_name and "konselor01" in by_name
    assert by_name["konselor01"]["status"] == "aktif"
    assert by_name["konselor01"]["masa_aktif_akhir"] == masa


# ------------------------------------------------------- blokir akses akun
def test_deactivated_admin_cannot_login_nor_use_old_session(client, admin_headers):
    login = client.post(
        "/api/admin/login", json={"username": "konselor01", "password": "sandiAman123"}
    )
    # akun belum ada -> buat dulu lalu login
    assert login.status_code == 401
    assert _create(client, admin_headers).status_code == 201
    login = client.post(
        "/api/admin/login", json={"username": "konselor01", "password": "sandiAman123"}
    )
    assert login.status_code == 200
    old_token = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Nonaktifkan oleh admin utama.
    user_id = client.get("/api/admin/admins", headers=admin_headers).json()["items"][-1]["id"]
    res = client.put(
        f"/api/admin/admins/{user_id}", json={"is_active": False}, headers=admin_headers
    )
    assert res.status_code == 200
    assert res.json()["status"] == "nonaktif"

    # Login ditolak...
    res = client.post(
        "/api/admin/login", json={"username": "konselor01", "password": "sandiAman123"}
    )
    assert res.status_code == 403
    assert "dinonaktifkan" in res.json()["detail"]
    # ...dan sesi lama pun hangus seketika.
    res = client.get("/api/admin/me", headers=old_token)
    assert res.status_code == 403


def test_cannot_deactivate_or_delete_self(client, admin_headers):
    me_id = client.get("/api/admin/admins", headers=admin_headers).json()["items"][0]["id"]
    res = client.put(
        f"/api/admin/admins/{me_id}", json={"is_active": False}, headers=admin_headers
    )
    assert res.status_code == 400
    assert "sendiri" in res.json()["detail"]
    res = client.delete(f"/api/admin/admins/{me_id}", headers=admin_headers)
    assert res.status_code == 400


def test_expired_admin_blocked_then_reenabled(client, admin_headers):
    kemarin = (date.today() - timedelta(days=1)).isoformat()
    res = _create(client, admin_headers, masa_aktif_akhir=kemarin)
    assert res.status_code == 201
    assert res.json()["status"] == "kedaluwarsa"

    login = client.post(
        "/api/admin/login", json={"username": "konselor01", "password": "sandiAman123"}
    )
    assert login.status_code == 403
    assert "Masa aktif" in login.json()["detail"]

    # Perpanjang masa aktif -> bisa login lagi (batas tanggal itu sendiri masih berlaku).
    user_id = res.json()["id"]
    depan = (date.today() + timedelta(days=30)).isoformat()
    upd = client.put(
        f"/api/admin/admins/{user_id}", json={"masa_aktif_akhir": depan}, headers=admin_headers
    )
    assert upd.status_code == 200
    login = client.post(
        "/api/admin/login", json={"username": "konselor01", "password": "sandiAman123"}
    )
    assert login.status_code == 200

    # Hapus batas (null) juga diperbolehkan.
    upd = client.put(
        f"/api/admin/admins/{user_id}", json={"masa_aktif_akhir": None}, headers=admin_headers
    )
    assert upd.status_code == 200
    assert upd.json()["masa_aktif_akhir"] is None


def test_admin_direct_reset_password(client, admin_headers):
    assert _create(client, admin_headers).status_code == 201
    user_id = client.get("/api/admin/admins", headers=admin_headers).json()["items"][-1]["id"]
    res = client.post(
        f"/api/admin/admins/{user_id}/reset-password",
        json={"password_baru": "sandiBaru456"},
        headers=admin_headers,
    )
    assert res.status_code == 200
    ok = client.post(
        "/api/admin/login", json={"username": "konselor01", "password": "sandiBaru456"}
    )
    assert ok.status_code == 200
    lama = client.post(
        "/api/admin/login", json={"username": "konselor01", "password": "sandiAman123"}
    )
    assert lama.status_code == 401


# ------------------------------------------------------- OTP lupa sandi
def test_forgot_password_unknown_or_incomplete_is_generic(client, db, admin_headers):
    # Username tak dikenal: tetap 200 generik, tanpa kode debug.
    res = client.post("/api/admin/forgot-password", json={"username": "tidak_ada"})
    assert res.status_code == 200
    body = res.json()
    assert "Jika akun terdaftar" in body["pesan"]
    assert "debug_code" not in body

    # Admin tanpa nomor WA terdaftar: juga generik (tidak bisa kirim).
    make = client.get("/api/admin/admins", headers=admin_headers)
    assert make.status_code == 200
    res = client.post("/api/admin/forgot-password", json={"username": "admin"})
    assert res.status_code == 200
    assert "debug_code" not in res.json()


def test_reset_password_flow_success(client, db, admin_headers):
    _give_wa(db)
    res = client.post("/api/admin/forgot-password", json={"username": "admin"})
    assert res.status_code == 200
    kode = res.json().get("debug_code")
    assert kode and len(kode) == 6  # lingkungan uji non-produksi menampilkan kode

    res = client.post(
        "/api/admin/reset-password",
        json={"username": "admin", "kode": kode, "password_baru": "sandiOtp789"},
    )
    assert res.status_code == 200, res.text

    ok = client.post("/api/admin/login", json={"username": "admin", "password": "sandiOtp789"})
    assert ok.status_code == 200
    lama = client.post("/api/admin/login", json={"username": "admin", "password": "adminpass123"})
    assert lama.status_code == 401

    # OTP terpakai -> tidak bisa dipakai lagi.
    res = client.post(
        "/api/admin/reset-password",
        json={"username": "admin", "kode": kode, "password_baru": "sandiOtp000"},
    )
    assert res.status_code == 400


def test_reset_password_wrong_code(client, db, admin_headers):
    _give_wa(db)
    client.post("/api/admin/forgot-password", json={"username": "admin"})
    res = client.post(
        "/api/admin/reset-password",
        json={"username": "admin", "kode": "000000", "password_baru": "sandiOtp789"},
    )
    assert res.status_code == 400
    assert "salah" in res.json()["detail"]


def test_reset_password_expired_code(client, db, admin_headers):
    from app.models import User

    _give_wa(db)
    client.post("/api/admin/forgot-password", json={"username": "admin"})
    u = db.query(User).filter(User.username == "admin").first()
    u.otp_expires_at = utcnow() - timedelta(minutes=1)
    db.commit()

    res = client.post(
        "/api/admin/reset-password",
        json={"username": "admin", "kode": "123456", "password_baru": "sandiOtp789"},
    )
    assert res.status_code == 400
    assert "kedaluwarsa" in res.json()["detail"]


def test_forgot_password_resend_rate_limited(client, db, admin_headers):
    _give_wa(db)
    ok = client.post("/api/admin/forgot-password", json={"username": "admin"})
    assert ok.status_code == 200
    soon = client.post("/api/admin/forgot-password", json={"username": "admin"})
    assert soon.status_code == 429


def test_forgot_password_rejected_for_inactive_account(client, db, admin_headers):
    assert _create(client, admin_headers).status_code == 201
    _give_wa(db, "konselor01")
    user_id = client.get("/api/admin/admins", headers=admin_headers).json()["items"][-1]["id"]
    client.put(
        f"/api/admin/admins/{user_id}", json={"is_active": False}, headers=admin_headers
    )
    # Respons tetap generik, tapi TIDAK ada kode debug (kode tidak benar-benar dikirim).
    res = client.post("/api/admin/forgot-password", json={"username": "konselor01"})
    assert res.status_code == 200
    assert "debug_code" not in res.json()
