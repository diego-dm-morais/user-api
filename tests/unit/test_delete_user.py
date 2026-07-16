import uuid
from datetime import UTC, datetime

import pytest

from tests.unit.fakes import FakePasswordHasher, FakeUserRepository, FixedClock
from user_api.application.use_cases import CreateUser, DeleteUser
from user_api.domain.exceptions import UserNotFoundError


async def _create(repo: FakeUserRepository):
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    use_case = CreateUser(repository=repo, hasher=FakePasswordHasher(), clock=clock)
    return await use_case.execute(name="User", email="a@example.com", password="supersecret")


async def test_delete_user_soft_deletes() -> None:
    repo = FakeUserRepository()
    user = await _create(repo)
    use_case = DeleteUser(repository=repo, clock=FixedClock(datetime(2026, 1, 2, tzinfo=UTC)))

    await use_case.execute(user.id)

    assert await repo.get_by_id(user.id) is None


async def test_delete_user_not_found_raises() -> None:
    repo = FakeUserRepository()
    use_case = DeleteUser(repository=repo, clock=FixedClock(datetime(2026, 1, 1, tzinfo=UTC)))

    with pytest.raises(UserNotFoundError):
        await use_case.execute(uuid.uuid4())


async def test_delete_user_twice_raises_not_found() -> None:
    repo = FakeUserRepository()
    user = await _create(repo)
    use_case = DeleteUser(repository=repo, clock=FixedClock(datetime(2026, 1, 2, tzinfo=UTC)))
    await use_case.execute(user.id)

    with pytest.raises(UserNotFoundError):
        await use_case.execute(user.id)
