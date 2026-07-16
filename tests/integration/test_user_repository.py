from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from user_api.adapters.outbound.persistence.repository import SqlAlchemyUserRepository
from user_api.domain.entities import User
from user_api.domain.exceptions import DuplicateEmailError, UserNotFoundError


def _make_user(email: str) -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        name="Ada",
        email=email,
        password_hash="hash",
        created_at=now,
        updated_at=now,
    )


async def test_add_and_get_by_id(db_session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(db_session)
    user = _make_user("ada@example.com")

    await repo.add(user)
    fetched = await repo.get_by_id(user.id)

    assert fetched is not None
    assert fetched.email == "ada@example.com"


async def test_add_duplicate_email_raises_via_unique_constraint(db_session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(db_session)
    await repo.add(_make_user("dup@example.com"))

    with pytest.raises(DuplicateEmailError):
        await repo.add(_make_user("dup@example.com"))


async def test_soft_deleted_user_not_returned_by_get_by_id(db_session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(db_session)
    user = _make_user("del@example.com")
    await repo.add(user)

    deleted = await repo.soft_delete(user.id, datetime.now(UTC))

    assert deleted is True
    assert await repo.get_by_id(user.id) is None


async def test_soft_delete_email_reusable_after_delete(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        repo = SqlAlchemyUserRepository(session)
        user = _make_user("reuse@example.com")
        await repo.add(user)
        await repo.soft_delete(user.id, datetime.now(UTC))

    async with sessionmaker() as session:
        repo = SqlAlchemyUserRepository(session)
        await repo.add(_make_user("reuse@example.com"))


async def test_get_by_email_including_pending_returns_unverified_user(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyUserRepository(db_session)
    user = _make_user("pending@example.com")
    await repo.add(user)

    fetched = await repo.get_by_email_including_pending("pending@example.com")

    assert fetched is not None
    assert fetched.email_verified_at is None


async def test_reset_email_verification_clears_timestamp(db_session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(db_session)
    user = _make_user("verify@example.com")
    user.email_verified_at = datetime.now(UTC)
    await repo.add(user)

    await repo.reset_email_verification(user.id)

    fetched = await repo.get_by_id(user.id)
    assert fetched is not None
    assert fetched.email_verified_at is None


async def test_reset_email_verification_is_noop_for_unknown_user(db_session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(db_session)

    # Must not raise: unknown id is silently ignored (defensive, no caller today
    # invokes this on a missing user, but the Port makes no promise otherwise).
    await repo.reset_email_verification(uuid4())


async def test_update_does_not_touch_email_verified_at(db_session: AsyncSession) -> None:
    """Lost-update regression (ALTO 1): update() must never write
    email_verified_at -- consume_and_verify (token_repository.py) is the
    sole owner outside reset_email_verification. Simulates the race: read
    a verified user, confirm email concurrently (writes directly to the
    row), then let the stale in-memory update() commit -- confirmation
    must survive."""
    repo = SqlAlchemyUserRepository(db_session)
    user = _make_user("lost-update@example.com")
    await repo.add(user)
    stale_snapshot = await repo.get_by_id(user.id)
    assert stale_snapshot is not None
    assert stale_snapshot.email_verified_at is None

    # Concurrent confirmation happens after the snapshot was read.
    when = datetime.now(UTC)
    await db_session.execute(
        text("UPDATE users SET email_verified_at = :when WHERE id = :id"),
        {"when": when, "id": user.id},
    )
    await db_session.commit()

    # The other use case finishes its update() using the stale snapshot.
    stale_snapshot.name = "New Name"
    await repo.update(stale_snapshot)

    fetched = await repo.get_by_id(user.id)
    assert fetched is not None
    assert fetched.name == "New Name"
    assert fetched.email_verified_at == when  # not reverted to None


async def test_update_raises_not_found_when_user_missing(db_session: AsyncSession) -> None:
    """Repository-level guard for a TOCTOU race: the row can vanish between
    the use case's get_by_id check and this update() call (e.g. concurrent
    delete). UpdateUser always checks existence first, so this branch is
    unreachable through the HTTP layer today; exercised directly here."""
    repo = SqlAlchemyUserRepository(db_session)
    ghost = _make_user("ghost@example.com")

    with pytest.raises(UserNotFoundError):
        await repo.update(ghost)


async def test_soft_delete_returns_false_for_unknown_user(db_session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(db_session)

    assert await repo.soft_delete(uuid4(), datetime.now(UTC)) is False


async def test_update_persists_name_and_email_changes(db_session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(db_session)
    user = _make_user("update-direct@example.com")
    await repo.add(user)

    user.name = "New Name"
    user.email = "updated-direct@example.com"
    user.updated_at = datetime.now(UTC)
    await repo.update(user)

    fetched = await repo.get_by_id(user.id)
    assert fetched is not None
    assert fetched.name == "New Name"
    assert fetched.email == "updated-direct@example.com"


async def test_update_raises_duplicate_email_via_unique_constraint(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyUserRepository(db_session)
    await repo.add(_make_user("taken-direct@example.com"))
    other = _make_user("free-direct@example.com")
    await repo.add(other)

    other.email = "taken-direct@example.com"
    with pytest.raises(DuplicateEmailError):
        await repo.update(other)


async def test_list_paginated_returns_page_and_total(db_session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(db_session)
    for i in range(3):
        await repo.add(_make_user(f"page{i}@example.com"))

    items, total = await repo.list_paginated(page=1, page_size=2)

    assert total == 3
    assert len(items) == 2
