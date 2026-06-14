# SOLID & Clean Architecture Refactoring Design

**Date:** 2026-06-14
**Scope:** Full architectural refactor of pubg_telegram_bot
**Environment:** Local only (no prod impact during refactor)

---

## Problem Statement

The current codebase has grown organically into a single large file (`bot.py`, ~42KB) with tightly coupled concerns. Database access, business logic, Telegram handlers, and external API calls are mixed together. This makes the code hard to test, extend, and maintain.

Key pain points:
- `bot.py` contains handlers, inline business logic, and direct DB calls
- No dependency injection — external clients are hardcoded, impossible to mock
- Tests hit the real database or require complex monkey-patching
- Error handling is scattered across every function with repeated `try/except` blocks
- No domain models — raw tuples from DB are passed around

---

## Goal

Refactor the bot into a layered SOLID architecture where:
- Each class has exactly one responsibility
- Dependencies flow inward (handlers → services → repositories → DB)
- All external dependencies are injected, not hardcoded
- Unit tests run without a real DB or Telegram connection
- Adding a new feature means adding files, not modifying existing ones

---

## Target Folder Structure

```
pubg_telegram_bot/
├── src/
│   ├── config/
│   │   └── settings.py              # Config class (all env vars)
│   │
│   ├── models/                      # Pure dataclasses, zero dependencies
│   │   ├── user.py                  # User dataclass
│   │   ├── product.py               # Product dataclass
│   │   ├── order.py                 # Order dataclass
│   │   ├── music.py                 # MusicTrack dataclass
│   │   └── errors.py                # BotError hierarchy
│   │
│   ├── repositories/                # Data access layer
│   │   ├── base.py                  # Protocol definitions for all repos
│   │   ├── user_repository.py       # PostgresUserRepository
│   │   ├── product_repository.py    # PostgresProductRepository
│   │   ├── order_repository.py      # PostgresOrderRepository
│   │   └── music_repository.py      # PostgresMusicRepository
│   │
│   ├── services/                    # Business logic layer
│   │   ├── music_service.py         # Search, cache, trending logic
│   │   ├── download_service.py      # yt-dlp orchestration, compress, split
│   │   ├── market_service.py        # Product catalog, order creation
│   │   ├── movie_service.py         # OMDB movie search
│   │   └── trending_service.py      # Deezer trending charts
│   │
│   ├── infrastructure/              # External API wrappers
│   │   ├── database.py              # psycopg2 connection pool only
│   │   ├── deezer_client.py         # Deezer REST API wrapper
│   │   ├── youtube_client.py        # yt-dlp wrapper (async)
│   │   └── omdb_client.py           # OMDB REST API wrapper
│   │
│   └── handlers/                    # Telegram presentation layer
│       ├── base_handler.py          # BaseHandler with safe_handle()
│       ├── start_handler.py         # /start, menu
│       ├── music_handler.py         # Music search, download callbacks
│       ├── download_handler.py      # URL detection, quality selection
│       ├── market_handler.py        # Marketplace, orders, payment
│       ├── movie_handler.py         # Movie search
│       └── admin_handler.py         # Stats, ban, product management
│
├── tests/
│   ├── unit/
│   │   ├── test_music_service.py
│   │   ├── test_market_service.py
│   │   ├── test_download_service.py
│   │   └── test_errors.py
│   └── integration/
│       ├── test_music_repository.py
│       └── test_user_repository.py
│
├── bot.py                           # Assembly only — wires DI, registers handlers
├── api.py                           # FastAPI mini-app (unchanged)
└── schema.sql                       # Unchanged
```

---

## Layer Responsibilities

### Models (`src/models/`)
- Pure Python `@dataclass` objects
- No methods that touch DB or external services
- Represent domain concepts: `User`, `Product`, `Order`, `MusicTrack`
- `errors.py` defines the exception hierarchy used across all layers

```python
# src/models/music.py
@dataclass
class MusicTrack:
    video_id: str
    title: str
    performer: str
    file_id: str | None = None
    download_count: int = 0

# src/models/errors.py
class BotError(Exception): ...
class NotFoundError(BotError): ...
class DownloadError(BotError): ...
class RateLimitError(BotError): ...
class PaymentError(BotError): ...
```

### Repositories (`src/repositories/`)
- `base.py` defines `Protocol` classes for each repository interface
- Concrete classes (`PostgresXxxRepository`) implement those protocols
- Contain only SQL queries and DB interaction — no business logic
- Accept `Database` (infrastructure) via constructor injection

```python
# src/repositories/base.py
class MusicRepositoryProtocol(Protocol):
    async def get_by_id(self, video_id: str) -> MusicTrack | None: ...
    async def save(self, track: MusicTrack) -> None: ...
    async def increment_download(self, video_id: str) -> None: ...
```

### Services (`src/services/`)
- Contain all business logic
- Accept repository protocols and infrastructure clients via constructor (DI)
- Never import concrete DB classes directly
- Raise typed `BotError` subclasses on failure

```python
# src/services/music_service.py
class MusicService:
    def __init__(
        self,
        repo: MusicRepositoryProtocol,
        deezer: DeezerClientProtocol,
        rate_limiter: RateLimiterProtocol,
    ): ...

    async def search(self, query: str, user_id: int) -> list[MusicTrack]: ...
    async def get_cached(self, video_id: str) -> MusicTrack | None: ...
    async def save_to_cache(self, track: MusicTrack) -> None: ...
```

