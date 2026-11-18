# Contoh API - UPA BK UTM

Base URL lokal: `http://127.0.0.1:8000`
Dokumentasi interaktif: `/api/docs` (OpenAPI otomatis dari FastAPI).

Pemisahan akses:
- Endpoint mahasiswa: `/api/registrations`, `/api/dass21/*`, `/api/chat/*`
  (diverifikasi dengan `registration_id` + `chat_token` yang diterima saat daftar).
- Endpoint admin: `/api/admin/*` (kecuali `/login`) memerlukan header
  `Authorization: Bearer <access_token>`.

---

## 1. Opsi Form Pendaftaran

```bash
curl http://127.0.0.1:8000/api/registrations/options
```

```json
{
  "jenis_layanan": ["Konseling Individu", "Konseling Kelompok", "Konsultasi Karier", "Edukasi Kesehatan Mental", "Lainnya"],
  "hari": ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"],
  "waktu": ["Pagi (08.00-11.00)", "Siang (11.00-14.00)", "Sore (14.00-17.00)"]
}
```

## 2. Mendaftarkan Layanan

```bash
curl -X POST http://127.0.0.1:8000/api/registrations \
  -H "Content-Type: application/json" \
  -d '{
    "nama": "Mahasiswa Contoh",
    "nim": "2101101234",
    "kontak": "081234567890",
    "jenis_layanan": "Konseling Individu",
    "preferensi_hari": "Senin",
    "preferensi_waktu": "Pagi (08.00-11.00)",
    "keluhan": "Sering cemas menghadapi ujian.",
    "setuju_penggunaan_data": true
  }'
```

Respons `201 Created`:

```json
{
  "registration_id": 11,
  "chat_token": "c69f5ccd92f645b0d2b8e2372d68a5ad",
  "nama": "Mahasiswa Contoh",
  "pesan": "Pendaftaran berhasil. Preferensi jadwal Anda akan dikonfirmasi terpisah oleh petugas UPA BK - ini bukan jadwal terkonfirmasi.",
  "langkah_selanjutnya": "/dass21.html",
  "created_at": "2026-10-28T10:38:30.279367Z"
}
```

> Simpan `registration_id` + `chat_token` di sisi mahasiswa (frontend menyimpannya
> di `sessionStorage`). Tanpa `setuju_penggunaan_data: true` responsnya `422`.

## 3. Mengambil Pertanyaan DASS-21

```bash
curl http://127.0.0.1:8000/api/dass21/questions
```

```json
{
  "pengantar": "Pernyataan berikut berkaitan dengan cara Anda merasa dan berperilaku selama 7 hari terakhir. ...",
  "pertanyaan": [
    { "no": 1, "teks": "Saya merasa sulit untuk menjadi tenang (sulit rileks)." },
    { "no": 2, "teks": "Saya merasa mulut saya kering." }
  ],
  "opsi": [
    { "nilai": 0, "label": "Tidak sama sekali" },
    { "nilai": 1, "label": "Sedikit, atau sesekali" },
    { "nilai": 2, "label": "Sedang, atau sering" },
    { "nilai": 3, "label": "Sangat cocok, atau hampir selalu" }
  ]
}
```

## 4. Mengirim Jawaban Skrining

```bash
curl -X POST http://127.0.0.1:8000/api/dass21/submit \
  -H "Content-Type: application/json" \
  -d '{
    "registration_id": 11,
    "chat_token": "c69f5ccd92f645b0d2b8e2372d68a5ad",
    "jawaban": { "1": 0, "2": 1, "3": 2, "4": 0, "5": 1, "6": 0, "7": 1,
                 "8": 2, "9": 0, "10": 1, "11": 0, "12": 1, "13": 2, "14": 0,
                 "15": 1, "16": 0, "17": 2, "18": 1, "19": 0, "20": 1, "21": 0 }
  }'
```

Respons `200 OK` - **tanpa skor/kategori apa pun (kebijakan privasi mahasiswa):**

```json
{
  "status": "tersimpan",
  "pesan": "Terima kasih! Jawaban skrining Anda telah tersimpan dan akan ditinjau oleh petugas UPA BK. Sesuai kebijakan layanan, hasil tidak ditampilkan kepada mahasiswa.",
  "langkah_selanjutnya": "/chatbot.html"
}
```

Kesalahan umum:
- `422` - jawaban kurang dari 21 atau nilai di luar 0-3
  (`"Jawaban belum lengkap, nomor yang hilang: [14]"`).
