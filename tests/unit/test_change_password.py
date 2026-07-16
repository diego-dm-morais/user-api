import uuid
from datetime import UTC, datetime

import pytest

from tests.unit.fakes import FakePasswordHasher, FakeUserRepository, FixedClock
from user_api.application.use_cases import ChangePassword, CreateUser
from user_api.domain.exceptions import UserNotFoundError, WeakPasswordError


async def _create(repo: FakeUserRepository):
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    use_case = CreateUser(repository=repo, hasher=FakePasswordHasher(), clock=clock)
    return await use_case.execute(name="User", email="a@example.com", password="supersecret")


async def test_change_password_success_never_returns_plain_password() -> None:
    repo = FakeUserRepository()
    user = await _create(repo)
    use_case = ChangePassword(
        repository=repo,
        hasher=FakePasswordHasher(),
        clock=FixedClock(datetime(2026, 1, 2, tzinfo=UTC)),
    )

    updated = await use_case.execute(user.id, new_password="newsecretpw")

    assert updated.password_hash == "hashed:newsecretpw"
    assert not hasattr(updated, "new_password")


async def test_change_password_weak_password_raises() -> None:
    repo = FakeUserRepository()
    user = await _create(repo)
    use_case = ChangePassword(
        repository=repo,
        hasher=FakePasswordHasher(),
        clock=FixedClock(datetime(2026, 1, 2, tzinfo=UTC)),
    )

    with pytest.raises(WeakPasswordError):
        await use_case.execute(user.id, new_password="short")


async def test_change_password_not_found_raises() -> None:
    repo = FakeUserRepository()
    use_case = ChangePassword(
        repository=repo,
        hasher=FakePasswordHasher(),
        clock=FixedClock(datetime(2026, 1, 1, tzinfo=UTC)),
    )

    with pytest.raises(UserNotFoundError):
        await use_case.execute(uuid.uuid4(), new_password="supersecret")
