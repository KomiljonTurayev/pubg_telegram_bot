import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def _parse_db_url(url):
    """DATABASE_URL ni alohida qismlarga ajratish."""
    parsed = urlparse(url)
    return {
        "name": parsed.path.lstrip("/"),
        "user": parsed.username,
        "pass": parsed.password,
        "host": parsed.hostname,
        "port": parsed.port or 5432,
    }

class Config:
    """Loyiha sozlamalari va muhit o'zgaruvchilari."""
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

    # DB sozlamalari — Render DATABASE_URL yoki alohida o'zgaruvchilar
    _db_url = os.getenv("DATABASE_URL")
    if _db_url:
        _db = _parse_db_url(_db_url)
        DB_NAME = _db["name"]
        DB_USER = _db["user"]
        DB_PASS = _db["pass"]
        DB_HOST = _db["host"]
        DB_PORT = _db["port"]
    else:
        DB_NAME = os.getenv("POSTGRES_DB", "postgres")
        DB_USER = os.getenv("POSTGRES_USER", "postgres")
        DB_PASS = os.getenv("POSTGRES_PASSWORD", "password")
        DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
        DB_PORT = int(os.getenv("POSTGRES_PORT", 5432))

    # To'lov
    PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")  # Click yoki Payme
    # FFmpeg
    FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")