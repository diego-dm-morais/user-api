import uuid
from datetime import UTC, datetime

import pytest

from tests.unit.fakes import FakePasswordHasher, FakeUserRepository, FixedClock
from user_api.application.use_cases import CreateUser, UpdateUser
from user_api.domain.exceptions import DuplicateEmailError, UserNotFoundError


async def _create(repo: FakeUserRepository, email: str):
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    use_case = CreateUser(repository=repo, hasher=FakePasswordHasher(), clock=clock)
    return await use_case.execute(name="User", email=email, password="supersecret")


async def test_update_user_changes_only_provided_fields() -> None:
    repo = FakeUserRepository()
    user = await _create(repo, "a@example.com")
    use_case = UpdateUser(repository=repo, clock=FixedClock(datetime(2026, 1, 2, tzinfo=UTC)))

    updated = await use_case.execute(user.id, name="New Name")

    assert updated.name == "New Name"
    assert updated.email == "a@example.com"


async def test_update_user_duplicate_email_raises() -> None:
    repo = FakeUserRepository()
    await _create(repo, "a@example.com")
    user2 = await _create(repo, "b@example.com")
    use_case = UpdateUser(repository=repo, clock=FixedClock(datetime(2026, 1, 2, tzinfo=UTC)))

    with pytest.raises(DuplicateEmailError):
        await use_case.execute(user2.id, email="a@example.com")


async def test_update_user_not_found_raises() -> None:
    repo = FakeUserRepository()
    use_case = UpdateUser(repository=repo, clock=FixedClock(datetime(2026, 1, 1, tzinfo=UTC)))

    with pytest.raises(UserNotFoundError):
        await use_case.execute(uuid.uuid4(), name="X")


async def test_update_user_email_change_resets_email_verified() -> None:
    """Regression: changing the email must invalidate the prior confirmation
    -- the old proof-of-ownership doesn't cover the new address."""
    repo = FakeUserRepository()
    user = await _create(repo, "a@example.com")
    assert user.email_verified_at is not None  # 001/plan.md ADR-006
    use_case = UpdateUser(repository=repo, clock=FixedClock(datetime(2026, 1, 2, tzinfo=UTC)))

    updated = await use_case.execute(user.id, email="new-address@example.com")

    assert updated.email == "new-address@example.com"
    assert updated.email_verified_at is None
    assert updated.email_verified is False
    # Lost-update fix: persisted via the dedicated atomic method, not update().
    assert repo.reset_email_verification_calls == [user.id]


async def test_update_user_same_email_does_not_reset_email_verified() -> None:
    """Re-submitting the same email (e.g. an unrelated name-only PATCH that
    still echoes email) must not spuriously un-verify the account."""
    repo = FakeUserRepository()
    user = await _create(repo, "a@example.com")
    use_case = UpdateUser(repository=repo, clock=FixedClock(datetime(2026, 1, 2, tzinfo=UTC)))

    updated = await use_case.execute(user.id, email="a@example.com")

    assert updated.email_verified_at is not None
    assert updated.email_verified is True
    assert repo.reset_email_verification_calls == []
