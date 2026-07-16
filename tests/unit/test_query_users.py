import uuid
from datetime import UTC, datetime

import pytest

from tests.unit.fakes import FakePasswordHasher, FakeUserRepository, FixedClock
from user_api.application.use_cases import CreateUser, GetUser, ListUsers
from user_api.domain.exceptions import UserNotFoundError


async def _create(repo: FakeUserRepository, email: str) -> None:
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    use_case = CreateUser(repository=repo, hasher=FakePasswordHasher(), clock=clock)
    await use_case.execute(name="User", email=email, password="supersecret")


async def test_get_user_returns_existing() -> None:
    repo = FakeUserRepository()
    await _create(repo, "a@example.com")
    [created] = (await repo.list_paginated(1, 10))[0]

    use_case = GetUser(repository=repo)
    user = await use_case.execute(created.id)

    assert user.email == "a@example.com"


async def test_get_user_not_found_raises() -> None:
    repo = FakeUserRepository()
    use_case = GetUser(repository=repo)

    with pytest.raises(UserNotFoundError):
        await use_case.execute(uuid.uuid4())


async def test_list_users_paginates() -> None:
    repo = FakeUserRepository()
    for i in range(5):
        await _create(repo, f"user{i}@example.com")

    use_case = ListUsers(repository=repo)
    items, total = await use_case.execute(page=1, page_size=2)

    assert total == 5
    assert len(items) == 2
