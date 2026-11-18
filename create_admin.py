"""Membuat akun admin baru atau mengganti sandi admin yang sudah ada.

Pemakaian:
    python create_admin.py                      # interaktif (minta input)
    python create_admin.py petugas01 sandiAman123
    python create_admin.py petugas01 sandiAman123 "Ratna Wulandari" 2101101999 \
        Fakultas Psikologi 08123456789

Profil (nama, NIM, fakultas, no. WhatsApp) boleh dilewati saat membuat akun
via CLI, tetapi sebaiknya dilengkapi lewat dashboard (Manajemen Akun Admin)
karena nomor WhatsApp dipakai untuk kode OTP reset kata sandi.
"""
import getpass
import sys

from app.config import settings
from app.database import SessionLocal, init_db
from app.models import User
from app.security import hash_password
from app.services.wa import normalize_wa


def main() -> None:
    init_db()

    args = sys.argv[1:]
    username = args[0] if len(args) >= 1 else input("Username admin: ").strip()
    if not username:
        print("Username tidak boleh kosong.")
        sys.exit(1)

    if len(args) >= 2:
        password = args[1]
    else:
        password = getpass.getpass("Password admin (min. 8 karakter): ")
        confirm = getpass.getpass("Ulangi password: ")
        if password != confirm:
            print("Password tidak sama.")
            sys.exit(1)
    if len(password) < 8:
        print("Password minimal 8 karakter.")
        sys.exit(1)

    # Argumen profil opsional: nama, nim, fakultas, no WA (atau dikosongkan).
    nama = args[2].strip() if len(args) >= 3 else None
    nim = args[3].strip() if len(args) >= 4 else None
    fakultas = args[4].strip() if len(args) >= 5 else None
    wa_raw = args[5].strip() if len(args) >= 6 else None
    wa = normalize_wa(wa_raw) if wa_raw else None
    if wa_raw and not wa:
        print("Nomor WhatsApp tidak valid (contoh: 08123456789).")
        sys.exit(1)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user:
            user.password_hash = hash_password(password)
            user.role = "admin"
            if nama:
                user.nama_lengkap = nama
            if nim:
                user.nim = nim
            if fakultas:
                user.fakultas = fakultas
            if wa:
                user.no_whatsapp = wa
            action = f"Sandi admin '{username}' berhasil diperbarui."
        else:
            user = User(
                username=username,
                password_hash=hash_password(password),
                role="admin",
                nama_lengkap=nama,
                nim=nim,
                fakultas=fakultas,
                no_whatsapp=wa,
                is_active=True,
            )
            db.add(user)
            action = f"Admin baru '{username}' berhasil dibuat."
        db.commit()
        print(f"✔ {action}")
        if not user.no_whatsapp:
            print("  Catatan: akun belum punya nomor WhatsApp (reset sandi via OTP belum bisa).")
        print("  Gunakan kredensial ini pada halaman login admin (/admin-login.html).")
    finally:
        db.close()


if __name__ == "__main__":
    if settings.APP_ENV != "development":
        print("Peringatan: APP_ENV bukan 'development'. Pastikan Anda memakai sandi yang kuat.")
    main()
