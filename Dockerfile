# ── Stage 1: Build (Yig'ish bosqichi) ──────────────────────────
FROM python:3.11-slim as builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Kompilyatsiya uchun zarur paketlar (agar kutubxonalar build talab qilsa)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Kutubxonalarni maxsus papkaga o'rnatamiz
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime (Ishga tushirish bosqichi) ──────────────
FROM python:3.11-slim

WORKDIR /app

# Faqat ish vaqtida kerak bo'ladigan paketlar (ffmpeg va minimal libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Yuklab olingan fayllar uchun papka yaratish
RUN mkdir -p /app/downloads

# Builder stage-dan faqat o'rnatilgan paketlarni nusxalaymiz
COPY --from=builder /install /usr/local
COPY . .

ENV PORT=8000
EXPOSE 8000

# Volume orqali fayllarni boshqarish imkoniyati
VOLUME ["/app/downloads"]

CMD ["python", "bot.py"]