"""Inisialisasi database: membuat semua tabel bila belum ada.

Skrip ini aman dijalankan berulang (idempoten) karena memakai
Base.metadata.create_all yang hanya membuat tabel yang belum tersedia.

Pemakaian:
    python init_db.py
"""
from app.config import settings
from app.database import init_db


def main() -> None:
    init_db()
    print("✔ Database siap dan semua tabel telah dibuat/diperiksa.")
    print(f"  Lokasi database : {settings.DATABASE_URL}")
    print("  Tabel           : users, petugas, registrations, dass21_responses,")
    print("                    conversations, messages, followups")
    print()
    print("Langkah berikutnya:")
    print("  - Untuk mengisi data dummy pengembangan : python seed_data.py")
    print("  - Untuk menjalankan aplikasi            : python run.py")


if __name__ == "__main__":
    main()