- `403` - `chat_token` salah.
- `409` - skrining untuk pendaftaran itu sudah pernah dikirim.

## 5. Memulai Sesi Obrolan

```bash
curl -X POST http://127.0.0.1:8000/api/chat/start \
  -H "Content-Type: application/json" \
  -d '{ "registration_id": 11, "chat_token": "c69f5ccd92f645b0d2b8e2372d68a5ad" }'
```

```json
{
  "conversation_id": 4,
  "nama": "Mahasiswa Contoh",
  "pesan_pembuka": "Halo, Mahasiswa Contoh. Selamat datang di ruang obrolan UPA BK. ...",
  "disclaimer": "Asisten obrolan ini membantu mendengarkan dan memberi dukungan awal, namun BUKAN pengganti konseling profesional. ...",
  "riwayat": []
}
```

`403` bila skrining DASS-21 belum diisi (urutan layanan ditegakkan).

## 6. Mengirim Pesan Obrolan (normal)

```bash
curl -X POST http://127.0.0.1:8000/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "registration_id": 11,
    "chat_token": "c69f5ccd92f645b0d2b8e2372d68a5ad",
    "conversation_id": 4,
    "text": "Saya stres soal skripsi dan deadline tugas"
  }'
```

```json
{
  "reply": "Terdengar seperti tuntutan kuliah sedang mengambil banyak ruang di kepala Anda. Bagaimana pola tidur dan istirahat Anda selama menghadapi semua itu?",
  "conversation_id": 4,
  "eskalasi": false
}
```

## 7. Pesan Berindikasi Krisis (eskalasi otomatis)

```bash
curl -X POST http://127.0.0.1:8000/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{ "registration_id": 11, "chat_token": "...", "conversation_id": 4,
        "text": "kadang saya merasa ingin mengakhiri hidup" }'
```

```json
{
  "reply": "Terima kasih sudah berani menyampaikan hal yang berat ini. Keselamatan Anda adalah prioritas kami ... 1) ... hubungi 112 ... 119 ext. 8 ... 2) ... UPA BK UTM ... 3) ...",
  "conversation_id": 4,
  "eskalasi": true
}
```

Sistem otomatis: menyimpan catatan audit `sistem` berpenanda `[ESKALASI]` dan
mengubah status tindak lanjut menjadi `perlu_ditinjau_segera`
(konfigurasi `CRISIS_CONFIG` - perlu persetujuan UPA BK).

## 8. Riwayat Obrolan Mahasiswa

```bash
curl "http://127.0.0.1:8000/api/chat/history?registration_id=11&chat_token=c69f5ccd92f645b0d2b8e2372d68a5ad"
```

```json
{
  "conversation_id": 4,
  "riwayat": [
    { "sender": "mahasiswa", "text": "Saya stres soal skripsi...", "created_at": "2026-10-28T10:39:12.123456Z" },
    { "sender": "bot", "text": "Terdengar seperti tuntutan kuliah...", "created_at": "2026-10-28T10:39:12.234567Z" }
  ]
}
```

Pesan `sistem` (audit) sengaja tidak disertakan; hanya admin yang melihatnya.

## 9. Login Admin

```bash
curl -X POST http://127.0.0.1:8000/api/admin/login \
  -H "Content-Type: application/json" \
  -d '{ "username": "admin", "password": "admin123" }'
```

```json
{
  "access_token": "eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiIsImV4cCI6MTc5MzIxMjY5M30.PE79...",
  "token_type": "bearer",
  "username": "admin",
  "role": "admin"
}
```

`401` bila kredensial salah; `429` bila 5x gagal dalam 15 menit.

## 10. Statistik Dashboard

```bash
curl http://127.0.0.1:8000/api/admin/stats -H "Authorization: Bearer $TOKEN"
```

```json
{
  "total_registrasi": 10,
  "total_skrining_dass21": 10,
  "total_percakapan": 3,
  "total_pesan": 14,
  "perlu_ditinjau_segera": 1,
  "eskalasi_otomatis": 1,
  "per_status": { "menunggu_ditinjau": 4, "sedang_diproses": 2, "dijadwalkan": 1, "selesai": 2, "perlu_ditinjau_segera": 1 },
  "per_jenis_layanan": { "Konseling Individu": 5, "Konseling Kelompok": 2, "Konsultasi Karier": 2, "Edukasi Kesehatan Mental": 1 }
}
```

## 11. Daftar Pendaftar (filter + urutan prioritas)

