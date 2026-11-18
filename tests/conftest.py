"""Konfigurasi pytest: database in-memory + klien uji + fixture bantu."""
import os

# Harus di-set SEBELUM mengimpor modul aplikasi.
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_ALLOW_EXTERNAL"] = "false"
# Paksa database uji in-memory (tes memakai engine sendiri via dependency override).
os.environ["DATABASE_URL"] = "sqlite://"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, enable_sqlite_fk, get_db  # noqa: E402


class _State:
    engine = None
    Session = None


@pytest.fixture()
def client():
    """Klien uji dengan database SQLite in-memory per-fungsi."""
    from app.main import create_app

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    enable_sqlite_fk(engine)  # samakan perilaku FK dengan engine produksi
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    _State.engine = engine
    _State.Session = SessionLocal

    app = create_app(init_db_on_start=False)

    def _override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def db(client):
    """Sesi database untuk asersi langsung terhadap isi tabel."""
    session = _State.Session()
    try:
        yield session
    finally:
        session.close()


def make_admin(db, username: str = "admin", password: str = "adminpass123"):
    from app.models import User
    from app.security import hash_password

    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = User(username=username, password_hash=hash_password(password), role="admin")
        db.add(user)
        db.commit()
    return user


@pytest.fixture()
def admin_headers(client, db):
    make_admin(db)
    res = client.post("/api/admin/login", json={"username": "admin", "password": "adminpass123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


VALID_REGISTRATION = {
    "nama": "Budi Contoh",
    "nim": "2101101999",
    "kontak": "budi.contoh@mail.contoh.ac.id",
    "jenis_layanan": "Konseling Individu",
    "preferensi_hari": "Senin",
    "preferensi_waktu": "Pagi (08.00-11.00)",
    "keluhan": "Sulit fokus belajar karena cemas berlebihan.",
    "setuju_penggunaan_data": True,
}


def register_student(client, **overrides):
    payload = {**VALID_REGISTRATION, **overrides}
    res = client.post("/api/registrations", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def full_answers():
    """Pola jawaban tetap: item i bernilai i mod 4 (0-3)."""
    return {str(i): (i % 4) for i in range(1, 22)}


def submit_dass(client, reg_json, answers=None):
    res = client.post(
        "/api/dass21/submit",
        json={
            "registration_id": reg_json["registration_id"],
            "chat_token": reg_json["chat_token"],
            "jawaban": answers or full_answers(),
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture()
def sample_registration(client):
    """Satu pendaftaran mahasiswa yang sudah menyelesaikan skrining DASS-21."""
    reg = register_student(client)
    submit_dass(client, reg)
    return reg
