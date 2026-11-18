---
title: Layanan UPA BK UTM
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Aplikasi Web Layanan Konseling UPA BK UTM

Aplikasi web **UPA BK UTM** (Unit Pelaksana Aktivitas Bimbingan Konseling,
Universitas Trunojoyo Madura) berbasis LLM dengan database terintegrasi:
pendaftaran layanan mandiri mahasiswa, skrining DASS-21, chatbot dukungan
awal, dan dashboard admin untuk petugas.

> **STATUS: PROTOTIPE PENGEMBANGAN.** Semua data adalah fiktif. Kebijakan
> krisis, kategori risiko, dan kontak resmi WAJIB disetujui UPA BK sebelum
> dipakai nyata. Lihat `docs/prototype-limitations.md`.

---

## Fitur Utama

**Mahasiswa (tanpa akun):**
1. **Pendaftaran** - data diri, jenis layanan, preferensi hari/waktu (preferensi
   awal, bukan jadwal final), keluhan opsional, persetujuan penggunaan data.
2. **Skrining DASS-21** - 21 pernyataan standar, penilaian otomatis 3 subskala
   (depresi, kecemasan, stres). **Skor tidak pernah ditampilkan ke mahasiswa** -
   hanya ditinjau petugas.
3. **Ruang Obrolan** - chatbot empatik Bahasa Indonesia (disclaimer "bukan
   pengganti konseling profesional"), deteksi krisis independent dari LLM,
   permintaan pendampingan manusia dicatat tanpa janji respons langsung.

**Admin/Petugas:**
- Login aman (PBKDF2 + token sesi, rate limit percobaan gagal).
- **Manajemen akun admin**: admin menentukan siapa saja yang boleh login -
  membuat akun baru dengan profil wajib (nama lengkap, NIM, fakultas, nomor
  WhatsApp), mengaktifkan/menonaktifkan akun, mengedit profil, mereset sandi
  akun lain, dan menghapus akun. Akun nonaktif/kedaluwarsa langsung tidak bisa
  masuk (sesi yang sedang berjalan pun hangus).
- **Masa aktif akun**: tiap akun admin dapat diberi batas tanggal berlaku
  (kosong = selamanya). Setelah tanggal tersebut login otomatis ditolak dengan
  pesan jelas, dan dashboard menandai akun sebagai "Kedaluwarsa".
- **Reset kata sandi mandiri via OTP WhatsApp**: tautan "Lupa kata sandi?" di
  halaman login mengirim kode 6 digit ke nomor WhatsApp terdaftar (hash
  SHA-256, berlaku 10 menit, maks. 5 percobaan, jeda kirim ulang 60 detik).
- Statistik agregat (pendaftaran, skrining, obrolan, eskalasi).
- Daftar mahasiswa: pencarian nama/NIM, filter status/layanan/tanggal,
  **urutan antrean prioritas** (eskalasi krisis paling atas).
- **Jadwal konseling kalender (mingguan & bulanan)**: dua tampilan kalender
  waktu WIB - grid mingguan Senin-Minggu dan **grid bulanan seperti kalender
  umum** (5-6 minggu, navigasi bulan lalu/ini/depan, hari luar bulan redup,
  legenda warna). Klik sesi untuk membuka detail kasus; filter per konselor
  berlaku di kedua tampilan. Berbeda dengan preferensi awal mahasiswa, jadwal
  di sini adalah keputusan final petugas.
- **Pengingat sesi (reminder)**: sesi dalam masa H-1 hari (≤ 24 jam) dan
  H-1 jam (≤ 60 menit) otomatis ditandai pada **lonceng Pengingat** di header
  dashboard (badge jumlah yang perlu ditindaklanjuti), lengkap dengan
  **notifikasi browser otomatis** untuk masa H-1 jam. Admin dapat mengirim
  **pengingat WhatsApp** manual ke mahasiswa dan/atau konselor (isi pesan hanya
  info jadwal - tanpa data sensitif); setiap pengiriman tercatat pada tabel
  audit `schedule_reminders` sehingga tidak ada pengiriman ganda. Kontak email
  dinonaktifkan dengan pesan jelas agar nomor WA dilengkapi.
- **Antrean penjadwalan prioritas darurat**: kasus eskalasi krisis otomatis tampil
  paling atas, disusul kasus dengan skrining DASS-21 kategori Berat/Sangat Berat,
  lalu yang paling lama menunggu. Sistem hanya MENUSULKAN dan memeriksa bentrok
  jadwal - pemilihan konselor dan slot tetap ditentukan admin (tidak ada
  penugasan otomatis). Sesi konselor yang sama tidak boleh tumpang tindih;
  kasus krisis yang dijadwalkan tetap membawa penanda darurat sampai
  diselesaikan petugas secara sadar.
- Detail lengkap: pendaftaran, jawaban + skor + kategori DASS-21 (dengan
  disclaimer), keluhan, riwayat obrolan (termasuk catatan audit sistem).
- Kelola tindak lanjut: 5 status (`menunggu_ditinjau`, `sedang_diproses`,
  `dijadwalkan`, `selesai`, `perlu_ditinjau_segera`), catatan petugas, penugasan.
- **Petugas penangani**: admin mengelola direktori staf/konselor (tambah, ganti
  nama, nonaktifkan, hapus) dan **menugaskan penanggung jawab** pada tiap kasus;
  ada filter kasus per petugas, statistik beban kasus per petugas, dan kolom
  petugas pada ekspor CSV.
- **Analisis AI terpadu (khusus admin)**: satu tombol di detail kasus yang
  menggabungkan keluhan tertulis + hasil DASS-21 + isi obrolan chatbox menjadi
  ringkasan terpadu (tema, tingkat perhatian, kaitan DASS-21, saran tindak
  lanjut). Mengikuti gerbang privasi LLM yang sama dengan chatbot (default:
  mock, tidak ada data keluar) dan **bukan diagnosis**.
- Ekspor CSV terbatas: versi standar tanpa data sensitif; versi sensitif
  (keluhan + skor) memerlukan konfirmasi dan dicatat log audit.

**Teknologi:** Python 3.10+, FastAPI, SQLAlchemy 2, SQLite (siap migrasi
PostgreSQL), Pydantic v2, pytest, frontend HTML/CSS/JS statis (Bahasa Indonesia).

---

## Struktur Proyek

```
upa-bk-utm/
├── run.py                    # Menjalankan server (uvicorn)
├── init_db.py                # Membuat tabel database (idempoten)
├── seed_data.py              # Mengisi data dummy pengembangan (10 mahasiswa + 3 petugas fiktif)
├── create_admin.py           # Membuat/mengganti akun admin
├── requirements.txt          # Dependensi runtime (untuk MENJALANKAN aplikasi)
├── requirements-dev.txt      # Dependensi tambahan (hanya untuk pytest/test)
├── pytest.ini                # Konfigurasi pengujian
├── .env.example              # Contoh konfigurasi (salin jadi .env)
├── app/
│   ├── main.py               # Aplikasi FastAPI + frontend statis
│   ├── config.py             # Pengaturan dari environment
│   ├── database.py           # Engine & sesi SQLAlchemy
│   ├── models.py             # 9 tabel: users, petugas, registrations,
│   │                         #   dass21_responses, conversations, messages,
│   │                         #   followups, schedules, schedule_reminders
│   ├── security.py           # Hash password PBKDF2, token sesi HMAC, chat token
│   ├── utils.py
│   ├── routers/
│   │   ├── registrations.py  # POST /api/registrations, GET options
│   │   ├── dass21.py         # GET questions, POST submit (tanpa skor ke mahasiswa)
│   │   ├── chat.py           # start/message/history + lapisan keselamatan
│   │   ├── admin.py          # login, stats, list, detail, followup, petugas,
│   │   │                     #   penugasan penangani, jadwal mingguan & bulanan,
│   │   │                     #   pengingat sesi (WA), export CSV
│   │   └── deps.py           # RBAC get_current_admin
│   ├── services/
│   │   ├── dass21_questions.py  # 21 pernyataan (terjemahan kerja - validasi UPA BK)
│   │   ├── dass21_scoring.py    # Penilaian baku x2 + cut-off + versi penilaian
│   │   ├── crisis.py            # Kata kunci krisis/handoff + pesan keamanan (konfigurasi)
│   │   ├── scheduling.py        # Antrean prioritas penjadwalan + deteksi bentrok
│   │   │                        #   + kalender bulanan + pengingat (WIB)
│   │   ├── options.py
│   │   └── llm/
│   │       ├── base.py           # Antarmuka penyedia + jenis error
│   │       ├── mock_provider.py  # Penyedia simulasi offline (default, tanpa biaya)
│   │       ├── openai_compat.py  # Penyedia kompatibel OpenAI (timeout/auth/429)
│   │       └── manager.py        # Pemilihan penyedia + fallback aman
│   └── prompts/
│       └── chatbot_system_prompt.md  # System prompt TERPISAH dari frontend
├── frontend/                 # UI Bahasa Indonesia
│   ├── index.html, registrasi.html, dass21.html, chatbot.html
│   ├── admin-login.html, admin-dashboard.html
│   ├── css/style.css
│   └── js/  (registrasi.js, dass21.js, chatbot.js, admin.js)
├── tests/                    # 119 tes pytest
│   ├── conftest.py
│   ├── test_auth.py              # login, token, ganti password, rate limit
│   ├── test_registrations.py     # validasi + penyimpanan pendaftaran
│   ├── test_dass21_scoring.py    # unit penilaian DASS-21
│   ├── test_dass21_api.py        # submit + anti-kebocoran skor
│   ├── test_chatbot.py           # obrolan, krisis, handoff, penyedia LLM
│   ├── test_admin_access.py      # RBAC, filter, prioritas, ekspor
│   ├── test_petugas.py           # kelola petugas + penugasan penangani
│   ├── test_schedule.py          # kalender mingguan & bulanan, antrean darurat,
│   │                             #   bentrok, pengingat (due/terkirim/WA), RBAC
│   ├── test_analysis.py          # analisis kasus terpadu (LLM)
│   └── test_models_storage.py    # FK, unik, cascade, indeks
└── docs/
    ├── api_examples.md           # Contoh request/response tiap endpoint
    └── prototype-limitations.md  # Batasan prototipe + checklist pra-produksi
```

---

## Cara Menjalankan (Lokal)

### 1. Prasyarat
- Python **3.10+** (diuji pada 3.12)
- pip

### 2. Instal dependensi
```bash
cd upa-bk-utm
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

> `requirements.txt` hanya berisi dependensi **runtime** — cukup untuk
> menjalankan aplikasi. **pytest TIDAK diperlukan untuk menjalankan
> aplikasi.** pytest hanya dipakai untuk test suite; untuk mengujinya
> install terpisah: `pip install -r requirements-dev.txt`.

#### Jika gagal download paket (mis. pytest)

Tanda umum: `WARNING: Retrying ...` / `Could not find a version that
satisfies the requirement` / instalasi berhenti di tengah. Langkah urut:

1. **Pastikan Python & pip sesuai** (pytest 8 butuh Python >= 3.8):
   ```bash
   python --version
   python -m pip install --upgrade pip
   ```
   Selalu gunakan `python -m pip ...` agar pip sama dengan interpreter
   `python` yang dipakai.
2. **Masalah jaringan/proxy (umum di jaringan kampus):**
   ```bash
   python -m pip install -r requirements.txt --proxy http://user:pass@proxy:port
   # atau coba mirror publik lain:
   python -m pip install -r requirements.txt -i https://pypi.org/simple
   ```
3. **Cache pip korup** -> ulangi dengan `--no-cache-dir`.
4. **Tetap gagal hanya di pytest?** Abaikan dulu dan jalankan aplikasi:
   aplikasi TIDAK butuh pytest. Test bisa dijalankan nanti di komputer/
   jaringan lain.

### 3. Konfigurasi (opsional saat pengembangan)
```bash
cp .env.example .env      # Windows: copy .env.example .env
```
Untuk pengembangan, nilai bawaan sudah cukup. Untuk produksi **wajib** mengganti
`SECRET_KEY` (mis. `python -c "import secrets; print(secrets.token_urlsafe(48))"`).

### 4. Buat database + data dummy
```bash
python init_db.py        # membuat tabel + migrasi ringan (dilakukan juga otomatis saat startup)
python seed_data.py      # mengisi 10 mahasiswa + 3 petugas fiktif + admin pengembangan
```

### 5. Jalankan server
```bash
python run.py
# atau: uvicorn app.main:app --reload
```
Buka:
- **Aplikasi mahasiswa** : http://127.0.0.1:8000/
- **Dashboard admin**    : http://127.0.0.1:8000/admin-login.html
- **Dokumentasi API**    : http://127.0.0.1:8000/api/docs

### 6. Akun admin pengembangan
- Username: `admin`
- Password: `admin123`

**Cara mengganti kredensial** (pilih salah satu):
1. Halaman admin -> profil -> ubah password (endpoint `PATCH /api/admin/password`);
2. CLI: `python create_admin.py <username> <password-baru>`;
3. Seed ulang dengan env baru: ubah `ADMIN_USERNAME`/`ADMIN_PASSWORD` di `.env`
   lalu hapus `upabk.db` dan jalankan ulang `python init_db.py && python seed_data.py`.

> Akun ini dibuat otomatis saat startup di mode `development` bila tabel users kosong.
> Password tersimpan sebagai hash PBKDF2-SHA256 (390.000 iterasi), tidak pernah plain.

### 7. Jalankan pengujian (opsional, butuh pytest)
```bash
pip install -r requirements-dev.txt   # sekali saja: menambah pytest
pytest            # 119 tes: auth, registrasi, scoring DASS-21, DB, akses admin, chatbot, petugas, penjadwalan + kalender + pengingat, analisis
```
Jika pytest gagal terpasang di jaringanmu, aplikasi tetap dapat dijalankan
normal tanpa langkah ini.

---

## Mengaktifkan LLM Nyata

Default memakai **penyedia mock** (offline, tanpa biaya) sehingga seluruh alur
dapat diuji tanpa API key. Untuk memakai API kompatibel OpenAI:

1. Di `.env`:
   ```
   LLM_PROVIDER=openai_compatible
   LLM_BASE_URL=https://api.openai.com/v1     # atau penyedia/Ollama lain
   LLM_MODEL=gpt-4o-mini
   LLM_API_KEY=sk-...
   LLM_ALLOW_EXTERNAL=true
   ```
2. `LLM_ALLOW_EXTERNAL=false` (default) adalah **pengaman privasi**: data
   obrolan TIDAK akan dikirim keluar meski API key terisi (sistem otomatis
   memakai mock). Aktifkan hanya setelah **review privasi & persetujuan UPA BK**,
   karena data kesehatan mental tidak boleh dikirim ke layanan eksternal tanpa
   dasar hukum/konsentrasi persetujuan yang memadai.
3. Error (timeout, API key salah, rate limit 429, koneksi gagal) ditangani
   dengan rapi: pengguna menerima pesan pelayanan sopan, detail teknis ke log.
4. Menambah model lokal: buat kelas turunan `LLMProvider` di
   `app/services/llm/` lalu daftarkan di `manager.get_provider()`.

## Mengubah System Prompt Chatbot

Edit file `app/prompts/chatbot_system_prompt.md` (terpisah dari kode frontend,
sesuai kebutuhan). Perubahan berlaku tanpa mengubah kode.

---

## Manajemen Akun Admin & Reset Sandi via WhatsApp

### Aturan akses login

Saat login (dan pada setiap request), sistem memeriksa:

| Kondisi | Efek |
|---|---|
| `is_active = false` (dinonaktifkan) | Login ditolak: "Akun Anda dinonaktifkan..." |
| `masa_aktif_akhir` < hari ini | Login ditolak: "Masa aktif akun Anda telah berakhir (s.d. TANGGAL)..." |
| Keduanya baik | Login normal |

Pengaman bawaan: tidak bisa menonaktifkan/menghapus **akun sendiri**, dan tidak
bisa menonaktifkan admin terakhir yang masih aktif.

### Alur reset sandi (halaman login -> "Lupa kata sandi?")

1. Admin memasukkan username -> server membuat kode 6 digit acak, menyimpan
   **hash**-nya (10 menit berlaku), dan mengirim pesan ke nomor WhatsApp
   terdaftar akun tersebut.
2. Admin memasukkan kode + kata sandi baru (min. 8 karakter).
3. Kode benar -> sandi diperbarui dan OTP hangus; salah maks. 5 kali -> kode
   dibatalkan, minta kode baru.

### Gateway WhatsApp (env)

```
WA_PROVIDER=mock        # default: kode hanya dicatat di log server (offline/demo)
WA_PROVIDER=fonnte      # kirim nyata via https://fonnte.com
WA_API_TOKEN=token-anda # wajib bila WA_PROVIDER=fonnte
OTP_TTL_MINUTES=10
OTP_MAX_ATTEMPTS=5
OTP_RESEND_SECONDS=60
```

Catatan penting: pada `APP_ENV != production`, respons API menyertakan
`debug_code` dan halaman login menampilkannya agar alur dapat didemokan tanpa
gateway WA. Pada produksi field ini TIDAK pernah muncul - kode hanya sampai ke
WhatsApp. Nomor WA dinormalisasi otomatis (08... / 8... -> 62...). Yang dikirim
ke gateway hanyalah nomor tujuan dan teks OTP - tidak ada data kasus.

---

## Keputusan Desain Penting

| Topik | Keputusan |
|---|---|
| Skor DASS-21 | Dihitung modul `dass21_scoring.py` (jumlah item x2, versi penilaian `DASS21-ID-STD-1.0`); hanya untuk admin; kategori memakai cut-off publikasi umum dan **bukan** kategori resmi UPA BK |
| Petugas penangani | Direktori nama staf (tabel `petugas`) dikelola admin; **bukan akun login** sehingga tidak menambah permukaan akses. Kolom `followups.assigned_admin_id` tetap mencatat akun admin terakhir yang memperbarui (audit), sedangkan `petugas_id` adalah penanggung jawab yang ditetapkan |
| Akun admin & masa aktif | Akun admin dikelola dari dashboard (profil nama/NIM/fakultas wajib, aktif/nonaktif, masa aktif berbatas tanggal). Pemeriksaan status berlaku pada login DAN tiap request sehingga penonaktifan efektif seketika; token lama tidak berguna |
| OTP reset sandi | Kode disimpan sebagai hash SHA-256 + pepper `SECRET_KEY`, tidak pernah plain; anti-enumerasi (respons generik untuk username tak dikenal/nonaktif/tanpa nomor WA); `debug_code` hanya ada di lingkungan non-produksi |
| Krisis | Lapisan kata kunci terpisah yang TIDAK bergantung pada LLM; pesan keamanan memuat 112 & 119 ext. 8; kontak UPA BK masih placeholder `[Dikonfirmasi oleh UPA BK]` |
| Akses obrolan mahasiswa | Token akses turunan HMAC dari `SECRET_KEY` + `registration_id` (tidak tersimpan di DB); mahasiswa hanya melihat datanya sendiri |
| Chat token vs sesi admin | Mahasiswa tanpa akun; admin memakai token bertanda tangan HMAC bermasa aktif + cookie HttpOnly |
| Log | Tidak pernah memuat isi keluhan/obrolan/password/API key; hanya metadata (id, status, panjang pesan) |
| Zona waktu | DB menyimpan UTC; frontend menampilkan WIB (`Asia/Jakarta`); jadwal konseling memakai tanggal/jam WIB eksplisit (bukan turunan timestamp) |

## Catatan Keamanan Produksi

Baca `docs/prototype-limitations.md` sebelum menggunakan data nyata. Ringkas:
HTTPS wajib, ganti `SECRET_KEY`, perketat CORS, migrasi PostgreSQL, review
hukum/privasi untuk pengiriman data ke LLM eksternal, protokol krisis resmi
UPA BK, dan penambahan jejak audit permanen.

---

## Mengunggah ke GitHub

Repo ini siap diunggah: `.gitignore` sudah mengecualikan `.env`, database
(`*.db`), `venv/`, dan `__pycache__/` sehingga rahasia & data tidak ikut ke
GitHub. Setiap push/pull request dijalankan otomatis oleh CI
(`.github/workflows/ci.yml`): seluruh 119 tes pytest harus lulus.

```bash
git init
git add .
git commit -m "UPA BK UTM: layanan konseling + kalender mingguan/bulanan prioritas darurat + pengingat"

# buat repo kosong di GitHub (tanpa README), lalu:
git remote add origin https://github.com/<username>/upa-bk-utm.git
git branch -M main
git push -u origin main
```

> Jangan pernah meng-commit file `.env` atau `upabk.db` berisi data nyata.
> Kredensial login tidak pernah disimpan di kode - semua lewat environment.

## Menjalankan dari Clone GitHub (agar login/sandi benar-benar berfungsi)

Sistem sandi sudah diuji 119 tes + alur manual (login benar diterima, login
salah ditolak, ganti sandi membuat sandi lama hangus). Agar sandi berfungsi
benar saat di-deploy, ikuti urutan ini:

1. **Clone & instal**:
   ```bash
   git clone https://github.com/<username>/upa-bk-utm.git
   cd upa-bk-utm
   python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Set environment WAJIB** (buat file `.env` atau environment hosting):
   ```bash
   APP_ENV=production
   SECRET_KEY=<hasil: python -c "import secrets; print(secrets.token_urlsafe(48))">
   ADMIN_USERNAME=<username-anda>
   ADMIN_PASSWORD=<sandi-kuat-minimal-8-karakter>
   ```
   Sandi tersimpan sebagai hash PBKDF2-SHA256 (390.000 iterasi). Kunci
   `SECRET_KEY` yang berarti sesi/token/OTP ikut berubah - jangan ganti
   `SECRET_KEY` setelah ada pengguna aktif tanpa sadar semua sesi hangus.
3. **Inisialisasi database** (pilih salah satu):
   - Produksi: `python init_db.py` lalu `python create_admin.py <username> <sandi>`
     untuk membuat admin pertama.
   - Demo lokal: `python seed_data.py` (data fiktif + contoh jadwal minggu berjalan).
4. **Jalankan**: `python run.py` (lokal) atau `uvicorn app.main:app --host 0.0.0.0 --port 8000`
   di belakang reverse proxy HTTPS (Nginx/Caddy) atau platform seperti
   Render/Railway/Fly.io.
5. **Login di** `/admin-login.html`. Lupa sandi? Gunakan "Lupa kata sandi?"
   (OTP WhatsApp; set `WA_PROVIDER=fonnte` + `WA_API_TOKEN` untuk kirim nyata)
   atau reset via `python create_admin.py <username> <sandi-baru>`.

Gejala umum & solusi cepat:

| Gejala | Penyebab | Solusi |
|---|---|---|
| Login selalu "Username atau password salah" | Database baru masih kosong / admin belum dibuat | Jalankan `init_db.py` + `create_admin.py`, cek `ADMIN_USERNAME`/`ADMIN_PASSWORD` |
| Sesi langsung hangus setelah restart server | `SECRET_KEY` berubah tiap restart | Set `SECRET_KEY` tetap di environment |
| OTP tidak terkirim | Gateway WhatsApp belum dikonfigurasi | Set `WA_PROVIDER=fonnte` + `WA_API_TOKEN` (mode non-produksi menampilkan `debug_code`) |
| Tabel lama tidak punya kolom baru | Database lama dari versi sebelumnya | `python init_db.py` menjalankan migrasi ringan otomatis saat startup |

## Deploy ke Internet Gratis (FastAPI Cloud)

Cara termudah menempelkan aplikasi ke internet tanpa kartu kredit:
[FastAPI Cloud](https://fastapicloud.com) - hosting resmi dari pembuat
FastAPI. Paket Hobby gratis, dan **setiap `git push` ke branch `main`
otomatis deploy ulang**.

1. Daftar di https://fastapicloud.com (cukup email / akun GitHub).
2. Dashboard -> tim Anda -> **Create new app** -> pilih **GitHub Repo** ->
   sambungkan GitHub dan pilih repository ini -> **Create App**.
3. Di halaman aplikasi, isi **Environment Variables** (wajib):
   `APP_ENV=production`, `SECRET_KEY` (string acak panjang),
   `ADMIN_USERNAME`, `ADMIN_PASSWORD` (sandi kuat).
   Akun admin pertama dibuat otomatis saat aplikasi start bila database
   masih kosong.
4. Aplikasi online di `https://<nama-app>.fastapicloud.dev`; halaman admin
   di `/admin-login.html`.

Catatan paket gratis: penyimpanan sementara (data terhapus saat rebuild/
restart - cocok untuk demo/uji coba), dan aplikasi scale-to-zero ketika
idle. Untuk pemakaian nyata jangka panjang, gunakan database eksternal
(PostgreSQL) atau paket berbayar dengan persistent disk. File `Dockerfile`
di repo juga siap untuk platform Docker lain (mis. Hugging Face Spaces,
sekarang berbayar).