```bash
curl "http://127.0.0.1:8000/api/admin/registrations?sort=priority&status=menunggu_ditinjau&search=2101&date_from=2026-10-01&date_to=2026-10-31&page=1&per_page=20" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "total": 10, "page": 1, "per_page": 20,
  "items": [
    {
      "id": 5, "nama": "Eka Putri Ramadhani", "nim": "2101101005",
      "kontak": "eka.putri@mail.contoh.ac.id",
      "jenis_layanan": "Konseling Individu",
      "preferensi_hari": "Senin", "preferensi_waktu": "Siang (11.00-14.00)",
      "punya_keluhan": true,
      "status": "perlu_ditinjau_segera", "status_label": "Perlu Ditinjau Segera",
      "skor_depresi": 32, "skor_kecemasan": 30, "skor_stres": 42,
      "sudah_skrining": true,
      "created_at": "2026-10-15T02:37:53.412245Z"
    }
  ]
}
```

Urutan `sort=priority`: `perlu_ditinjau_segera` -> `menunggu_ditinjau` ->
`sedang_diproses` -> `dijadwalkan` -> `selesai`, lalu paling lama di atas.

## 12. Detail Satu Pendaftar

```bash
curl http://127.0.0.1:8000/api/admin/registrations/5 -H "Authorization: Bearer $TOKEN"
```

```json
{
  "id": 5, "nama": "...", "nim": "...", "kontak": "...",
  "jenis_layanan": "Konseling Individu",
  "keluhan": "Tidak bisa tidur nyenyak, sering terbangun karena pikiran berat.",
  "consent_status": "disetujui",
  "dass21": {
    "submitted_at": "2026-10-15T03:12:00.000000Z",
    "scoring_version": "DASS21-ID-STD-1.0",
    "skor": { "depresi": 32, "kecemasan": 30, "stres": 42 },
    "kategori_umum": { "depresi": "Sangat Berat", "kecemasan": "Sangat Berat", "stres": "Sangat Berat" },
    "catatan_kategori": "Kategori umum berdasarkan cut-off publikasi DASS-21 (Lovibond & Lovibond, 1995). Bukan kategori resmi UPA BK, bukan diagnosis, dan tidak ditampilkan kepada mahasiswa.",
    "jawaban": { "1": 3, "2": 3, "3": 3 }
  },
  "conversations": [
    { "id": 2, "created_at": "...", "messages": [
      { "sender": "mahasiswa", "text": "...", "created_at": "..." },
      { "sender": "bot", "text": "...", "created_at": "..." },
      { "sender": "sistem", "text": "[ESKALASI] ...", "created_at": "..." }
    ]}
  ],
  "followup": { "status": "perlu_ditinjau_segera", "status_label": "Perlu Ditinjau Segera",
                "catatan_petugas": "[OTOMATIS] ...", "assigned_admin": "admin", "updated_at": "..." },
  "meta_akses": "Data sensitif ... hanya untuk petugas berwenang. ..."
}
```

## 13. Memperbarui Tindak Lanjut

```bash
curl -X PATCH http://127.0.0.1:8000/api/admin/registrations/5/followup \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "status": "dijadwalkan", "catatan_petugas": "Sesi pertama dijadwalkan Senin pagi." }'
```

```json
{
  "status": "dijadwalkan",
  "status_label": "Dijadwalkan",
  "catatan_petugas": "Sesi pertama dijadwalkan Senin pagi.",
  "assigned_admin": "admin",
  "updated_at": "2026-10-28T10:45:00.000000Z"
}
```

Status yang valid: `menunggu_ditinjau`, `sedang_diproses`, `dijadwalkan`,
`selesai`, `perlu_ditinjau_segera`. `assigned_admin` diisi otomatis dari petugas
yang menyimpan.

## 14. Ekspor CSV

```bash
# Versi standar (tanpa keluhan & skor):
curl -OJ "http://127.0.0.1:8000/api/admin/export/registrations.csv" \
  -H "Authorization: Bearer $TOKEN"

# Versi sensitif (keluhan + skor DASS-21) - wajib sadar, dicatat log audit:
curl -OJ "http://127.0.0.1:8000/api/admin/export/registrations.csv?include_sensitive=true" \
  -H "Authorization: Bearer $TOKEN"
```

Baris header versi standar:
`id,tanggal_daftar,nama,nim,kontak,jenis_layanan,preferensi_hari,preferensi_waktu,status,petugas_penangani,catatan_petugas`

## 15. Kelola Petugas Penangani

