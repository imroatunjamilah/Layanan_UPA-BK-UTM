"""Pengujian autentikasi admin & proteksi endpoint (RBAC)."""
from app.models import User
from app.security import hash_password

from .conftest import make_admin


def test_login_sukses_mengembalikan_token(client, db):
    make_admin(db)
    res = client.post("/api/admin/login", json={"username": "admin", "password": "adminpass123"})
    assert res.status_code == 200
    data = res.json()
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["role"] == "admin"
    # cookie sesi juga diset (HttpOnly)
    assert "upa_admin_session" in res.cookies


def test_login_password_salah_401(client, db):
    make_admin(db)
    res = client.post("/api/admin/login", json={"username": "admin", "password": "bukan-sandi"})
    assert res.status_code == 401


def test_login_user_tak_dikenal_401(client, db):
    res = client.post("/api/admin/login", json={"username": "tidakada", "password": "apa-pun"})
    assert res.status_code == 401


def test_password_tidak_pernah_tersimpan_plain(client, db):
    user = make_admin(db, username="plaincheck", password="sandiRahasia123")
    db.refresh(user)
    assert user.password_hash != "sandiRahasia123"
    assert user.password_hash.startswith("pbkdf2_sha256$")


def test_endpoint_terlindungi_tanpa_token_401(client, db):
    make_admin(db)
    for path in ("/api/admin/me", "/api/admin/stats", "/api/admin/registrations"):
        assert client.get(path).status_code == 401, path


def test_token_palsu_ditolak_401(client, db):
    res = client.get("/api/admin/stats", headers={"Authorization": "Bearer token.palsu"})
    assert res.status_code == 401


def test_token_kedaluwarsa_ditolak_401(client, db):
    make_admin(db)
    from app.security import create_access_token

    token = create_access_token("admin", "admin", expires_minutes=-1)
    res = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_ganti_password_flow(client, db):
    make_admin(db)
    login = client.post("/api/admin/login", json={"username": "admin", "password": "adminpass123"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # password lama salah
    res = client.patch("/api/admin/password", headers=headers,
                       json={"password_lama": "salah", "password_baru": "sandiBaru456"})
    assert res.status_code == 400

    # ganti berhasil
    res = client.patch("/api/admin/password", headers=headers,
                       json={"password_lama": "adminpass123", "password_baru": "sandiBaru456"})
    assert res.status_code == 200

    # sandi lama gagal, sandi baru berhasil
    assert client.post("/api/admin/login",
                       json={"username": "admin", "password": "adminpass123"}).status_code == 401
    assert client.post("/api/admin/login",
                       json={"username": "admin", "password": "sandiBaru456"}).status_code == 200


def test_password_baru_terlalu_pendek_ditolak(client, db):
    make_admin(db)
    token = client.post("/api/admin/login",
                        json={"username": "admin", "password": "adminpass123"}).json()["access_token"]
    res = client.patch("/api/admin/password", headers={"Authorization": f"Bearer {token}"},
                       json={"password_lama": "adminpass123", "password_baru": "pendek"})
    assert res.status_code == 422


def test_rate_limit_login_setelah_5_kegagalan(client, db):
    username = "rate_limit_user"
    make_admin(db, username=username, password="sandiBenar123")
    for _ in range(5):
        res = client.post("/api/admin/login", json={"username": username, "password": "salah"})
        assert res.status_code == 401
    # percobaan ke-6 diblokir meski password benar
    res = client.post("/api/admin/login", json={"username": username, "password": "sandiBenar123"})
    assert res.status_code == 429


def test_hash_bisa_diverifikasi_dan_format_benar():
    hashed = hash_password("kata-sandi-aman")
    assert hashed.startswith("pbkdf2_sha256$")
    from app.security import verify_password

    assert verify_password("kata-sandi-aman", hashed)
    assert not verify_password("kata-sandi-salah", hashed)


def test_user_model_role_default_admin(client, db):
    user = make_admin(db, username="roletest", password="sandi12345")
    db.refresh(user)
    assert isinstance(user, User)
    assert user.role == "admin"
    assert user.created_at is not None
