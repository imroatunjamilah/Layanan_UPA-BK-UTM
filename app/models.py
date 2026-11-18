"""Model database UPA BK UTM.

Delapan tabel:
  users, petugas, registrations, dass21_responses, conversations, messages,
  followups, schedules

Kolom waktu disimpan sebagai UTC naive; serialisasi API menambahkan penanda 'Z'
(lihat app.utils.iso_utc) sehingga klien bisa menampilkannya di zona waktu lokal
(mis. WIB).
"""
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base
from .utils import utcnow


class User(Base):
    """Akun pengguna internal (admin/petugas UPA BK). Mahasiswa TIDAK memiliki akun.

    Kelola akses login:
    - is_active        : akun dinonaktifkan langsung tidak bisa login (sesi pun hangus).
    - masa_aktif_akhir : batas tanggal (inklusif) akun boleh dipakai; NULL = selamanya.
    - Profil (nama_lengkap, nim, fakultas) wajib diisi saat akun dibuat dari dashboard.
    - Kolom otp_* memegang kode reset kata sandi (hash SHA-256, TIDAK pernah plain).
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), nullable=False, unique=True, index=True)
    password_hash = Column(String(256), nullable=False)  # PBKDF2-SHA256, tidak pernah plain text
    role = Column(String(20), nullable=False, default="admin")  # admin | petugas
    nama_lengkap = Column(String(120), nullable=True)
    nim = Column(String(30), nullable=True)
    fakultas = Column(String(120), nullable=True)
    no_whatsapp = Column(String(30), nullable=True)  # format 62..., tujuan OTP reset sandi
    is_active = Column(Boolean, nullable=False, default=True)
    masa_aktif_akhir = Column(Date, nullable=True)  # tanggal terakhir akun berlaku (inklusif)
    # Kode reset kata sandi sementara (disimpan sebagai hash, kedaluwarsa otomatis).
    otp_hash = Column(String(128), nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)
    otp_attempts = Column(Integer, nullable=False, default=0)
    otp_sent_at = Column(DateTime, nullable=True)  # untuk batas jeda kirim ulang kode
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Petugas(Base):
    """Daftar petugas/konselor penangani yang dikelola admin.

    BUKAN akun login - hanya direktori nama staf agar admin dapat menetapkan
    siapa yang menangani setiap kasus (penanggung jawab).
    """

    __tablename__ = "petugas"

    id = Column(Integer, primary_key=True)
    nama = Column(String(120), nullable=False)
    peran = Column(String(50), nullable=False, default="Konselor")
    kontak = Column(String(120), nullable=True)
    aktif = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Registration(Base):
    """Pendaftaran layanan konseling oleh mahasiswa."""

    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True)
    nama = Column(String(120), nullable=False)
    nim = Column(String(30), nullable=False, index=True)
    kontak = Column(String(120), nullable=False)
    jenis_layanan = Column(String(50), nullable=False, index=True)
    # Preferensi tanggal/waktu: HANYA preferensi awal, bukan jadwal terkonfirmasi.
    preferensi_hari = Column(String(20), nullable=False)
    preferensi_waktu = Column(String(20), nullable=False)
    keluhan = Column(Text, nullable=True)  # opsional, digambar ulang mahasiswa sendiri
    consent_status = Column(String(20), nullable=False)  # "disetujui"
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)

    dass21 = relationship(
        "Dass21Response", back_populates="registration",
        cascade="all, delete-orphan", uselist=False,
    )
    conversations = relationship(
        "Conversation", back_populates="registration", cascade="all, delete-orphan",
    )
    followup = relationship(
        "Followup", back_populates="registration",
        cascade="all, delete-orphan", uselist=False,
    )
    schedules = relationship(
        "Schedule", back_populates="registration",
        cascade="all, delete-orphan", order_by="Schedule.tanggal",
    )


class Dass21Response(Base):
    """Jawaban & hasil skrining DASS-21 (21 item, skala 0-3).

    Skor TIDAK PERNAH dikirim ke mahasiswa; hanya ditampilkan kepada admin.
    """

    __tablename__ = "dass21_responses"
    __table_args__ = (UniqueConstraint("registration_id", name="uq_dass21_registration"),)

    id = Column(Integer, primary_key=True)
    registration_id = Column(
        Integer, ForeignKey("registrations.id"), nullable=False, index=True
    )
    jawaban_1 = Column(Integer, nullable=False)
    jawaban_2 = Column(Integer, nullable=False)
    jawaban_3 = Column(Integer, nullable=False)
    jawaban_4 = Column(Integer, nullable=False)
    jawaban_5 = Column(Integer, nullable=False)
    jawaban_6 = Column(Integer, nullable=False)
    jawaban_7 = Column(Integer, nullable=False)
    jawaban_8 = Column(Integer, nullable=False)
    jawaban_9 = Column(Integer, nullable=False)
    jawaban_10 = Column(Integer, nullable=False)
    jawaban_11 = Column(Integer, nullable=False)
    jawaban_12 = Column(Integer, nullable=False)
    jawaban_13 = Column(Integer, nullable=False)
    jawaban_14 = Column(Integer, nullable=False)
    jawaban_15 = Column(Integer, nullable=False)
    jawaban_16 = Column(Integer, nullable=False)
    jawaban_17 = Column(Integer, nullable=False)
    jawaban_18 = Column(Integer, nullable=False)
    jawaban_19 = Column(Integer, nullable=False)
    jawaban_20 = Column(Integer, nullable=False)
    jawaban_21 = Column(Integer, nullable=False)
    skor_depresi = Column(Integer, nullable=False)
    skor_kecemasan = Column(Integer, nullable=False)
    skor_stres = Column(Integer, nullable=False)
    scoring_version = Column(String(20), nullable=False)  # versi algoritma penilaian
    submitted_at = Column(DateTime, nullable=False, default=utcnow, index=True)

    registration = relationship("Registration", back_populates="dass21")


class Conversation(Base):
    """Sesi percakapan mahasiswa dengan chatbot (satu registration dapat punya >1 sesi)."""

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    registration_id = Column(
        Integer, ForeignKey("registrations.id"), nullable=False, index=True
    )
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    registration = relationship("Registration", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation",
        cascade="all, delete-orphan", order_by="Message.created_at",
    )


class Message(Base):
    """Satu pesan dalam percakapan.

    sender: "mahasiswa" | "bot" | "sistem"
      - mahasiswa : pesan dari mahasiswa
      - bot       : balasan asisten/chatbot
      - sistem    : catatan audit internal (mis. penanda eskalasi krisis),
                    TIDAK dikirim ke mahasiswa, hanya terlihat oleh admin.
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id"), nullable=False, index=True
    )
    sender = Column(String(20), nullable=False)
    message_text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)

    conversation = relationship("Conversation", back_populates="messages")