Direktori staf/konselor yang dapat ditugaskan sebagai penanggung jawab kasus
(bukan akun login):

```bash
# Daftar petugas + jumlah kasus yang ditanggung:
curl http://127.0.0.1:8000/api/admin/petugas -H "Authorization: Bearer $TOKEN"

# Tambah petugas:
curl -X POST http://127.0.0.1:8000/api/admin/petugas \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "nama": "Ratna Wulandari, M.Psi", "peran": "Psikolog Klinis", "kontak": "ratna@kampus.ac.id" }'

# Ganti nama / nonaktifkan:
curl -X PATCH http://127.0.0.1:8000/api/admin/petugas/1 \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "aktif": false }'

# Hapus (penugasan pada kasus otomatis dilepas, kasus tidak ikut terhapus):
curl -X DELETE http://127.0.0.1:8000/api/admin/petugas/1 -H "Authorization: Bearer $TOKEN"
```

## 16. Menugaskan Petugas Penangani pada Satu Kasus

```bash
# Tetapkan penanggung jawab:
curl -X PUT http://127.0.0.1:8000/api/admin/registrations/1/assign \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "petugas_id": 1 }'

# Lepas penugasan:
curl -X PUT http://127.0.0.1:8000/api/admin/registrations/1/assign \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "petugas_id": null }'
```

Filter daftar pendaftar per penugasan:
`GET /api/admin/registrations?assigned=ya` (sudah ada penangani),
`?assigned=tidak` (belum ada), atau `?assigned=ya&petugas_id=1` (milik petugas tertentu).

## 17. Analisis AI Terpadu (keluhan + DASS-21 + obrolan)

Analisis on-demand per kasus, khusus admin. Mengikuti gerbang privasi LLM
(`LLM_ALLOW_EXTERNAL=false` -> penyedia mock, tidak ada data keluar).
Hasil BUKAN diagnosis dan tidak pernah ditampilkan ke mahasiswa.

```bash
curl -X POST http://127.0.0.1:8000/api/admin/registrations/1/analysis \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "registration_id": 1,
  "penyedia": "mock",
  "dibuat_pada": "2026-10-31T11:05:00.000000Z",
  "analisis": {
    "ringkasan": "Mahasiswa mendaftar untuk Konsultasi Karier dengan keluhan yang tampak pada keluhan tertulis maupun obrolan chatbox. Tema yang menonjol: tekanan akademik, kecemasan.",
    "tema": ["tekanan akademik", "kecemasan"],
    "tingkat_perhatian": "tinggi",
    "kaitan_dass21": "Skrining DASS-21 menunjukkan kategori umum: depresi Ringan, kecemasan Sangat Berat, stres Ringan (cut-off publikasi, bukan diagnosis).",
    "saran_tindak_lanjut": [
      "Tinjau kasus segera; verifikasi indikasi krisis dan jadwalkan kontak awal.",
      "Konfirmasi preferensi jadwal dan tetapkan petugas penangani."
    ],
    "sumber": "llm"
  },
  "disclaimer": "Analisis ini adalah ringkasan otomatis berbantuan AI ... BUKAN diagnosis ..."
}
```

Catatan: `tingkat_perhatian` otomatis "tinggi" bila ada kategori DASS-21
Berat/Sangat Berat atau indikasi krisis. Bila penyedia LLM gagal, respons tetap
terstruktur dengan `"sumber": "fallback"`.

## 18. Ganti Password Admin

```bash
curl -X PATCH http://127.0.0.1:8000/api/admin/password \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "password_lama": "admin123", "password_baru": "sandiBaruAman456" }'
```

```json
{ "status": "ok", "pesan": "Password berhasil diperbarui." }
```

## 19. Cek Kesehatan

```bash
curl http://127.0.0.1:8000/api/health
# {"status":"ok","app":"UPA BK UTM - Layanan Konseling Mahasiswa","versi":"0.1.0"}
```

## 20. Antrean Prioritas Penjadwalan

Kasus yang perlu dijadwalkan, TERURUT: `darurat` (eskalasi krisis) paling atas,
disusul `tinggi` (DASS-21 kategori Berat/Sangat Berat), lalu `normal` (paling
lama menunggu didahulukan). Kasus yang sudah punya sesi aktif atau sudah selesai
tidak ditampilkan. Sistem hanya mengurutkan - konselor tetap dipilih admin.

```bash
curl http://127.0.0.1:8000/api/admin/schedule/queue -H "Authorization: Bearer $TOKEN"
```

