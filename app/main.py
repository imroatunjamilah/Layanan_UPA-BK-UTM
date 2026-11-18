"""Aplikasi FastAPI UPA BK UTM.

- Semua API berada di bawah /api (diaktifkan routers).
- Frontend statis (Bahasa Indonesia) dilayani dari folder frontend/ di root.
- Saat startup: database & tabel dibuat otomatis; akun admin awal dibuat bila
  belum ada user sama sekali (kredensial dari env, wajib diganti).
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import SessionLocal, init_db
from .models import User
from .routers import admin, chat, dass21, registrations
from .security import hash_password

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

FRONTEND_DIR = settings.BASE_DIR / "frontend"

PAGES = ["index", "registrasi", "dass21", "chatbot", "admin-login", "admin-dashboard"]


def _ensure_bootstrap_admin() -> None:
    """Membuat akun admin awal bila belum ada user sama sekali.

    Idempoten (aman dijalankan berulang) dan berlaku di lingkungan mana pun,
    sehingga deployment baru (mis. Render) langsung punya akun admin tanpa
    perlu akses shell.

    - APP_ENV development/test : pakai default admin/admin123 bila env kosong.
    - APP_ENV production       : wajib isi ADMIN_USERNAME & ADMIN_PASSWORD lewat
      environment; bila kosong/masih default, akun TIDAK dibuat demi keamanan
      (jangan pernah pakai sandi default di internet) dan aplikasi mencatat
      peringatan di log.
    """
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        username = settings.ADMIN_USERNAME
        password = settings.ADMIN_PASSWORD
        produksi = settings.APP_ENV == "production"
        if produksi and (not password or password == "admin123"):
            logger.warning(
                "APP_ENV=production tetapi ADMIN_PASSWORD belum diisi lewat Environment. "
                "Akun admin TIDAK dibuat demi keamanan. Isi ADMIN_USERNAME & "
                "ADMIN_PASSWORD di dashboard Render (Web Service -> Environment) "
                "lalu klik Manual Deploy / Restart.",
            )
            return
        db.add(User(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            nama_lengkap="Administrator Utama",
            is_active=True,
        ))
        db.commit()
        logger.warning(
            "Akun admin awal dibuat (username=%s). SEGERA ganti sandi lewat menu "
            "Ganti Sandi di dashboard admin!",
            username,
        )
    finally:
        db.close()


def create_app(init_db_on_start: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if init_db_on_start:
            init_db()
            _ensure_bootstrap_admin()
            logger.info("Database siap: %s", settings.DATABASE_URL)
        yield

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # prototipe: frontend dilayani same-origin; perketat saat produksi
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(registrations.router)
    app.include_router(dass21.router)
    app.include_router(chat.router)
    app.include_router(admin.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "app": settings.APP_NAME, "versi": settings.APP_VERSION}

    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="frontend")
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="site")
    else:  # pragma: no cover - hanya bila folder frontend dihapus
        logger.warning("Folder frontend tidak ditemukan; hanya API yang dilayani.")

    return app


app = create_app()
