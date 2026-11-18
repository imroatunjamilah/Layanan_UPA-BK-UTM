# Batasan Prototipe & Checklist Pra-Produksi - UPA BK UTM

Dokumen ini memuat (1) keterbatasan yang diketahui dari prototipe dan
(2) daftar periksa yang HARUS dipenuhi sebelum aplikasi dipakai dengan data
mahasiswa sungguhan. Aplikasi ini **bukan** sistem produksi; beberapa keputusan
desain sengaja disederhanakan demi pengembangan cepat dan pengujian tanpa biaya.

---

## Bagian 1 - Batasan yang Diketahui

### Keamanan & Autentikasi

1. **Token sesi stateless (HMAC)** - tidak ada pembatalan sesi seketika; rotasi
   token/daftar hitam belum ada. Masa aktif default 8 jam
   (`TOKEN_EXPIRE_MINUTES`). Produksi sebaiknya memakai sesi server-side atau
   JWT dengan refresh + rotation.
2. **Rate limit login in-memory** - penghitung percobaan gagal hilang saat
   restart dan tidak dibagi antar proses worker. Produksi perlu rate limit
   terdistribusi (Redis) + proteksi brute-force di level reverse proxy.
3. **RBAC sederhana** - hanya satu peran efektif (`admin`). Perbedaan
   admin vs petugas (mis. petugas tidak boleh ekspor sensitif) belum ada.
4. **Token akses obrolan mahasiswa bersifat turunan HMAC** dari
   `SECRET_KEY` + `registration_id` - tidak dapat dicabut dan tidak
   bermasa aktif. Jika `SECRET_KEY` bocor, semua token mahasiswa bisa
   diturunkan. Cocok untuk prototipe, bukan untuk produksi.
5. **CORS terbuka (`*`)** untuk memudahkan pengembangan. Wajib diperketat
   ke origin kampus sebelum produksi.
6. **Tidak ada HTTPS di prototipe** - server pengembangan berjalan HTTP.
   Produksi wajib di belakang HTTPS (reverse proxy kampus).
7. **Tidak ada 2FA** untuk akun petugas, dan tidak ada alur reset password
   mandiri (ganti password hanya via API/CLI dengan sesi aktif).

### Klinis & Protokol Layanan

8. **Redaksi 21 pernyataan DASS-21 adalah terjemahan kerja** yang dibuat untuk
   prototipe - belum divalidasi psikometrik. Sebelum dipakai nyata, UPA BK wajib
   memakai/mengesahkan versi terjemahan baku yang tervalidasi
   (`app/services/dass21_questions.py`).
9. **Kategori DASS-21 memakai cut-off publikasi umum** (Lovibond & Lovibond,
   1995) dan secara eksplisit **bukan kategori risiko resmi UPA BK**. Menyamakan
   keduanya tanpa persetujuan resmi dilarang (kebutuhan proyek). Skor adalah
   alat skrining, bukan diagnosis.
10. **Protokol krisis adalah konfigurasi default yang belum disetujui**:
    kata kunci deteksi sederhana (Bahasa Indonesia sehari-hari, tanpa slang
    lengkap), pesan keamanan memuat 112 / 119 ext. 8, dan kontak UPA BK masih
    placeholder `[Dikonfirmasi oleh UPA BK]`. Nomor kampus, alur verifikasi
    petugas, dan template pesan harus ditetapkan UPA BK.
11. **Eskalasi otomatis hanya menandai antrean** - tidak ada integrasi notifikasi
    nyata (SMS/WhatsApp/email/panggilan). Aplikasi **tidak menjanjikan respons
    manusia seketika** (sesuai kebutuhan), sehingga kondisi darurat tetap
    mengandalkan hotline. Integrasi on-call/pendjagaan petugas diperlukan
    sebelum produksi.
12. **Permintaan pendampingan manusia hanya dicatat** sebagai catatan otomatis
    dan pesan konfirmasi; belum ada mekanisme antrian tugas/kurasi khusus.
