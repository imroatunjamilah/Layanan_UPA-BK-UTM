"""Pengujian modul penilaian DASS-21 (unit test murni)."""
import pytest

from app.services.dass21_questions import QUESTIONS
from app.services.dass21_scoring import (
    SCORING_VERSION,
    SUBSCALE_ITEMS,
    classify_subscale,
    score_answers,
    validate_answers,
)


def test_21_pertanyaan_dengan_pembagian_3_subskala():
    assert len(QUESTIONS) == 21
    per_subskala = {}
    for no, sub, teks in QUESTIONS:
        per_subskala.setdefault(sub, []).append(no)
        assert teks, f"Pertanyaan {no} kosong."
    assert set(per_subskala) == {"depresi", "kecemasan", "stres"}
    for sub, items in per_subskala.items():
        assert len(items) == 7, f"Subskala {sub} harus 7 item."
        assert sorted(items) == sorted(SUBSCALE_ITEMS[sub])


def test_semua_jawaban_maksimal_menghasilkan_skor_42():
    answers = {i: 3 for i in range(1, 22)}
    hasil = score_answers(answers)
    assert hasil["skor_depresi"] == 42
    assert hasil["skor_kecemasan"] == 42
    assert hasil["skor_stres"] == 42
    assert hasil["scoring_version"] == SCORING_VERSION


def test_pemetaan_item_ke_subskala_yang_benar():
    # Hanya item depresi yang bernilai 3 -> hanya skor depresi yang 42.
    answers = {i: 0 for i in range(1, 22)}
    for i in (3, 5, 10, 13, 16, 17, 21):
        answers[i] = 3
    hasil = score_answers(answers)
    assert hasil["skor_depresi"] == 42
    assert hasil["skor_kecemasan"] == 0
    assert hasil["skor_stres"] == 0


def test_faktor_pengali_dua_kali():
    answers = {i: 0 for i in range(1, 22)}
    answers[1] = 2  # item stres
    assert score_answers(answers)["skor_stres"] == 4


def test_jawaban_tidak_lengkap_ditolak():
    answers = {i: 0 for i in range(1, 21)}  # nomor 21 hilang
    with pytest.raises(ValueError):
        score_answers(answers)


def test_nilai_di_luar_rentang_ditolak():
    answers = {i: 0 for i in range(1, 22)}
    answers[7] = 4
    with pytest.raises(ValueError):
        validate_answers(answers)
    answers[7] = -1
    with pytest.raises(ValueError):
        validate_answers(answers)


def test_nomor_tidak_dikenal_ditolak():
    answers = {i: 0 for i in range(1, 22)}
    answers[22] = 1
    with pytest.raises(ValueError):
        validate_answers(answers)


def test_batas_kategori_sesuai_cutoff_publikasi():
    # cut-off publikasi umum DASS-21 (Lovibond & Lovibond, 1995)
    assert classify_subscale("depresi", 0) == "Normal"
    assert classify_subscale("depresi", 9) == "Normal"
    assert classify_subscale("depresi", 10) == "Ringan"
    assert classify_subscale("depresi", 14) == "Sedang"
    assert classify_subscale("depresi", 21) == "Berat"
    assert classify_subscale("depresi", 28) == "Sangat Berat"
    assert classify_subscale("kecemasan", 8) == "Ringan"
    assert classify_subscale("kecemasan", 20) == "Sangat Berat"
    assert classify_subscale("stres", 15) == "Ringan"
    assert classify_subscale("stres", 34) == "Sangat Berat"
    with pytest.raises(ValueError):
        classify_subscale("subskala_lain", 10)


def test_hasil_scoring_tidak_mengandung_label_untuk_mahasiswa():
    """Kebijakan: skor/kategori tidak boleh keluar dari sistem ke arah mahasiswa.

    Fungsi penilaian hanya mengembalikan angka + versi penilaian.
    """
    hasil = score_answers({i: 1 for i in range(1, 22)})
    assert set(hasil) == {"skor_depresi", "skor_kecemasan", "skor_stres", "scoring_version"}
