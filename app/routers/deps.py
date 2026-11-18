"""Dependency & skema bersama untuk router."""
import logging
from datetime import date

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import TokenError, decode_access_token

logger = logging.getLogger("app.api")

SESSION_COOKIE = "upa_admin_session"


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(SESSION_COOKIE)


def account_status(user: User) -> str:
    """Status efektif akun: 'aktif' | 'nonaktif' | 'kedaluwarsa'."""
    if not user.is_active:
        return "nonaktif"
    if user.masa_aktif_akhir is not None and date.today() > user.masa_aktif_akhir:
        return "kedaluwarsa"
    return "aktif"


def ensure_account_usable(user: User) -> None:
    """Blokir akun nonaktif / masa aktif berakhir (dipakai login & tiap request)."""
    kondisi = account_status(user)
    if kondisi == "nonaktif":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Akun Anda dinonaktifkan. Hubungi administrator utama UPA BK.",
        )
    if kondisi == "kedaluwarsa":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Masa aktif akun Anda telah berakhir (s.d. {user.masa_aktif_akhir.isoformat()}). "
            "Hubungi administrator utama UPA BK.",
        )


def get_current_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """RBAC: hanya akun ber-role 'admin' yang boleh melewati endpoint terlindungi.

    Sesi yang masih bertanda tangan pun ditolak bila akunnya sudah dinonaktifkan
    atau masa aktifnya berakhir - penonaktifan berlaku seketika.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Belum login.")
    try:
        data = decode_access_token(token)
    except TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesi tidak valid atau kedaluwarsa.")
    user = db.query(User).filter(User.username == data.get("sub")).first()
    if not user or user.role != "admin":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Akses hanya untuk petugas/admin.")
    ensure_account_usable(user)
    return user
