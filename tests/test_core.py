"""
Core unit testlar — DB ulanishsiz ishlaydi (mock).
"""
import asyncio
import os
import sys
import unittest.mock as mock
import pytest

# ── DB mock (import tartibiga qarab) ──────────────────────────
fake_db = mock.AsyncMock()
fake_db.is_banned        = mock.AsyncMock(return_value=False)
fake_db.is_admin_db      = mock.AsyncMock(return_value=False)
fake_db.get_stats        = mock.AsyncMock(return_value=(100, []))
fake_db.get_cached_music = mock.AsyncMock(return_value=None)
fake_db.save_search_history = mock.AsyncMock()
fake_db.get_total_searches  = mock.AsyncMock(return_value=500)
fake_db.get_daily_active_users = mock.AsyncMock(return_value=25)
fake_db.get_most_searched      = mock.AsyncMock(return_value=[("Eminem", 10)])
fake_db.get_cache_count        = mock.AsyncMock(return_value=200)
fake_db.get_total_downloads    = mock.AsyncMock(return_value=1500)

sys.modules["database"]      = mock.MagicMock(db=fake_db, Database=mock.MagicMock(return_value=fake_db))
sys.modules["psycopg2"]      = mock.MagicMock()
sys.modules["psycopg2.pool"] = mock.MagicMock()

os.environ.setdefault("BOT_TOKEN", "0:test_token")
os.environ.setdefault("ADMIN_ID",  "0")


# ──────────────────────────────────────────────────────────────
# 1. Rate Limiter
# ──────────────────────────────────────────────────────────────
class TestRateLimiter:
    def test_search_allows_within_limit(self):
        from rate_limiter import check_search, _search_log
        _search_log.clear()
        uid = 10001
        for _ in range(4):
            ok, wait = check_search(uid)
            assert ok is True
            assert wait == 0

    def test_search_blocks_over_limit(self):
        from rate_limiter import check_search, _search_log
        _search_log.clear()
        uid = 10002
        for _ in range(4):
            check_search(uid)
        ok, wait = check_search(uid)
        assert ok is False
        assert wait > 0

    def test_download_allows_within_limit(self):
        from rate_limiter import check_download, _download_log
        _download_log.clear()
        uid = 10003
        for _ in range(2):
            ok, wait = check_download(uid)
            assert ok is True

    def test_download_blocks_over_limit(self):
        from rate_limiter import check_download, _download_log
        _download_log.clear()
        uid = 10004
        for _ in range(2):
            check_download(uid)
        ok, wait = check_download(uid)
        assert ok is False
        assert wait > 0

    def test_different_users_independent(self):
        from rate_limiter import check_search, _search_log
        _search_log.clear()
        for uid in [20001, 20002, 20003]:
            ok, _ = check_search(uid)
            assert ok is True


# ──────────────────────────────────────────────────────────────
# 2. Config
# ──────────────────────────────────────────────────────────────
class TestConfig:
    def test_bot_token_loaded(self):
        from config import Config
        assert Config.BOT_TOKEN is not None
        assert len(Config.BOT_TOKEN) > 0

    def test_admin_id_integer(self):
        from config import Config
        assert isinstance(Config.ADMIN_ID, int)

    def test_optional_api_keys_default_empty(self):
        from config import Config
        assert isinstance(Config.YOUTUBE_API_KEY, str)
        assert isinstance(Config.OMDB_API_KEY, str)


# ──────────────────────────────────────────────────────────────
# 3. Music Search — keyboard builder
# ──────────────────────────────────────────────────────────────
class TestMusicSearch:
    SAMPLE_DEEZER = [
        {"title": "Lose Yourself", "artist": "Eminem", "duration": "5:26",
         "deezer_id": "123456789", "preview": "https://preview.url", "cover": "https://cover.url", "album": "8 Mile"},
        {"title": "Stan",          "artist": "Eminem", "duration": "6:44",
         "deezer_id": "987654321", "preview": "https://preview2.url", "cover": "", "album": "The Marshall Mathers LP"},
    ]
    SAMPLE_YT = [
        {"id": "abc123", "title": "Eminem - Lose Yourself", "artist": "Eminem", "duration": "5:26", "source": "youtube"},
    ]

    def test_deezer_keyboard_callback_length(self):
        from music_search import build_deezer_keyboard
        kb = build_deezer_keyboard(self.SAMPLE_DEEZER)
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data:
                    assert len(btn.callback_data.encode()) <= 64, \
                        f"callback_data too long: {btn.callback_data}"

    def test_deezer_keyboard_correct_callback_prefix(self):
        from music_search import build_deezer_keyboard
        kb = build_deezer_keyboard(self.SAMPLE_DEEZER)
        data_buttons = [
            btn for row in kb.inline_keyboard for btn in row
            if btn.callback_data and btn.callback_data != "close_search"
        ]
        for btn in data_buttons:
            assert btn.callback_data.startswith("dz_show_"), btn.callback_data

    def test_youtube_keyboard_callback_prefix(self):
        from music_search import build_youtube_keyboard
        kb = build_youtube_keyboard(self.SAMPLE_YT)
        data_buttons = [
            btn for row in kb.inline_keyboard for btn in row
            if btn.callback_data and btn.callback_data != "close_search"
        ]
        assert all(btn.callback_data.startswith("show_music_options_") for btn in data_buttons)

    def test_build_results_keyboard_is_alias(self):
        from music_search import build_results_keyboard, build_youtube_keyboard
        assert build_results_keyboard is build_youtube_keyboard

    def test_empty_results_gives_close_button(self):
        from music_search import build_deezer_keyboard
        kb = build_deezer_keyboard([])
        all_cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "close_search" in all_cbs


