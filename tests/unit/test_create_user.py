from datetime import UTC, datetime

import pytest

from tests.unit.fakes import FakePasswordHasher, FakeUserRepository, FixedClock
from user_api.application.use_cases import CreateUser
from user_api.domain.exceptions import DuplicateEmailError, WeakPasswordError


def _make_use_case() -> tuple[CreateUser, FakeUserRepository]:
    repo = FakeUserRepository()
    use_case = CreateUser(
        repository=repo,
        hasher=FakePasswordHasher(),
        clock=FixedClock(datetime(2026, 1, 1, tzinfo=UTC)),
    )
    return use_case, repo


async def test_create_user_success_hashes_password_and_persists() -> None:
    use_case, repo = _make_use_case()

    user = await use_case.execute(name="Ada", email="ada@example.com", password="supersecret")

    assert user.password_hash == "hashed:supersecret"
    assert user.email == "ada@example.com"
    assert await repo.get_by_id(user.id) == user


async def test_create_user_is_marked_email_verified_at_creation() -> None:
    """001/plan.md ADR-006: admin-created accounts are trusted (API key
    caller) and never go through email confirmation, so they're verified
    immediately, consistent with 002/plan.md ADR-001's backfill decision."""
    use_case, _ = _make_use_case()

    user = await use_case.execute(name="Ada", email="ada@example.com", password="supersecret")

    assert user.email_verified_at is not None
    assert user.email_verified is True


async def test_create_user_duplicate_email_raises() -> None:
    use_case, _ = _make_use_case()
    await use_case.execute(name="Ada", email="ada@example.com", password="supersecret")

    with pytest.raises(DuplicateEmailError):
        await use_case.execute(name="Ada 2", email="ada@example.com", password="anotherpass")


async def test_create_user_weak_password_raises() -> None:
    use_case, _ = _make_use_case()

    with pytest.raises(WeakPasswordError):
        await use_case.execute(name="Ada", email="ada@example.com", password="short")
