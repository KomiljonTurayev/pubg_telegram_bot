import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Loyiha sozlamalari va muhit o'zgaruvchilari."""
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
    
    # DB sozlamalari
    DB_NAME = os.getenv("POSTGRES_DB", "postgres")
    DB_USER = os.getenv("POSTGRES_USER", "postgres")
    DB_PASS = os.getenv("POSTGRES_PASSWORD", "password")
    DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
    
    # To'lov
    PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")  # Click yoki Payme
    # FFmpeg
    FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")