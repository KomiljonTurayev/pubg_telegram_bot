"""
Database integration testlar — real PostgreSQL kerak.
CI da postgres:15-alpine service bilan ishlaydi.
"""
import os
import pytest
import asyncio

# Agar DB sozlanmagan bo'lsa, testni o'tkazib yuborish
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_PASSWORD"),
    reason="POSTGRES_PASSWORD not set — skipping DB tests"
)


@pytest.fixture(scope="module")
def db():
    from database import Database
    return Database()


@pytest.mark.asyncio
async def test_add_and_check_user(db):
    test_id = 999999901
    await db.add_user(test_id, "ci_test_user", "CI Test User")
    is_admin = await db.is_admin_db(test_id)
    is_banned = await db.is_banned(test_id)
    assert is_admin is False
    assert is_banned is False


@pytest.mark.asyncio
async def test_get_stats_returns_tuple(db):
    count, growth = await db.get_stats()
    assert isinstance(count, int)
    assert isinstance(growth, list)


@pytest.mark.asyncio
async def test_products_count_is_int(db):
    count = await db.get_products_count()
    assert isinstance(count, int)
    assert count >= 0


@pytest.mark.asyncio
async def test_music_cache_miss(db):
    result = await db.get_cached_music("nonexistent_video_id_xyz_999")
    assert result is None


@pytest.mark.asyncio
async def test_save_search_history(db):
    test_id = 999999902
    await db.add_user(test_id, "ci_search_user", "CI Search User")
    await db.save_search_history(test_id, "test query ci")
    count = await db.get_total_searches()
    assert isinstance(count, int)
    assert count >= 1


@pytest.mark.asyncio
async def test_daily_active_users_is_int(db):
    result = await db.get_daily_active_users()
    assert isinstance(result, int)
    assert result >= 0


@pytest.mark.asyncio
async def test_most_searched_is_list(db):
    result = await db.get_most_searched(5)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_ban_and_unban_user(db):
    test_id = 999999903
    await db.add_user(test_id, "ci_ban_user", "CI Ban User")
    await db.ban_user(test_id)
    assert await db.is_banned(test_id) is True
    await db.unban_user(test_id)
    assert await db.is_banned(test_id) is False