13. **Chatbot bukan alat terapi**: penyedia mock memakai aturan sederhana;
    LLM nyata bisa keliru. System prompt melarang diagnosis/saran obat, tetapi
    tidak ada penyaring konten keluaran (output guard) tambahan.

### Privasi & Data

14. **Pengiriman data ke LLM eksternal dinonaktifkan secara default**
    (`LLM_ALLOW_EXTERNAL=false`). Mengaktifkannya tanpa review privasi/dasar
    pemrosesan data melanggar prinsip proyek: data kesehatan mental yang dapat
    mengidentifikasi seseorang tidak boleh dikirim ke layanan eksternal tanpa
    persetujuan dan pengamanan yang memadai.
15. **Log audit minimal** - ekspor CSV, login, eskalasi dicatat, tetapi belum ada
    tabel audit permanen untuk akses data sensitif (siapa melihat detail siapa,
    kapan). Kebijakan "riwayat obrolan dilihat sesuai kelas akses" baru
    diimplementasikan sebatas pembatasan endpoint + pesan `sistem` khusus admin.
16. **Tidak ada retensi/anonimisasi** - data obrolan & skrining tersimpan tanpa
    batas waktu. Kebijakan retensi (mis. hapus setelah X bulan) harus ditetapkan
    institusi dan diimplementasikan.
17. **Seed data fiktif** - semua nama/NIM/kontak pada `seed_data.py` adalah
    fiktif dan domain `mail.contoh.ac.id` dipakai agar jelas semu. Jangan pernah
    menggantinya dengan data mahasiswa asli di repositori.

### Arsitektur & Operasional

18. **SQLite untuk pengembangan** - struktur model dibuat portabel
    (tipe standar SQLAlchemy) namun migrasi PostgreSQL belum diuji; belum ada
    tool migrasi skema (Alembic). `DATABASE_URL` perlu diubah + pengetesan ulang.
19. **Satu baris tindak lanjut per pendaftaran** (`uq_followup_registration`) -
    perubahan status menimpa nilai lama; belum ada tabel riwayat status.
20. **Skrining sekali per pendaftaran** (`uq_dass21_registration`) - mahasiswa
    yang mendaftar ulang mendapat baris pendaftaran baru; belum ada dedup NIM.
21. **Tanpa backup/restore otomatis** - file SQLite harus dibackup manual
    selama pengembangan.
22. **Tanpa CI/CD** - pengujian dijalankan manual (`pytest`), belum ada pipeline.
23. **Frontend sederhana** - HTML/JS statis tanpa framework; aksesibilitas
    (WCAG) baru memenuhi dasar (label, aria pada beberapa elemen) dan belum
    diaudit; layar kecil diuji terbatas. sessionStorage dipakai menyimpan
    `chat_token` mahasiswa (hilang saat tab ditutup - memengaruhi kenyamanan,
    namun membatasi risiko).
24. **Zona waktu** - DB menyimpan UTC, UI menampilkan WIB (`Asia/Jakarta`).
    Bila layanan lintas zona diperlukan, perlu penyesuaian.

---

## Bagian 2 - Checklist Sebelum Produksi

### A. Tata Kelola & Klinis (UPA BK)

- [ ] Menyetujui **protokol krisis resmi**: nomor kontak darurat kampus,
      alur verifikasi petugas, SLA respons, template pesan
      (ganti `app/services/crisis.py`, khususnya `UPA_BK_EMERGENCY_CONTACT`).
- [ ] Memvalidasi/mengesahkan **redaksi DASS-21** yang dipakai.
- [ ] Menetapkan apakah kategori cut-off DASS-21 boleh ditampilkan ke petugas
      atau hanya skor mentah; menyamakan/denial kategori resmi UPA BK.
- [ ] Menyetujui **aturan eskalasi otomatis** (`CRISIS_CONFIG`) dan siapa yang
      menerima notifikasi eskalasi.
- [ ] Menetapkan **kebijakan retensi data** (skrining, obrolan, log).
- [ ] Menyusun **SOP pemantauan antrean prioritas** (siapa menjaga, kapan).

### B. Hukum & Privasi

