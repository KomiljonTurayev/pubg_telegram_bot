import pytest
import asyncio
from database import db

@pytest.mark.asyncio
async def test_database_connection():
    """Ma'lumotlar bazasiga ulanish va foydalanuvchi qo'shishni tekshirish."""
    test_id = 123456789
    await db.add_user(test_id, "testuser", "Test User")
    
    # Adminlikni tekshirish (default FALSE bo'lishi kerak)
    is_admin = await db.is_admin_db(test_id)
    assert is_admin is False

def test_config_placeholders():
    """Config o'zgaruvchilari mavjudligini tekshirish."""
    from config import Config
    assert Config.BOT_TOKEN is not None

@pytest.mark.asyncio
async def test_products_count():
    """Mahsulotlar sonini olish funksiyasini tekshirish."""
    count = await db.get_products_count()
    assert isinstance(count, int)