"""Shared fixtures for contract/ and integration/ tests: a real, ephemeral
Postgres via testcontainers (ADR-003) — no SQLite fallback, matches prod dialect.
"""

import hashlib
import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

VALID_API_KEY = "test-api-key-do-not-use-in-prod"
VALID_API_KEY_HASH = hashlib.sha256(VALID_API_KEY.encode("utf-8")).hexdigest()

# Settings() is read once (lru_cache) on first use by the app; these must be
# in place before that happens. DATABASE_URL itself is never used by contract
# tests (the get_db_session dependency is overridden to point at the
# container), but Settings requires the field to be present.
os.environ.setdefault("API_KEY_HASHES", VALID_API_KEY_HASH)
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused/unused")
# Generous limit so unrelated tests never trip FR-014's rate limiter (all contract
# tests share one client IP via ASGITransport); SC-006 is covered by a unit test
# against SlidingWindowIpRateLimiter directly instead (tests/unit/test_ip_rate_limiter.py).
os.environ.setdefault("AUTH_REGISTER_RATE_LIMIT", "1000/60s")

from user_api.adapters.outbound.persistence.models import Base  # noqa: E402


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest_asyncio.fixture(scope="session")
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(postgres_url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture(scope="session")
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def clean_db_after_test(engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE email_verification_tokens, users"))


@pytest_asyncio.fixture
async def db_session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as session:
        yield session


class _RecordingEmailSender:
    """Test double for EmailSender: captures (to, plaintext_token) pairs
    directly via the Port instead of scraping application logs — the
    ConsoleEmailSender adapter masks the token in its log line (security
    fix), so tests that need the real plaintext token to drive
    GET /auth/confirm must get it from here, not from caplog."""

    def __init__(self, sink: list[tuple[str, str]]) -> None:
        self._sink = sink

    async def send_verification_email(self, to: str, token: str) -> None:
        self._sink.append((to, token))


@pytest.fixture
def sent_emails() -> list[tuple[str, str]]:
    return []


@pytest_asyncio.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession],
    sent_emails: list[tuple[str, str]],
) -> AsyncIterator[AsyncClient]:
    from user_api.adapters.inbound.http.app import app
    from user_api.adapters.inbound.http.auth_router import get_email_sender
    from user_api.adapters.outbound.persistence.session import get_db_session

    async def _override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_email_sender] = lambda: _RecordingEmailSender(sent_emails)
    # raise_app_exceptions=False: matches real server behavior for an
    # unhandled exception (ServerErrorMiddleware sends the 500 response,
    # then re-raises for server-side logging purposes only -- httpx's
    # default would surface that re-raise as a Python exception in the
    # test instead of the HTTP response the real client actually gets).
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": VALID_API_KEY}
