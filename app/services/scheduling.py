"""Logika penjadwalan konseling UPA BK UTM.

Prinsip utama:
1. **Penanganan darurat diprioritaskan** - kasus dengan eskalasi krisis
   (`perlu_ditinjau_segera`) selalu berada di paling atas antrean penjadwalan,
   disusul kasus dengan hasil skrining DASS-21 kategori berat, lalu kasus yang
   paling lama menunggu.
2. **Konselor tetap ditentukan admin** - sistem hanya MENUSULKAN urutan kasus
   dan memeriksa bentrok jadwal; keputusan menugaskan konselor mana untuk slot
   mana tetap milik admin (tidak ada penugasan otomatis).
3. Waktu sesi memakai tanggal/jam menurut **WIB (Asia/Jakarta)** karena jadwal
   adalah kesepakatan lokal, bukan turunan timestamp UTC.

Kategori urgensi antrean:
- ``darurat`` : eskalasi krisis (status followup `perlu_ditinjau_segera`).
- ``tinggi``  : ada subskala DASS-21 kategori "Berat"/"Sangat Berat".
- ``normal``  : kasus lain yang belum punya sesi aktif.
"""
from datetime import date, datetime, time, timedelta, timezone

from app.models import Dass21Response, Followup, Registration, Schedule, ScheduleReminder
from app.services.dass21_scoring import classify_subscale
from app.services.crisis import CRISIS_CONFIG
from app.services.wa import normalize_wa

# Zona waktu tampilan & penjadwalan (WIB).
WIB = timezone(timedelta(hours=7))

STATUS_AKTIF_JADWAL = ("terjadwal", "ditunda")
STATUS_JADWAL = ("terjadwal", "selesai", "dibatalkan", "ditunda")
METODE_JADWAL = ("Tatap Muka", "Online", "Lainnya")

HARI_INDONESIA = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

NAMA_BULAN = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

URGENSI_URUT = {"darurat": 0, "tinggi": 1, "normal": 2}

# Pengingat sesi: H-1 hari (<= 24 jam sebelum sesi) dan H-1 jam (<= 60 menit).
JENIS_PENGINGAT = ("h1_hari", "h1_jam", "manual")
TARGET_PENGINGAT = ("mahasiswa", "petugas", "keduanya")
H1_HARI_MENIT = 24 * 60
H1_JAM_MENIT = 60


def wib_today() -> date:
    """Tanggal hari ini menurut WIB."""
    return datetime.now(WIB).date()


def monday_of(d: date) -> date:
    """Mengembalikan tanggal Senin pada minggu yang memuat `d` (minggu mulai Senin)."""
    return d - timedelta(days=d.weekday())


def parse_hhmm(value: str) -> int:
    """Validasi string "HH:MM" dan kembalikan menit sejak 00:00. ValueError bila salah."""
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("Format jam harus HH:MM, contoh: 09:30.")
    hh, mm = int(parts[0]), int(parts[1])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("Jam harus antara 00:00-23:59.")
    return hh * 60 + mm


def menit_ke_hhmm(total_menit: int) -> str:
    return f"{total_menit // 60:02d}:{total_menit % 60:02d}"


def _interval(jadwal: Schedule) -> tuple[int, int]:
    mulai = parse_hhmm(jadwal.jam_mulai)
    return mulai, mulai + int(jadwal.durasi_menit or 0)


def cari_bentrok(db, petugas_id: int, tanggal: date, jam_mulai: str,
                 durasi_menit: int, exclude_id: int | None = None):
    """Cari sesi AKTIF milik petugas yang bentrok waktu pada tanggal yang sama.

    Dua interval [a,b) dan [c,d) dianggap bertabrakan bila a < d dan c < b.
    Mengembalikan objek Schedule pertama yang bentrok, atau None.
    """
    mulai = parse_hhmm(jam_mulai)
    akhir = mulai + int(durasi_menit)
    rows = (
        db.query(Schedule)
        .filter(
            Schedule.petugas_id == petugas_id,
            Schedule.tanggal == tanggal,
            Schedule.status.in_(STATUS_AKTIF_JADWAL),
        )
        .all()
    )
    for s in rows:
        if exclude_id is not None and s.id == exclude_id:
            continue
        s_mulai, s_akhir = _interval(s)
        if mulai < s_akhir and s_mulai < akhir:
            return s
    return None


