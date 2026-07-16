import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from user_api.adapters.outbound.persistence.repository import SqlAlchemyUserRepository
from user_api.domain.entities import User
from user_api.domain.exceptions import DuplicateEmailError


def _make_user(email: str) -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(), name="Ada", email=email, password_hash="hash", created_at=now, updated_at=now
    )


async def test_concurrent_create_same_email_one_succeeds_one_conflicts(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    email = "race@example.com"

    async def _create() -> bool:
        async with sessionmaker() as session:
            repo = SqlAlchemyUserRepository(session)
            try:
                await repo.add(_make_user(email))
                return True
            except DuplicateEmailError:
                return False

    results = await asyncio.gather(_create(), _create())

    assert sorted(results) == [False, True]