# ──────────────────────────────────────────────────────────────
# 3b. Video Note option (YouTube)
# ──────────────────────────────────────────────────────────────
class TestVideoNote:
    @pytest.mark.asyncio
    async def test_show_music_options_includes_video_note_button(self, monkeypatch):
        import music_downloader

        async def fake_get_link_info(url: str):
            return {"title": "Test title"}

        monkeypatch.setattr(music_downloader, "get_link_info", fake_get_link_info)

        captured = {}

        async def reply_text(text, reply_markup=None, parse_mode=None, **kwargs):
            captured["reply_markup"] = reply_markup
            return mock.AsyncMock()

        msg = mock.MagicMock()
        msg.reply_text = reply_text

        query = mock.MagicMock()
        query.data = "show_music_options_abc123"
        query.message = msg
        query.answer = mock.AsyncMock()

        upd = mock.MagicMock()
        upd.callback_query = query

        await music_downloader.show_music_options(upd, mock.MagicMock())

        kb = captured["reply_markup"]
        assert kb is not None
        all_cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
        assert "vnote_abc123" in all_cbs


# ──────────────────────────────────────────────────────────────
# 4. Utils decorators
# ──────────────────────────────────────────────────────────────
class TestDecorators:
    def test_admin_only_is_async(self):
        from utils import admin_only
        dummy = admin_only(lambda u, c: None)
        assert asyncio.iscoroutinefunction(dummy)

    def test_ban_check_is_async(self):
        from utils import ban_check
        dummy = ban_check(lambda u, c: None)
        assert asyncio.iscoroutinefunction(dummy)

    @pytest.mark.asyncio
    async def test_ban_check_blocks_banned_user(self):
        fake_db.is_banned = mock.AsyncMock(return_value=True)
        from utils import ban_check

        called = []

        @ban_check
        async def handler(update, context):
            called.append(True)

        upd = mock.MagicMock()
        upd.effective_user.id = 99999
        upd.callback_query = None
        upd.effective_message = mock.AsyncMock()

        await handler(upd, mock.MagicMock())
        assert called == [], "Banned user should not reach handler"
        fake_db.is_banned = mock.AsyncMock(return_value=False)

    @pytest.mark.asyncio
    async def test_ban_check_passes_normal_user(self):
        fake_db.is_banned = mock.AsyncMock(return_value=False)
        from utils import ban_check

        called = []

        @ban_check
        async def handler(update, context):
            called.append(True)

        upd = mock.MagicMock()
        upd.effective_user.id = 88888
        upd.callback_query = None

        await handler(upd, mock.MagicMock())
        assert called == [True]


# ──────────────────────────────────────────────────────────────
# 5. Trending moduli
# ──────────────────────────────────────────────────────────────
class TestTrending:
    def test_module_has_required_functions(self):
        import trending
        assert callable(trending.get_trending_music)
        assert callable(trending.get_trending_videos)
        assert callable(trending.search_deezer)

    @pytest.mark.asyncio
    async def test_trending_music_returns_list(self):
        import trending
        result = await trending.get_trending_music()
        assert isinstance(result, list)
        if result:
            track = result[0]
            for key in ["title", "artist", "duration", "deezer_id"]:
                assert key in track, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_search_deezer_returns_list(self):
        import trending
        result = await trending.search_deezer("Eminem")
        assert isinstance(result, list)
        if result:
            track = result[0]
            for key in ["title", "artist", "duration", "deezer_id", "preview", "cover", "album"]:
                assert key in track, f"Missing key: {key}"


# ──────────────────────────────────────────────────────────────
# 6. Movie Handler
# ──────────────────────────────────────────────────────────────
class TestMovieHandler:
    def test_module_imports(self):
        import movie_handler
        assert callable(movie_handler.handle_movie_search)
        assert callable(movie_handler.handle_movie_detail)

    def test_no_api_key_config(self):
        from config import Config
        # OMDB_API_KEY mavjud yoki bo'sh — ikkalasi ham str bo'lishi kerak
        assert isinstance(Config.OMDB_API_KEY, str)