def kategori_terberat(dass: Dass21Response | None) -> str | None:
    """Kategori DASS-21 paling berat dari tiga subskala (atau None bila tidak skrining)."""
    if dass is None:
        return None
    urut = {"Normal": 0, "Ringan": 1, "Sedang": 2, "Berat": 3, "Sangat Berat": 4}
    kategori = [
        classify_subscale("depresi", dass.skor_depresi),
        classify_subscale("kecemasan", dass.skor_kecemasan),
        classify_subscale("stres", dass.skor_stres),
    ]
    return max(kategori, key=lambda k: urut.get(k, -1))


def hitung_urgensi(followup: Followup | None, dass: Dass21Response | None) -> tuple[str, str]:
    """Tentukan (kategori_urgensi, alasan) satu kasus untuk antrean penjadwalan."""
    status = followup.status if followup else "menunggu_ditinjau"
    if status == CRISIS_CONFIG["STATUS_ESKALASI"]:
        return "darurat", "Eskalasi krisis - wajib ditangani dan dijadwalkan paling awal."
    kategori = kategori_terberat(dass)
    if kategori in ("Berat", "Sangat Berat"):
        return "tinggi", f"Skrining DASS-21 kategori {kategori} - usulkan slot sebelum kasus normal."
    return "normal", "Menunggu penjadwalan sesi konseling."


def punya_sesi_aktif(db, registration_id: int) -> bool:
    """Benar bila kasus masih memiliki sesi terjadwal/ditunda yang belum selesai."""
    return (
        db.query(Schedule)
        .filter(
            Schedule.registration_id == registration_id,
            Schedule.status.in_(STATUS_AKTIF_JADWAL),
        )
        .count()
        > 0
    )


def antrean_penjadwalan(db, limit: int = 25) -> list[dict]:
    """Bangun antrean kasus yang perlu dijadwalkan, TERURUT PRIORITAS DARURAT.

    Kandidat antrean = semua pendaftaran yang:
    - tidak memiliki sesi aktif (terjadwal/ditunda), DAN
    - status tindak lanjut bukan `selesai`.

    Urutan: darurat (krisis) -> tinggi (DASS berat) -> normal; di dalam kelas yang
    sama, kasus yang lebih lama mendaftar didahulukan.
    """
    rows = (
        db.query(Registration, Followup, Dass21Response)
        .outerjoin(Followup, Followup.registration_id == Registration.id)
        .outerjoin(Dass21Response, Dass21Response.registration_id == Registration.id)
        .order_by(Registration.created_at.asc())
        .all()
    )
    items: list[dict] = []
    for reg, followup, dass in rows:
        if followup and followup.status == "selesai":
            continue
        if punya_sesi_aktif(db, reg.id):
            continue
        urgensi, alasan = hitung_urgensi(followup, dass)
        menunggu_hari = max(0, (datetime.now(WIB) - reg.created_at.replace(tzinfo=WIB)).days)
        petugas = followup.petugas if followup else None
        items.append({
            "registration_id": reg.id,
            "nama": reg.nama,
            "nim": reg.nim,
            "jenis_layanan": reg.jenis_layanan,
            "preferensi_hari": reg.preferensi_hari,
            "preferensi_waktu": reg.preferensi_waktu,
            "punya_keluhan": bool(reg.keluhan),
            "status": followup.status if followup else "menunggu_ditinjau",
            "petugas": (
                {"id": petugas.id, "nama": petugas.nama, "peran": petugas.peran}
                if petugas else None
            ),
            "kategori_dass": kategori_terberat(dass),
            "urgensi": urgensi,
            "alasan": alasan,
            "menunggu_hari": menunggu_hari,
            "created_at": reg.created_at,
        })
    items.sort(key=lambda x: (URGENSI_URUT[x["urgensi"]], -x["menunggu_hari"]))
    if limit and limit > 0:
        items = items[:limit]
    for it in items:
        it["created_at"] = it["created_at"].isoformat() + "Z"
    return items