```json
{
  "total": 3,
  "ringkasan": {"darurat": 1, "tinggi": 1, "normal": 1},
  "items": [
    {
      "registration_id": 15,
      "nama": "Eka Krisis",
      "nim": "2101101005",
      "jenis_layanan": "Konseling Individu",
      "preferensi_hari": "Senin",
      "preferensi_waktu": "Siang (11.00-14.00)",
      "status": "perlu_ditinjau_segera",
      "petugas": null,
      "kategori_dass": "Sangat Berat",
      "urgensi": "darurat",
      "alasan": "Eskalasi krisis - wajib ditangani dan dijadwalkan paling awal.",
      "menunggu_hari": 2,
      "created_at": "2026-11-16T09:10:00Z"
    }
  ],
  "meta": "Kasus eskalasi krisis selalu di atas. ..."
}
```

## 21. Melihat Jadwal Mingguan (kalender Senin-Minggu, WIB)

```bash
# minggu berjalan
curl http://127.0.0.1:8000/api/admin/schedule/week -H "Authorization: Bearer $TOKEN"

# minggu tertentu + filter konselor (start boleh hari apa pun; dinormalkan ke Senin)
curl "http://127.0.0.1:8000/api/admin/schedule/week?start=2026-11-19&petugas_id=2" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "start": "2026-11-16",
  "end": "2026-11-22",
  "hari_ini": "2026-11-18",
  "total": 1,
  "total_darurat": 1,
  "days": [
    {
      "tanggal": "2026-11-19",
      "hari": "Kamis",
      "is_today": false,
      "items": [
        {
          "id": 1,
          "registration_id": 15,
          "nama": "Eka Krisis",
          "nim": "2101101005",
          "petugas": {"id": 2, "nama": "Andi Prasetyo, M.Psi", "peran": "Konselor Senior"},
          "tanggal": "2026-11-19",
          "hari": "Kamis",
          "jam_mulai": "09:00",
          "jam_selesai": "10:00",
          "durasi_menit": 60,
          "metode": "Tatap Muka",
          "lokasi": "Ruang BK 1",
          "catatan": "Sesi darurat pasca-eskalasi otomatis.",
          "status": "terjadwal",
          "followup_status": "perlu_ditinjau_segera",
          "urgensi": "darurat"
        }
      ]
    }
  ]
}
```

## 22. Membuat Sesi Konseling (jadwal final)

Konselor WAJIB dipilih admin; konselor nonaktif ditolak; tanggal tidak boleh di
masa lalu (WIB); sesi konselor yang sama tidak boleh tumpang tindih (`409`).
Kasus `menunggu_ditinjau`/`sedang_diproses` otomatis menjadi `dijadwalkan`;
status krisis `perlu_ditinjau_segera` dipertahankan.

```bash
curl -X POST http://127.0.0.1:8000/api/admin/schedule \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "registration_id": 15,
    "petugas_id": 2,
    "tanggal": "2026-11-19",
    "jam_mulai": "09:00",
    "durasi_menit": 60,
    "metode": "Tatap Muka",
    "lokasi": "Ruang BK 1",
    "catatan": "Sesi darurat - prioritaskan."
  }'
```

Respons `201 Created` memuat jadwal lengkap seperti contoh pada nomor 21.
Pembatalan yang perlu tercatat: `PATCH /api/admin/schedule/{id}` dengan
`{"status": "dibatalkan"}`; opsi status: `terjadwal`, `selesai`, `dibatalkan`,
`ditunda`. Menggeser jadwal (tanggal/jam/konselor/durasi/metode/lokasi/catatan)
juga lewat PATCH dan tetap diperiksa bentroknya. Hapus permanen (salah input):
`DELETE /api/admin/schedule/{id}`.


## 23. Melihat Jadwal Bulanan (grid kalender seperti kalender umum, WIB)

Grid 5-6 minggu mulai Senin; hari di luar bulan tetap ikut (`in_month: false`)
agar tampilan utuh seperti kalender dinding. Navigasi antarbulan lewat parameter
`month` (format `YYYY-MM`).

