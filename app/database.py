"""Koneksi & sesi database (SQLAlchemy).

SQLite dipakai untuk pengembangan. Struktur model dibuat dengan tipe
data standar SQLAlchemy sehingga mudah dimigrasi ke PostgreSQL hanya
dengan mengubah DATABASE_URL.
"""
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


def _make_engine(url: str):
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _make_engine(settings.DATABASE_URL)

def _enable_sqlite_fk(dbapi_conn, _record):
    """Aktifkan penegakan foreign key di SQLite (nonaktif secara default)."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def enable_sqlite_fk(target_engine) -> None:
    """Pasang listener PRAGMA foreign_keys pada engine SQLite tertentu.

    Dipanggil untuk engine utama maupun engine uji agar perilaku FK konsisten.
    """
    if target_engine.dialect.name == "sqlite":
        event.listen(target_engine, "connect", _enable_sqlite_fk)


enable_sqlite_fk(engine)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Kelas dasar seluruh model ORM."""


def get_db():
    """Dependency FastAPI: menyediakan sesi database per-request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    """Migrasi ringan (idempoten) untuk database lama.

    Base.metadata.create_all hanya membuat TABEL baru; kolom tambahan pada
    tabel lama perlu ALTER TABLE manual. Dipanggil otomatis oleh init_db().
    """
    insp = inspect(engine)
    if "followups" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("followups")}
        if "petugas_id" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE followups ADD COLUMN petugas_id INTEGER"))


def init_db() -> None:
    """Membuat seluruh tabel bila belum ada + menjalankan migrasi (idempoten)."""
    from . import models  # noqa: F401  (pastikan model terdaftar)

    Base.metadata.create_all(bind=engine)
    run_migrations()