def serialize_schedule(s: Schedule, followup_status: str | None = None,
                       urgensi: str | None = None) -> dict:
    """Serialisasi satu baris Schedule untuk respons API."""
    petugas = s.petugas
    mulai = parse_hhmm(s.jam_mulai)
    return {
        "id": s.id,
        "registration_id": s.registration_id,
        "nama": s.registration.nama if s.registration else None,
        "nim": s.registration.nim if s.registration else None,
        "jenis_layanan": s.registration.jenis_layanan if s.registration else None,
        "petugas": (
            {"id": petugas.id, "nama": petugas.nama, "peran": petugas.peran}
            if petugas else None
        ),
        "tanggal": s.tanggal.isoformat(),
        "hari": HARI_INDONESIA[s.tanggal.weekday()],
        "jam_mulai": s.jam_mulai,
        "jam_selesai": menit_ke_hhmm(mulai + int(s.durasi_menit or 0)),
        "durasi_menit": s.durasi_menit,
        "metode": s.metode,
        "lokasi": s.lokasi,
        "catatan": s.catatan,
        "status": s.status,
        "followup_status": followup_status,
        "urgensi": urgensi,
        "created_at": s.created_at.isoformat() + "Z",
        "updated_at": s.updated_at.isoformat() + "Z",
    }


# ------------------------------------------------------------ kalender bulanan
def month_grid_bounds(year: int, month: int) -> tuple[date, date]:
    """Batas grid kalender bulanan: Senin pertama pada/sebelum tanggal 1 dan
    Minggu terakhir pada/setelah akhir bulan (minggu mulai Senin)."""
    pertama = date(year, month, 1)
    if month == 12:
        akhir = date(year, 12, 31)
    else:
        akhir = date(year, month + 1, 1) - timedelta(days=1)
    return monday_of(pertama), akhir + timedelta(days=6 - akhir.weekday())


def week_rows(start: date, end: date) -> list[list[date]]:
    """Pecah rentang [start..end] menjadi minggu-minggu (7 hari, mulai Senin)."""
    minggu = []
    d = start
    while d <= end:
        minggu.append([d + timedelta(days=i) for i in range(7)])
        d += timedelta(days=7)
    return minggu


