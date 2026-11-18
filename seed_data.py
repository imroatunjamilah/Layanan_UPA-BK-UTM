"""Mengisi database dengan data virtual/dummy untuk PENGEMBANGAN SAJA.

Isi:
- 1 akun admin pengembangan (dari env ADMIN_USERNAME/ADMIN_PASSWORD).
- 10 profil mahasiswa FIKTIF (nama, NIM, kontak semu).
- 10 pendaftaran (jenis layanan & preferensi bervariasi) + tindak lanjut beragam.
- 3 petugas penangani FIKTIF + contoh penugasan penanggung jawab pada beberapa kasus.
- 10 hasil skrining DASS-21 sintetis (jawaban digenerate, skor dihitung dengan
  modul scoring asli agar konsisten dengan algoritma produksi).
- Contoh keluhan (generik, fiktif).
- Contoh percakapan (termasuk satu contoh eskalasi krisis yang ditangani sistem).
- 1 percakapan contoh dengan permintaan pendampingan manusia.

KEAMANAN: Semua nama/NIM/kontak adalah FIKTIF. Jangan pernah memasukkan data
mahasiswa asli ke skrip ini. Skrip menolak berjalan di luar mode development
kecuali diberi flag --force.

Pemakaian:
    python seed_data.py            # isi data dummy (tolak bila sudah ada data)
    python seed_data.py --force    # paksa isi meski database berisi data / APP_ENV != development
"""
import random
import sys
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import SessionLocal, init_db
from app.models import (
    Conversation,
    Dass21Response,
    Followup,
    Message,
    Petugas,
    Registration,
    Schedule,
    User,
)
from app.security import hash_password
from app.services import crisis
from app.services.dass21_scoring import score_answers, SUBSCALE_ITEMS
from app.utils import utcnow

# ------------------------------------------------------------------ data fiktif
# NAMA/NIM/KONTAK SEPENUHNYA FIKTIF (domain "mail.contoh.ac.id" = contoh).
STUDENTS = [
    # (nama, nim, kontak, jenis_layanan, hari, waktu, keluhan)
    ("Andi Pratama", "2101101001", "andi.pratama@mail.contoh.ac.id", "Konseling Individu",
     "Senin", "Pagi (08.00-11.00)",
     "Sulit fokus kuliah karena sering overthinking soal tugas dan nilai."),
    ("Bunga Sari Dewi", "2101101002", "081234500002", "Konseling Kelompok",
     "Rabu", "Siang (11.00-14.00)", None),
    ("Citra Ayu Lestari", "2101101003", "citra.lestari@mail.contoh.ac.id", "Konseling Individu",
     "Kamis", "Sore (14.00-17.00)",
     "Sering merasa sedih tanpa sebab yang jelas, semangat menurun bulan ini."),
    ("Dimas Anggara", "2101101004", "081234500004", "Konsultasi Karier",
     "Jumat", "Pagi (08.00-11.00)",
     "Bingung menentukan arah karier setelah lulus, khawatir tidak siap kerja."),
    ("Eka Putri Ramadhani", "2101101005", "eka.putri@mail.contoh.ac.id", "Konseling Individu",
     "Senin", "Siang (11.00-14.00)",
     "Tidak bisa tidur nyenyak, sering terbangun karena pikiran berat."),
    ("Farhan Maulana", "2101101006", "081234500006", "Edukasi Kesehatan Mental",
     "Selasa", "Sore (14.00-17.00)", None),
    ("Gita Nurhaliza", "2101101007", "gita.nur@mail.contoh.ac.id", "Konseling Individu",
     "Rabu", "Pagi (08.00-11.00)",
     "Gugup berlebihan setiap harus presentasi di depan kelas."),
    ("Hendra Wijaya", "2101101008", "081234500008", "Konseling Kelompok",
     "Kamis", "Siang (11.00-14.00)",
     "Merasa kesepian setelah pindah domisili, sulit bergaul dengan teman baru."),
    ("Indah Permata Sari", "2101101009", "081234500009", "Konsultasi Karier",
     "Jumat", "Siang (11.00-14.00)", None),
    ("Joko Susilo", "2101101010", "joko.susilo@mail.contoh.ac.id", "Konseling Individu",
     "Selasa", "Pagi (08.00-11.00)",
     "Beban organisasi dan kuliah terasa menumpuk, mudah tersinggung belakangan ini."),
]

