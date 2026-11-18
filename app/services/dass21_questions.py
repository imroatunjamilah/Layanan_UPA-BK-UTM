"""Daftar 21 pernyataan DASS-21 versi Bahasa Indonesia (kerja).

CATATAN PENTING (harus divalidasi UPA BK):
Redaksi di bawah ini adalah terjemahan kerja dari DASS-21 (Lovibond & Lovibond, 1995).
Sebelum dipakai untuk layanan sesungguhnya, redaksinya harus direview/disetujui
oleh UPA BK (idealnya memakai versi terjemahan baku yang telah divalidasi psikometrik).
"""

INTRO_DASS21 = (
    "Pernyataan berikut berkaitan dengan cara Anda merasa dan berperilaku "
    "selama 7 hari terakhir. Tidak ada jawaban benar atau salah. Pilihlah "
    "jawaban yang paling menggambarkan kondisi Anda. Jawaban Anda bersifat "
    "rahasia: hasilnya hanya dapat diakses oleh petugas UPA BK dan tidak "
    "ditampilkan kepada mahasiswa."
)

# (nomor, subskala, teks)
QUESTIONS: list[tuple[int, str, str]] = [
    (1, "stres", "Saya merasa sulit untuk menjadi tenang (sulit rileks)."),
    (2, "kecemasan", "Saya merasa mulut saya kering."),
    (3, "depresi", "Saya merasa tidak ada perasaan positif sama sekali."),
    (4, "kecemasan", "Saya mengalami gangguan pernapasan (misalnya bernapas cepat atau sesak) tanpa melakukan aktivitas fisik yang berat."),
    (5, "depresi", "Saya merasa sulit memiliki inisiatif untuk memulai sesuatu."),
    (6, "stres", "Saya cenderung bereaksi berlebihan terhadap situasi."),
    (7, "kecemasan", "Saya merasa tubuh saya gemetar (misalnya tangan terasa gemetar)."),
    (8, "stres", "Saya merasa telah menghabiskan banyak energi karena cemas."),
    (9, "kecemasan", "Saya merasa khawatir dengan situasi di mana saya bisa panik dan mempermalukan diri."),
    (10, "depresi", "Saya merasa tidak ada lagi hal yang bisa saya harapkan."),
    (11, "stres", "Saya merasa gelisah dan sulit untuk menenangkan diri."),
    (12, "stres", "Saya merasa sulit untuk bersantai."),
    (13, "depresi", "Saya merasa sedih dan murung."),
    (14, "stres", "Saya merasa tidak sabar atau mudah marah ketika menghadapi hambatan."),
    (15, "kecemasan", "Saya merasa hampir mengalami kepanikan."),
    (16, "depresi", "Saya merasa tidak dapat bersemangat terhadap apa pun."),
    (17, "depresi", "Saya merasa hidup saya tidak berharga."),
    (18, "stres", "Saya merasa sulit untuk mentoleransi gangguan terhadap hal yang sedang saya lakukan."),
    (19, "kecemasan", "Saya menyadari detak jantung saya padahal tidak sedang melakukan aktivitas fisik."),
    (20, "kecemasan", "Saya merasa takut tanpa alasan yang jelas."),
    (21, "depresi", "Saya merasa hidup saya tidak bermakna."),
]

# Opsi jawaban standar DASS-21 (frekuensi dalam 7 hari terakhir)
ANSWER_OPTIONS = [
    {"nilai": 0, "label": "Tidak sama sekali"},
    {"nilai": 1, "label": "Sedikit, atau sesekali"},
    {"nilai": 2, "label": "Sedang, atau sering"},
    {"nilai": 3, "label": "Sangat cocok, atau hampir selalu"},
]