### Infrastructure (`src/infrastructure/`)
- `database.py`: only holds the psycopg2 connection pool and `execute()` helper
- `deezer_client.py`, `youtube_client.py`, `omdb_client.py`: thin wrappers around external APIs, return domain models or raise `BotError` subclasses
- Each client also has a `Protocol` defined in `repositories/base.py` so services can depend on the protocol, not the concrete client

### Handlers (`src/handlers/`)
- Accept service objects via constructor injection
- Contain zero business logic — only translate between Telegram `Update` and service calls
- Inherit from `BaseHandler` which provides `safe_handle()` for centralized error-to-message translation
- Register their own handlers via a `register(app)` method

```python
# src/handlers/base_handler.py
class BaseHandler:
    async def safe_handle(self, update: Update, ctx: Context, coro: Awaitable) -> None:
        try:
            await coro
        except NotFoundError as e:
            await update.effective_message.reply_text(f"❌ Topilmadi: {e}")
        except DownloadError as e:
            await update.effective_message.reply_text(f"⚠️ Yuklab bo'lmadi: {e}")
        except RateLimitError:
            await update.effective_message.reply_text("⏳ Iltimos, biroz kuting.")
        except BotError as e:
            await update.effective_message.reply_text(f"❌ Xatolik: {e}")

# src/handlers/music_handler.py
class MusicHandler(BaseHandler):
    def __init__(self, music_service: MusicService): ...

    async def handle_search(self, update: Update, ctx: Context) -> None:
        await self.safe_handle(update, ctx,
            self._do_search(update, ctx))

    def register(self, app: Application) -> None:
        app.add_handler(MessageHandler(filters.TEXT, self.handle_search))
```

### bot.py — Assembly only
```python
# bot.py
settings = Settings()
db = Database(settings)

user_repo = PostgresUserRepository(db)
music_repo = PostgresMusicRepository(db)
product_repo = PostgresProductRepository(db)
order_repo = PostgresOrderRepository(db)

deezer = DeezerClient(settings)
youtube = YouTubeClient(settings)
omdb = OmdbClient(settings)

music_service = MusicService(music_repo, deezer)
download_service = DownloadService(youtube, music_repo)
market_service = MarketService(product_repo, order_repo)
movie_service = MovieService(omdb)
trending_service = TrendingService(deezer)

handlers = [
    StartHandler(user_repo),
    MusicHandler(music_service),
    DownloadHandler(download_service),
    MarketHandler(market_service),
    MovieHandler(movie_service),
    AdminHandler(user_repo, music_repo, order_repo),
]

app = ApplicationBuilder().token(settings.BOT_TOKEN).build()
for h in handlers:
    h.register(app)

app.run_polling()
```

---

## SOLID Principles Applied

| Principle | Application |
|---|---|
| **S** Single Responsibility | Handler = Telegram I/O only. Service = logic only. Repository = SQL only. |
| **O** Open/Closed | New feature = new Handler + Service + Repository. No existing file changed. |
| **L** Liskov Substitution | `PostgresMusicRepository` fully satisfies `MusicRepositoryProtocol` — swap without breaking callers. |
| **I** Interface Segregation | `MusicRepositoryProtocol` and `UserRepositoryProtocol` are separate — services only depend on what they use. |
| **D** Dependency Inversion | Services depend on `Protocol` abstractions, not concrete `Postgres*` classes. |

---

## Error Handling Strategy

All errors flow upward from infrastructure → service → handler.

- Infrastructure raises `BotError` subclasses (never raw exceptions)
- Services re-raise or wrap with more specific subtypes
- `BaseHandler.safe_handle()` catches all `BotError` subclasses and sends appropriate Telegram messages
- Unknown exceptions are logged and a generic message is sent

---

## Testing Strategy

### Unit Tests (no real DB, no Telegram)
- Use `unittest.mock.AsyncMock(spec=XxxProtocol)` for all injected deps
- Test service business logic in isolation
- Test that handlers call the correct service methods with correct args
- Test that each `BotError` subtype results in the correct reply text

### Integration Tests (real DB)
- Use `pytest-postgresql` or a test Docker container
- Test repository SQL queries against real PostgreSQL
- Run migrations via `schema.sql` in fixture setup

### What stays unchanged
- `api.py` (FastAPI mini-app) — no refactoring needed
- `schema.sql` — DB schema unchanged
- `.env` / `config` values — same env vars, new `Settings` class reads them

---

## Migration Approach

Refactor is done in one branch locally. Existing functionality is preserved exactly — no features added or removed. The public bot behavior (commands, messages, keyboards) stays identical. Only internal structure changes.

Order of implementation:
1. `src/models/` — dataclasses and errors (no deps, start here)
2. `src/config/settings.py` — replaces `config.py`
3. `src/infrastructure/database.py` — replaces `database.py`
4. `src/infrastructure/` clients — Deezer, YouTube, OMDB wrappers
5. `src/repositories/` — protocols + Postgres implementations
6. `src/services/` — business logic using injected deps
7. `src/handlers/` — thin Telegram adapters
8. `bot.py` — DI assembly, register handlers
9. `tests/unit/` — unit tests for each service
10. `tests/integration/` — repo integration tests
