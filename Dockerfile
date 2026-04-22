FROM python:3.11-slim

# Tizim paketlarini o'rnatish (ffmpeg video konvertatsiya uchun zarur)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Kutubxonalarni o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bot kodini nusxalash
COPY . .

# FastAPI porti uchun muhit o'zgaruvchisi
ENV PORT=8000
EXPOSE 8000

# Botni ishga tushirish
CMD ["python", "bot.py"]