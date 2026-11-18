# Docker image untuk deploy gratis di Hugging Face Spaces (tanpa kartu kredit).
# Aplikasi FastAPI mendengarkan di port 7860 (port standar HF Spaces).

FROM python:3.12-slim

WORKDIR /app

# Lapisan dependensi dipisah agar build cache efektif.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kode aplikasi, frontend, dan skrip bantu.
COPY . .

# HF Spaces mengharapkan port 7860 pada 0.0.0.0.
ENV PORT=7860 \
    HOST=0.0.0.0 \
    APP_ENV=production \
    PYTHONUNBUFFERED=1

EXPOSE 7860

CMD ["python", "run.py"]