# Intensitas sintetis per subskala (0.0 normal ... 1.0 sangat berat) untuk tiap mahasiswa.
DASS_PROFILES = [
    {"depresi": 0.10, "kecemasan": 0.10, "stres": 0.20},
    {"depresi": 0.20, "kecemasan": 0.15, "stres": 0.15},
    {"depresi": 0.40, "kecemasan": 0.20, "stres": 0.25},
    {"depresi": 0.25, "kecemasan": 0.55, "stres": 0.40},
    {"depresi": 0.75, "kecemasan": 0.80, "stres": 0.95},
    {"depresi": 0.10, "kecemasan": 0.10, "stres": 0.10},
    {"depresi": 0.20, "kecemasan": 0.25, "stres": 0.40},
    {"depresi": 0.55, "kecemasan": 0.40, "stres": 0.45},
    {"depresi": 0.10, "kecemasan": 0.15, "stres": 0.10},
    {"depresi": 0.25, "kecemasan": 0.40, "stres": 0.30},
]

# Direktori petugas penangani (FIKTIF) - bukan akun login, hanya penanda penanggung jawab.
PETUGAS = [
    # (nama, peran, kontak)
    ("Dra. Ratna Wulandari, M.Psi", "Psikolog Klinis", "ratna.wulandari@upabk.contoh.ac.id"),
    ("Andi Prasetyo, M.Psi", "Konselor Senior", "andi.prasetyo@upabk.contoh.ac.id"),
    ("Siti Rahmawati, S.Psi", "Parapiawai Konseling", "siti.rahmawati@upabk.contoh.ac.id"),
]

# Status tindak lanjut awal (bervariasi; bisa berubah otomatis oleh contoh krisis).
FOLLOWUP_STATES = [
    ("menunggu_ditinjau", None),
    ("menunggu_ditinjau", None),
    ("sedang_diproses", "Sudah dihubungi via telepon, mahasiswa bersedia lanjut konseling individu."),
    ("menunggu_ditinjau", None),
    ("menunggu_ditinjau", None),
    ("menunggu_ditinjau", None),
    ("dijadwalkan", "Sesi pertama dijadwalkan sesuai preferensi, menunggu konfirmasi ruang."),
    ("sedang_diproses", "Diproses: mahasiswa akan dihubungkan ke kelompok dukungan sebaya."),
    ("selesai", "Sesi konsultasi karier selesai; mahasiswa menyatakan lebih siap menyusun rencana."),
    ("selesai", "Konseling individu selesai 2 sesi; hasil memuaskan, anjuran kontrol bila perlu."),
]

# Contoh percakapan (indeks mahasiswa 0-based) - semuanya fiktif.
CONVERSATIONS = {
    2: [  # Citra - tema akademik/sedih
        ("mahasiswa", "Akhir-akhir ini saya sering merasa sedih tanpa alasan yang jelas, bu."),
        ("bot", "Terima kasih sudah mau terbuka tentang perasaan sedih ini. Menahan perasaan seperti itu tidak mudah. Kapan mulai terasa berat, dan apa yang biasanya muncul saat perasaan itu datang?"),
        ("mahasiswa", "Mulai sekitar sebulan lalu. Setiap malam rasanya berat, kadang sampai nangis sendiri."),
        ("bot", "Terima kasih sudah berbagi. Bagaimana hal ini memengaruhi aktivitas harian Anda, misalnya tidur, kuliah, atau makan?"),
    ],
    4: [  # Eka - PERCAKAPAN KRISIS (contoh penanganan otomatis)
        ("mahasiswa", "Bu, seminggu ini saya tidak bisa tidur. Pikiran saya terus berat."),
        ("bot", "Terdengar seperti pikiran Anda terus berjalan dan sulit dihentikan. Boleh ceritakan, situasi seperti apa yang paling sering memicunya belakangan ini?"),
        ("mahasiswa", "Kadang saya merasa ingin mengakhiri hidup saja, capek sama semuanya."),
        ("bot", crisis.SAFETY_MESSAGE),
        ("sistem", f"{crisis.CRISIS_CONFIG['MARKER_ESKALASI']} Potensi krisis terdeteksi pada pesan mahasiswa - mohon verifikasi dan tindak lanjut segera oleh petugas."),
    ],
    7: [  # Hendra - kesepian + permintaan pendampingan manusia
        ("mahasiswa", "Saya merasa kesepian sejak pindah ke sini, sulit dapat teman."),
        ("bot", "Rasa kesepian itu nyata dan menyakitkan, dan mengakuinya butuh keberanian. Bagaimana hubungan Anda dengan orang-orang di sekitar Anda akhir-akhir ini?"),
        ("mahasiswa", "Masih kaku. Sebenarnya saya ingin bicara dengan konselor langsung."),
        ("bot", crisis.HANDOFF_ACKNOWLEDGMENT),
        ("sistem", f"{crisis.CRISIS_CONFIG['MARKER_OTOMATIS']} Mahasiswa meminta pendampingan manusia/konselor."),
    ],
}


