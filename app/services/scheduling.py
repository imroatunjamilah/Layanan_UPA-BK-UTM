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
from datetime import date, datetime, timedelta, timezone

from app.models import Dass21Response, Followup, Registration, Schedule
from app.services.dass21_scoring import classify_subscale
from app.services.crisis import CRISIS_CONFIG

# Zona waktu tampilan & penjadwalan (WIB).
WIB = timezone(timedelta(hours=7))

STATUS_AKTIF_JADWAL = ("terjadwal", "ditunda")
STATUS_JADWAL = ("terjadwal", "selesai", "dibatalkan", "ditunda")
METODE_JADWAL = ("Tatap Muka", "Online", "Lainnya")

HARI_INDONESIA = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

URGENSI_URUT = {"darurat": 0, "tinggi": 1, "normal": 2}


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