- [ ] Review hukum pemrosesan data kesehatan mental (dasar pemrosesan,
      persetujuan, hak subjek data).
- [ ] **Jangan mengaktifkan `LLM_ALLOW_EXTERNAL`** sebelum: kontrak pemrosesan
      data dengan penyedia, penonaktifan logging penyedia, evaluasi
      pengiriman minimal data, dan persetujuan institusi.
- [ ] Menambah **tabel jejak audit permanen** untuk akses data sensitif
      (detail mahasiswa, ekspor) dan pemeriksaan berkala.
- [ ] Menyembunyikan/menyamarkan pengenal di seluruh log (sudah dilakukan
      sebatas prototipe - audit ulang).

### C. Keamanan Teknis

- [ ] HTTPS wajib (reverse proxy kampus), HSTS.
- [ ] Ganti `SECRET_KEY` dengan nilai acak panjang + strategi rotasi.
- [ ] Perketat CORS ke domain kampus.
- [ ] Pindahkan rate limit ke penyimpanan bersama; tambah proteksi
      brute-force di proxy.
- [ ] Tambah 2FA untuk akun petugas + alur reset password resmi.
- [ ] Ganti token mahasiswa turunan-HMAC dengan token bermasa aktif yang
      dapat dicabut (disimpan hash di DB).
- [ ] Tambah header keamanan (CSP, X-Frame-Options, dsb.).
- [ ] Uji penetrasi dasar + dependency scanning rutin (`pip-audit`).

### D. Infrastruktur & Data

- [ ] Migrasi ke PostgreSQL + Alembic untuk migrasi skema.
- [ ] Backup otomatis terjadwal + uji restore.
- [ ] Tambah tabel riwayat status tindak lanjut (audit trail perubahan status).
- [ ] Notifikasi nyata untuk eskalasi (email/WhatsApp gateway/SMS) sesuai
      keputusan UPA BK.
- [ ] CI/CD: jalankan `pytest` otomatis pada setiap perubahan.
- [ ] Monitoring (uptime, error rate) + prosedur on-call petugas TI.

### E. Pengujian Tambahan

- [ ] Uji penerimaan bersama petugas UPA BK (alur nyata, bukan data dummy).
- [ ] Uji aksesibilitas (keyboard-only, screen reader).
- [ ] Uji beban ringan untuk skenario pendaftaran massal.
- [ ] Uji manual skenario krisis bersama stres kasus yang disepakati.

### F. Penjadwalan (fitur jadwal mingguan)

Yang SUDAH ada: kalender mingguan WIB (Senin-Minggu), antrean prioritas
darurat (krisis paling atas, lalu DASS-21 Berat/Sangat Berat, lalu paling lama
menunggu), penugasan konselor manual oleh admin, deteksi bentrok slot konselor,
dan status sesi (terjadwal/selesai/dibatalkan/ditunda).

Batasan saat ini (belum ada, perlu keputusan/kebutuhan UPA BK):

- [ ] Belum ada konfigurasi jam kerja/availabilitas per konselor (slot manual
      penuh oleh admin; sistem hanya mencegah tumpang tindih).
- [ ] Belum ada notifikasi ke mahasiswa saat jadwal dibuat/diubah (mis. via
      WhatsApp gateway).
- [ ] Belum ada jadwal berulang (mis. "setiap Selasa 10.00 selama 4 sesi").
- [ ] Mahasiswa belum bisa melihat/mengonfirmasi jadwalnya sendiri.
- [ ] Riwayat perubahan jadwal belum disimpan sebagai audit trail permanen
      (hanya log aplikasi).

---

## Penutup

Prototipe ini dimaksudkan sebagai fondasi yang dapat dijalankan dan diuji:
seluruh alur mahasiswa-admin berfungsi dengan data fiktif, kebijakan sensitif
diterapkan secara eksplisit di kode, dan semua keputusan yang memerlukan
wewenang institusi ditandai sebagai konfigurasi yang menunggu persetujuan
UPA BK - bukan dikarang. Lengkapi checklist di atas sebelum data mahasiswa
asli masuk ke sistem.
