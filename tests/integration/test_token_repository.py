import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from user_api.adapters.outbound.persistence.repository import SqlAlchemyUserRepository
from user_api.adapters.outbound.persistence.token_repository import (
    SqlAlchemyEmailVerificationTokenRepository,
)
from user_api.domain.entities import EmailVerificationToken, User


def _make_user(email: str) -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(), name="Ada", email=email, password_hash="hash", created_at=now, updated_at=now
    )


def _make_token(
    user_id, *, token_hash: str, created_at: datetime, expires_at: datetime, used_at=None
) -> EmailVerificationToken:
    return EmailVerificationToken(
        id=uuid4(),
        user_id=user_id,
        token_hash=token_hash,
        created_at=created_at,
        expires_at=expires_at,
        used_at=used_at,
    )


async def test_get_latest_for_user_returns_none_when_no_tokens(db_session: AsyncSession) -> None:
    repo = SqlAlchemyEmailVerificationTokenRepository(db_session)

    assert await repo.get_latest_for_user(uuid4()) is None


async def test_get_latest_for_user_returns_most_recent(db_session: AsyncSession) -> None:
    users = SqlAlchemyUserRepository(db_session)
    tokens = SqlAlchemyEmailVerificationTokenRepository(db_session)
    user = _make_user("latest@example.com")
    await users.add(user)
    now = datetime.now(UTC)
    older = _make_token(
        user.id,
        token_hash="hash-old",
        created_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=23),
    )
    newer = _make_token(
        user.id, token_hash="hash-new", created_at=now, expires_at=now + timedelta(hours=24)
    )
    await tokens.add(older)
    await tokens.add(newer)

    latest = await tokens.get_latest_for_user(user.id)

    assert latest is not None
    assert latest.token_hash == "hash-new"


async def test_consume_and_verify_returns_none_for_unknown_hash(db_session: AsyncSession) -> None:
    repo = SqlAlchemyEmailVerificationTokenRepository(db_session)

    result = await repo.consume_and_verify("does-not-exist", datetime.now(UTC))

    assert result is None


async def test_consume_and_verify_returns_none_for_expired_token(db_session: AsyncSession) -> None:
    users = SqlAlchemyUserRepository(db_session)
    tokens = SqlAlchemyEmailVerificationTokenRepository(db_session)
    user = _make_user("expired@example.com")
    await users.add(user)
    now = datetime.now(UTC)
    token = _make_token(
        user.id,
        token_hash="hash-expired",
        created_at=now - timedelta(hours=25),
        expires_at=now - timedelta(hours=1),
    )
    await tokens.add(token)

    result = await tokens.consume_and_verify("hash-expired", now)

    assert result is None


async def test_consume_and_verify_returns_none_for_already_used_token(
    db_session: AsyncSession,
) -> None:
    users = SqlAlchemyUserRepository(db_session)
    tokens = SqlAlchemyEmailVerificationTokenRepository(db_session)
    user = _make_user("used@example.com")
    await users.add(user)
    now = datetime.now(UTC)
    token = _make_token(
        user.id,
        token_hash="hash-used",
        created_at=now,
        expires_at=now + timedelta(hours=24),
        used_at=now,
    )
    await tokens.add(token)

    result = await tokens.consume_and_verify("hash-used", now)

    assert result is None


async def test_consume_and_verify_returns_none_when_owning_user_soft_deleted(
    db_session: AsyncSession,
) -> None:
    """The token is otherwise valid, but the account was soft-deleted after
    issuance and before confirmation -- consume_and_verify must not verify a
    deleted account."""
    users = SqlAlchemyUserRepository(db_session)
    tokens = SqlAlchemyEmailVerificationTokenRepository(db_session)
    user = _make_user("deleted-owner@example.com")
    await users.add(user)
    now = datetime.now(UTC)
    token = _make_token(
        user.id, token_hash="hash-orphan", created_at=now, expires_at=now + timedelta(hours=24)
    )
    await tokens.add(token)
    await users.soft_delete(user.id, now)

    result = await tokens.consume_and_verify("hash-orphan", now)

    assert result is None


async def test_consume_and_verify_success_marks_token_used_and_verifies_user(
    db_session: AsyncSession,
) -> None:
    users = SqlAlchemyUserRepository(db_session)
    tokens = SqlAlchemyEmailVerificationTokenRepository(db_session)
    user = _make_user("confirm-direct@example.com")
    await users.add(user)
    now = datetime.now(UTC)
    token = _make_token(
        user.id, token_hash="hash-valid", created_at=now, expires_at=now + timedelta(hours=24)
    )
    await tokens.add(token)

    result = await tokens.consume_and_verify("hash-valid", now)

    assert result == user.id
    verified_user = await users.get_by_id(user.id)
    assert verified_user is not None
    assert verified_user.email_verified_at == now
    # Reuse must now fail: the token is marked used.
    assert await tokens.consume_and_verify("hash-valid", now) is None


async def test_consume_and_verify_concurrent_calls_only_one_succeeds(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Regression for the SELECT-then-UPDATE race (SC-004): two concurrent
    confirmations of the same token must never both succeed."""
    now = datetime.now(UTC)
    async with sessionmaker() as setup_session:
        users = SqlAlchemyUserRepository(setup_session)
        user = _make_user("race-confirm@example.com")
        await users.add(user)
        tokens = SqlAlchemyEmailVerificationTokenRepository(setup_session)
        token = _make_token(
            user.id, token_hash="hash-race", created_at=now, expires_at=now + timedelta(hours=24)
        )
        await tokens.add(token)

    async def _confirm() -> UUID | None:
        async with sessionmaker() as session:
            repo = SqlAlchemyEmailVerificationTokenRepository(session)
            return await repo.consume_and_verify("hash-race", now)

    results = await asyncio.gather(_confirm(), _confirm())

    assert sorted(results, key=lambda r: r is None) == [user.id, None]