class Followup(Base):
    """Status tindak lanjut layanan (satu baris aktif per pendaftaran)."""

    __tablename__ = "followups"
    __table_args__ = (UniqueConstraint("registration_id", name="uq_followup_registration"),)

    id = Column(Integer, primary_key=True)
    registration_id = Column(
        Integer, ForeignKey("registrations.id"), nullable=False, index=True
    )
    # menunggu_ditinjau | sedang_diproses | dijadwalkan | selesai | perlu_ditinjau_segera
    status = Column(String(30), nullable=False, default="menunggu_ditinjau")
    catatan_petugas = Column(Text, nullable=True)
    assigned_admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Petugas penangani yang DITETAPKAN admin (beda dengan assigned_admin_id
    # yang otomatis mencatat akun admin terakhir yang memperbarui baris ini).
    petugas_id = Column(Integer, ForeignKey("petugas.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    registration = relationship("Registration", back_populates="followup")
    assigned_admin = relationship("User")
    petugas = relationship("Petugas")


class Schedule(Base):
    """Jadwal sesi konseling FINAL yang ditetapkan admin/petugas.

    Berbeda dengan `preferensi_hari`/`preferensi_waktu` pada Registration (hanya
    keinginan awal mahasiswa), baris di sini adalah jadwal terkonfirmasi:
    tanggal + jam + konselor penanggung jawab. Satu kasus dapat memiliki lebih
    dari satu sesi (mis. sesi lanjutan).

    - tanggal   : tanggal sesi menurut WIB (Asia/Jakarta) - bukan turunan timestamp UTC.
    - jam_mulai : "HH:MM" menurut WIB; akhir sesi = jam_mulai + durasi_menit.
    - status    : terjadwal | selesai | dibatalkan | ditunda.
    - created_by: akun admin yang membuat/mengubah jadwal (jejak audit).
    """

    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True)
    registration_id = Column(
        Integer, ForeignKey("registrations.id"), nullable=False, index=True
    )
    petugas_id = Column(Integer, ForeignKey("petugas.id"), nullable=True, index=True)
    tanggal = Column(Date, nullable=False, index=True)
    jam_mulai = Column(String(5), nullable=False)  # format "HH:MM" (WIB)
    durasi_menit = Column(Integer, nullable=False, default=60)
    metode = Column(String(30), nullable=False, default="Tatap Muka")  # Tatap Muka | Online | Lainnya
    lokasi = Column(String(200), nullable=True)  # ruangan atau tautan meeting
    catatan = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="terjadwal", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    registration = relationship("Registration", back_populates="schedules")
    petugas = relationship("Petugas")
    creator = relationship("User")