# Contoh jadwal konseling (FIKTIF) - offset hari dari hari ini (WIB), jam WIB.
# Kasus krisis (indeks 4) sengaja diberi slot paling awal untuk mencontohkan
# prioritas penanganan darurat.
JADWAL_CONTOH = [
    # (nim, offset_hari, jam_mulai, durasi_menit, metode, lokasi, catatan)
    ("2101101005", 1, "09:00", 60, "Tatap Muka", "Ruang BK 1",
     "Sesi darurat pasca-eskalasi otomatis - prioritas tertinggi."),
    ("2101101003", 2, "10:00", 60, "Tatap Muka", "Ruang BK 2",
     "Sesi pertama konseling individu."),
    ("2101101008", 3, "13:00", 60, "Online", "meet.google.com/upa-bk-demo",
     "Pendampingan awal setelah permintaan bicara dengan konselor."),
    ("2101101007", 4, "14:00", 90, "Tatap Muka", "Ruang BK 1",
     "Latihan manajemen kecemasan saat presentasi."),
]


def _generate_answers(profile: dict[str, float]) -> dict[int, int]:
    """Menumbuhkan jawaban 0-3 sintetis dari intensitas target per subskala."""
    answers: dict[int, int] = {}
    for subscale, items in SUBSCALE_ITEMS.items():
        intensity = profile[subscale]
        for item in items:
            noise = random.uniform(-0.7, 0.7)
            value = round(intensity * 3 + noise)
            answers[item] = max(0, min(3, int(value)))
    return answers


