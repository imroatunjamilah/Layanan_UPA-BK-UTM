"""Titik masuk aplikasi untuk platform hosting (FastAPI Cloud, dsb.).

Sebagian besar platform mengekspor variabel `app` dari file `main.py`
atau `app/main.py` di akar proyek. File ini menjamin deteksi otomatis
di mana pun aplikasi ditempatkan, tanpa mengubah perilaku apa pun.
"""
from app.main import app

__all__ = ["app"]
