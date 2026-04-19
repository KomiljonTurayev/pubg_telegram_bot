"""
Database integration testlar — real PostgreSQL kerak.
CI da postgres:15-alpine service bilan ishlaydi.

MUHIM: Bu testlar faqat POSTGRES_PASSWORD env mavjud bo'lganda,
       va database moduli mock QILINMAGAN bo'lganda ishlaydi.
"""
import os
import sys
import pytest

# Modul-darajadagi mock bor bo'lsa yoki DB sozlanmagan bo'lsa — o'tkazib yubor
_db_module = sys.modules.get("database")
_is_mocked = _db_module is not None and hasattr(_db_module, "_mock_name")
_no_password = not os.getenv("POSTGRES_PASSWORD")

pytestmark = pytest.mark.skipif(
    _is_mocked or _no_password,
    reason="Real DB not available (mocked or POSTGRES_PASSWORD not set)",
)


@pytest.fixture(scope="module")
def real_db():
    """Real Database instance yaratish (mock emas)."""
    # Agar sys.modules da mock bo'lsa — o'chirib real ni yuklaymiz
    real_module = sys.modules.pop("database", None)
    try:
        import importlib
        db_mod = importlib.import_module("database")
        yield db_mod.db
    finally:
        if real_module is not None:
            sys.modules["database"] = real_module


@pytest.mark.asyncio
async def test_add_and_check_user(real_db):
    test_id = 999999901
    await real_db.add_user(test_id, "ci_test_user", "CI Test User")
    assert await real_db.is_admin_db(test_id) is False
    assert await real_db.is_banned(test_id) is False


@pytest.mark.asyncio
async def test_get_stats_returns_tuple(real_db):
    count, growth = await real_db.get_stats()
    assert isinstance(count, int)
    assert isinstance(growth, list)


@pytest.mark.asyncio
async def test_products_count_is_int(real_db):
    count = await real_db.get_products_count()
    assert isinstance(count, int)
    assert count >= 0


@pytest.mark.asyncio
async def test_music_cache_miss(real_db):
    result = await real_db.get_cached_music("nonexistent_xyz_ci_999")
    assert result is None


@pytest.mark.asyncio
async def test_save_search_and_count(real_db):
    test_id = 999999902
    await real_db.add_user(test_id, "ci_search_user", "CI Search User")
    await real_db.save_search_history(test_id, "ci_test_query_unique_xyz")
    count = await real_db.get_total_searches()
    assert isinstance(count, int)
    assert count >= 1


@pytest.mark.asyncio
async def test_daily_active_users_is_int(real_db):
    result = await real_db.get_daily_active_users()
    assert isinstance(result, int)


@pytest.mark.asyncio
async def test_ban_and_unban_user(real_db):
    test_id = 999999903
    await real_db.add_user(test_id, "ci_ban_user", "CI Ban User")
    await real_db.ban_user(test_id)
    assert await real_db.is_banned(test_id) is True
    await real_db.unban_user(test_id)
    assert await real_db.is_banned(test_id) is False