# ------------------------------------------------------------------ pengingat
def waktu_sesi_wib(s: Schedule) -> datetime:
    """Datetime mulai sesi menurut WIB (gabungan tanggal + jam_mulai)."""
    mulai = parse_hhmm(s.jam_mulai)
    return datetime.combine(
        s.tanggal,
        time(min(mulai // 60, 23), mulai % 60),
        tzinfo=WIB,
    )


def selisih_menit(s: Schedule, now: datetime | None = None) -> int:
    """Menit dari sekarang (WIB) sampai mulai sesi; negatif = sudah lewat."""
    now = now or datetime.now(WIB)
    return round((waktu_sesi_wib(s) - now).total_seconds() / 60)


def pengingat_jatuh_tempo(selisih: int) -> list[str]:
    """Jenis pengingat yang JATUH TEMPO untuk sesi dengan selisih menit tertentu.

    - h1_hari : sesi <= 24 jam lagi (masa H-1 hari).
    - h1_jam  : sesi <= 60 menit lagi (masa H-1 jam).
    Sesi yang sudah lewat (selisih <= 0) tidak lagi jatuh tempo.
    """
    due = []
    if 0 < selisih <= H1_HARI_MENIT:
        due.append("h1_hari")
    if 0 < selisih <= H1_JAM_MENIT:
        due.append("h1_jam")
    return due


def build_reminder_message(s: Schedule, penerima: str) -> str:
    """Teks pengingat WhatsApp untuk sesi konseling.

    Privasi: hanya memuat info jadwal (tanggal, jam, metode, lokasi, nama
    konselor) - TIDAK memuat keluhan, skor DASS-21, atau isi obrolan.
    """
    nama_mhs = s.registration.nama if s.registration else "-"
    nama_petugas = s.petugas.nama if s.petugas else "-"
    hari = HARI_INDONESIA[s.tanggal.weekday()]
    selesai = menit_ke_hhmm(parse_hhmm(s.jam_mulai) + int(s.durasi_menit or 0))
    if penerima == "mahasiswa":
        pembuka = f"Halo {nama_mhs}, pengingat sesi konseling Anda di UPA BK UTM:"
    else:
        pembuka = (
            f"Halo {nama_petugas}, pengingat sesi konseling yang Anda tangani "
            f"({nama_mhs}) di UPA BK UTM:"
        )
    baris_lokasi = f" - {s.lokasi}" if s.lokasi else ""
    return (
        f"{pembuka}\n"
        f"- Waktu: {hari}, {s.tanggal.strftime('%d/%m/%Y')} "
        f"pukul {s.jam_mulai}-{selesai} WIB\n"
        f"- Metode: {s.metode}{baris_lokasi}\n"
        f"- Konselor: {nama_petugas}\n"
        f"Mohon hadir tepat waktu. Bila berhalangan, segera hubungi UPA BK UTM "
        f"agar jadwal dapat disesuaikan. Terima kasih."
    )


def upcoming_sessions(db, days_ahead: int = 7) -> list[dict]:
    """Sesi AKTIF (terjadwal/ditunda) dalam `days_ahead` hari ke depan (WIB),
    lengkap dengan status pengingat (jatuh tempo & sudah terkirim) dan nomor
    WhatsApp tujuan yang valid untuk mahasiswa + konselor.

    Urutan: paling dekat waktu sesi paling atas.
    """
    today = wib_today()
    sampai = today + timedelta(days=days_ahead)
    now_wib = datetime.now(WIB)

    rows = (
        db.query(Schedule, Followup, Dass21Response)
        .outerjoin(Followup, Followup.registration_id == Schedule.registration_id)
        .outerjoin(Dass21Response, Dass21Response.registration_id == Schedule.registration_id)
        .filter(
            Schedule.tanggal >= today,
            Schedule.tanggal <= sampai,
            Schedule.status.in_(STATUS_AKTIF_JADWAL),
        )
        .order_by(Schedule.tanggal.asc(), Schedule.jam_mulai.asc())
        .all()
    )

    # Kumpulkan pengingat yang SUDAH terkirim per sesi (anti-duplikat).
    ids = [s.id for s, _, _ in rows]
    terkirim_map: dict[int, list[str]] = {}
    if ids:
        for r in (
            db.query(ScheduleReminder)
            .filter(
                ScheduleReminder.schedule_id.in_(ids),
                ScheduleReminder.status == "terkirim",
            )
            .all()
        ):
            terkirim_map.setdefault(r.schedule_id, []).append(r.jenis)

    items: list[dict] = []
    for sched, followup, dass in rows:
        urgensi, _ = hitung_urgensi(followup, dass)
        sel = selisih_menit(sched, now_wib)
        due = pengingat_jatuh_tempo(sel)
        sudah = sorted(set(terkirim_map.get(sched.id, [])))
        belum = [j for j in due if j not in sudah]
        reg = sched.registration
        petugas = sched.petugas
        delta_hari = (sched.tanggal - today).days
        tag = "Hari ini" if delta_hari == 0 else "Besok" if delta_hari == 1 else f"{delta_hari} hari lagi"
        items.append({
            **serialize_schedule(sched, followup.status if followup else None, urgensi),
            "hari_tag": tag,
            "selisih_menit": sel,
            "waktu_sesi_wib": waktu_sesi_wib(sched).isoformat(),
            "pengingat_due": belum,
            "pengingat_terkirim": sudah,
            "nomor_wa": {
                "mahasiswa": normalize_wa(reg.kontak) if reg else None,
                "petugas": normalize_wa(petugas.kontak) if petugas else None,
            },
        })
    return items