```bash
# bulan berjalan
curl http://127.0.0.1:8000/api/admin/schedule/month -H "Authorization: Bearer $TOKEN"

# bulan tertentu + filter konselor
curl "http://127.0.0.1:8000/api/admin/schedule/month?month=2026-11&petugas_id=2" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "month": "2026-11",
  "label": "November 2026",
  "start": "2026-10-26",
  "end": "2026-12-06",
  "hari_ini": "2026-11-18",
  "total": 4,
  "total_darurat": 1,
  "weeks": [
    {
      "days": [
        {
          "tanggal": "2026-11-18",
          "hari": "Rabu",
          "is_today": true,
          "in_month": true,
          "items": [
            {
              "id": 1,
              "registration_id": 5,
              "nama": "Eka Putri Ramadhani",
              "nim": "2101101005",
              "petugas": {"id": 1, "nama": "Dra. Ratna Wulandari, M.Psi", "peran": "Konselor Senior"},
              "tanggal": "2026-11-19",
              "hari": "Kamis",
              "jam_mulai": "09:00",
              "jam_selesai": "10:00",
              "metode": "Tatap Muka",
              "lokasi": "Ruang BK 1",
              "status": "terjadwal",
              "urgensi": "darurat"
            }
          ]
        }
      ]
    }
  ]
}
```

## 24. Daftar Pengingat (badge lonceng dashboard)

Sesi AKTIF (terjadwal/ditunda) dalam N hari ke depan beserta status pengingat:

- `pengingat_due`      : pengingat yang JATUH TEMPO tapi BELUM terkirim -
  `h1_hari` bila sesi <= 24 jam lagi, `h1_jam` bila <= 60 menit lagi.
  Dipakai dashboard untuk badge lonceng + notifikasi browser otomatis (H-1 jam).
- `pengingat_terkirim` : pengingat yang sudah berhasil dikirim (anti-duplikat).
- `nomor_wa`           : nomor tujuan valid `62...`; `null` bila kontak
  mahasiswa/konselor berupa email atau kosong (WA tidak bisa dikirim).

```bash
curl "http://127.0.0.1:8000/api/admin/schedule/reminders?days=7" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "hari_ini": "2026-11-18",
  "days_ahead": 7,
  "total": 4,
  "total_due": 1,
  "items": [
    {
      "id": 1,
      "registration_id": 5,
      "nama": "Eka Putri Ramadhani",
      "nim": "2101101005",
      "tanggal": "2026-11-19",
      "hari": "Kamis",
      "jam_mulai": "09:00",
      "jam_selesai": "10:00",
      "metode": "Tatap Muka",
      "lokasi": "Ruang BK 1",
      "status": "terjadwal",
      "urgensi": "darurat",
      "hari_tag": "Besok",
      "selisih_menit": 1116,
      "waktu_sesi_wib": "2026-11-19T09:00:00+07:00",
      "pengingat_due": ["h1_hari"],
      "pengingat_terkirim": [],
      "nomor_wa": {"mahasiswa": "6281298765432", "petugas": "6281234567890"}
    }
  ],
  "meta": "Pengingat H-1 hari jatuh tempo <= 24 jam sebelum sesi; H-1 jam <= 60 menit. ..."
}
```

## 25. Mengirim Pengingat WhatsApp untuk Satu Sesi

Kirim manual oleh admin ke mahasiswa dan/atau konselor. Setiap percobaan
dicatat pada tabel `schedule_reminders` (audit + anti-duplikat). Isi pesan
hanya info jadwal (tanggal, jam, metode, lokasi, nama konselor) - TANPA
keluhan/skor/obrolan. Pada `WA_PROVIDER=mock` pesan hanya dicatat di log
server (mode demo); set `WA_PROVIDER=fonnte` + `WA_API_TOKEN` untuk kirim nyata.

```bash
# target: keduanya (default) | mahasiswa | petugas
# jenis : manual (default) | h1_hari | h1_jam
curl -X POST http://127.0.0.1:8000/api/admin/schedule/1/remind \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"target": "keduanya", "jenis": "h1_hari"}'
```

```json
{
  "status": "ok",
  "schedule_id": 1,
  "hasil": [
    {"target": "mahasiswa", "status": "terkirim", "nomor": "6281298765432", "keterangan": null},
    {"target": "petugas", "status": "terkirim", "nomor": "6281234567890", "keterangan": null}
  ],
  "meta": "Pada WA_PROVIDER=mock pesan hanya dicatat di log server (mode demo). ..."
}
```

Gagal yang mungkin: `404` jadwal tidak ada; `422` target/jenis tidak dikenal,
sesi bukan `terjadwal`/`ditunda`, atau waktu sesi sudah berlalu. Kontak
email/kosong TIDAK dihitung gagal kirim jaringan, tetapi dicatat per target
dengan keterangan "Kontak kosong atau bukan nomor WhatsApp" agar admin tahu
nomor WA perlu dilengkapi.