def main() -> None:
    force = "--force" in sys.argv
    if settings.APP_ENV != "development" and not force:
        print("DITOLAK: APP_ENV bukan 'development'. Skrip ini hanya untuk data dummy pengembangan.")
        print("Gunakan 'python seed_data.py --force' bila benar-benar yakin.")
        sys.exit(1)

    init_db()
    random.seed(7)  # hasil dapat direproduksi

    db = SessionLocal()
    try:
        existing = db.query(Registration).count()
        if existing and not force:
            print(f"DITOLAK: database sudah berisi {existing} pendaftaran. Gunakan --force untuk tetap mengisi.")
            sys.exit(1)

        # --- admin pengembangan -------------------------------------------
        admin = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
        if not admin:
            admin = User(
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                role="admin",
                nama_lengkap="Administrator Utama",
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print(f"✔ Admin pengembangan dibuat: {settings.ADMIN_USERNAME} / {settings.ADMIN_PASSWORD}")

        # --- direktori petugas penangani (fiktif) -------------------------
        if db.query(Petugas).count() == 0:
            for nama, peran, kontak in PETUGAS:
                db.add(Petugas(nama=nama, peran=peran, kontak=kontak))
            db.commit()
            print(f"✔ {len(PETUGAS)} petugas penangani fiktif ditambahkan.")
        petugas_rows = db.query(Petugas).order_by(Petugas.id).all()

        now = utcnow()
        created = 0
        for idx, (nama, nim, kontak, layanan, hari, waktu, keluhan) in enumerate(STUDENTS):
            reg = Registration(
                nama=nama, nim=nim, kontak=kontak,
                jenis_layanan=layanan,
                preferensi_hari=hari, preferensi_waktu=waktu,
                keluhan=keluhan, consent_status="disetujui",
                created_at=now - timedelta(days=random.randint(0, 20), hours=random.randint(0, 9)),
            )
            db.add(reg)
            db.flush()

            # skrining DASS-21 sintetis (skor dihitung modul asli)
            answers = _generate_answers(DASS_PROFILES[idx])
            scored = score_answers(answers)
            db.add(Dass21Response(
                registration_id=reg.id,
                **{f"jawaban_{i}": answers[i] for i in range(1, 22)},
                skor_depresi=scored["skor_depresi"],
                skor_kecemasan=scored["skor_kecemasan"],
                skor_stres=scored["skor_stres"],
                scoring_version=scored["scoring_version"],
                submitted_at=reg.created_at + timedelta(minutes=random.randint(5, 60)),
            ))

            # tindak lanjut
            status, catatan = FOLLOWUP_STATES[idx]
            # Contoh penugasan: kasus non-menunggu ditugaskan bergilir ke petugas
            # (kasus menunggu_ditinjau & krisis sengaja dibiarkan tanpa penangani).
            penangani = None
            if status not in ("menunggu_ditinjau",) and petugas_rows:
                penangani = petugas_rows[idx % len(petugas_rows)]
            followup = Followup(
                registration_id=reg.id, status=status, catatan_petugas=catatan,
                assigned_admin_id=admin.id if status not in ("menunggu_ditinjau",) else None,
                petugas_id=penangani.id if penangani else None,
            )
            db.add(followup)

            # percakapan contoh
            if idx in CONVERSATIONS:
                conv = Conversation(registration_id=reg.id, created_at=reg.created_at)
                db.add(conv)
                db.flush()
                base_time = reg.created_at + timedelta(hours=1)
                for i, (sender, text) in enumerate(CONVERSATIONS[idx]):
                    db.add(Message(
                        conversation_id=conv.id, sender=sender, message_text=text,
                        created_at=base_time + timedelta(minutes=2 * i),
                    ))
                conv.updated_at = base_time + timedelta(minutes=2 * len(CONVERSATIONS[idx]))

            created += 1

        db.commit()

        # contoh krisis pada mahasiswa indeks 4 -> eskalasi otomatis konsisten
        reg_krisis = db.query(Registration).filter(Registration.nim == STUDENTS[4][1]).first()
        if reg_krisis and reg_krisis.followup:
            reg_krisis.followup.status = crisis.CRISIS_CONFIG["STATUS_ESKALASI"]
            note = (
                f"{crisis.CRISIS_CONFIG['MARKER_OTOMATIS']} Sistem menandai potensi krisis "
                "saat obrolan (sesuai konfigurasi default yang perlu persetujuan UPA BK)."
            )
            reg_krisis.followup.catatan_petugas = (
                f"{reg_krisis.followup.catatan_petugas}\n{note}"
                if reg_krisis.followup.catatan_petugas else note
            )
            db.commit()

        # --- contoh jadwal konseling pada minggu berjalan (WIB) ------------
        if db.query(Schedule).count() == 0:
            wib = timezone(timedelta(hours=7))
            hari_ini = datetime.now(wib).date()
            jumlah_jadwal = 0
            for nim, offset, jam, durasi, metode, lokasi, catatan in JADWAL_CONTOH:
                reg = db.query(Registration).filter(Registration.nim == nim).first()
                if not reg:
                    continue
                fu = reg.followup
                if fu is None:
                    fu = Followup(registration_id=reg.id, status="menunggu_ditinjau")
                    db.add(fu)
                    db.flush()
                # Konselor: pakai penangan yang sudah ditetapkan, atau beri giliran
                # petugas aktif agar demo penugasan terlihat.
                petugas_id = fu.petugas_id
                if petugas_id is None and petugas_rows:
                    petugas_id = petugas_rows[jumlah_jadwal % len(petugas_rows)].id
                    fu.petugas_id = petugas_id
                if fu.status in ("menunggu_ditinjau", "sedang_diproses"):
                    fu.status = "dijadwalkan"
                db.add(Schedule(
                    registration_id=reg.id,
                    petugas_id=petugas_id,
                    tanggal=hari_ini + timedelta(days=offset),
                    jam_mulai=jam,
                    durasi_menit=durasi,
                    metode=metode,
                    lokasi=lokasi,
                    catatan=catatan,
                    status="terjadwal",
                    created_by=admin.id,
                ))
                jumlah_jadwal += 1
            db.commit()
            print(f"✔ {jumlah_jadwal} jadwal konseling contoh dibuat pada minggu berjalan (WIB).")

        print(f"✔ {created} pendaftaran dummy (10 mahasiswa fiktif) + skrining + tindak lanjut + contoh obrolan dibuat.")
        print("  Peringatan: data ini FIKTIF dan hanya untuk lingkungan pengembangan.")
        print(f"  Login admin: {settings.ADMIN_USERNAME} (sandi dari ADMIN_PASSWORD di .env)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
