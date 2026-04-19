"""
Shared test fixtures — mock DB unit testlar uchun.
"""
import sys
import os
import unittest.mock as mock
import pytest

# ── Mock DB — barcha unit testlar uchun autouse ────────────────
@pytest.fixture(scope="session", autouse=False)
def mock_db():
    """DB ga bog'liq modullarni mock bilan almashtirish."""
    fake = mock.AsyncMock()
    fake.is_banned            = mock.AsyncMock(return_value=False)
    fake.is_admin_db          = mock.AsyncMock(return_value=False)
    fake.get_stats            = mock.AsyncMock(return_value=(100, []))
    fake.get_cached_music     = mock.AsyncMock(return_value=None)
    fake.save_search_history  = mock.AsyncMock()
    fake.get_total_searches   = mock.AsyncMock(return_value=500)
    fake.get_daily_active_users = mock.AsyncMock(return_value=25)
    fake.get_most_searched    = mock.AsyncMock(return_value=[("Eminem", 10)])
    fake.get_cache_count      = mock.AsyncMock(return_value=200)
    fake.get_total_downloads  = mock.AsyncMock(return_value=1500)
    return fake
