from datetime import UTC, datetime, timedelta

import pytest

from tests.unit.fakes import (
    CountingPasswordHasher,
    FakeEmailSender,
    FakeEmailVerificationTokenRepository,
    FakePasswordHasher,
    FakeTokenGenerator,
    FakeUserRepository,
    FixedClock,
)
from user_api.application.registration_use_cases import RegisterUser
from user_api.domain.entities import User
from user_api.domain.exceptions import DuplicateEmailError, WeakPasswordError

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _make_use_case(now: datetime = NOW):
    repo = FakeUserRepository()
    tokens = FakeEmailVerificationTokenRepository(repo)
    email_sender = FakeEmailSender()
    use_case = RegisterUser(
        repository=repo,
        token_repository=tokens,
        hasher=FakePasswordHasher(),
        token_generator=FakeTokenGenerator(),
        email_sender=email_sender,
        clock=FixedClock(now),
    )
    return use_case, repo, tokens, email_sender


async def test_register_new_email_creates_pending_user_and_sends_token() -> None:
    use_case, repo, tokens, email_sender = _make_use_case()

    await use_case.execute(name="Ada", email="ada@example.com", password="supersecret")

    user = await repo.get_by_email_including_pending("ada@example.com")
    assert user is not None
    assert user.email_verified_at is None
    assert user.password_hash == "hashed:supersecret"
    assert email_sender.sent == [("ada@example.com", "token-1")]
    token = await tokens.get_latest_for_user(user.id)
    assert token is not None
    assert token.expires_at == NOW + timedelta(hours=24)


async def test_register_weak_password_raises_and_persists_nothing() -> None:
    use_case, repo, _, email_sender = _make_use_case()

    with pytest.raises(WeakPasswordError):
        await use_case.execute(name="Ada", email="ada@example.com", password="short")

    assert await repo.get_by_email_including_pending("ada@example.com") is None
    assert email_sender.sent == []


async def test_register_already_active_email_is_silent_noop() -> None:
    """SC-001/FR-010: registering an already-active email returns silently,
    no new token issued, no error raised."""
    use_case, repo, tokens, email_sender = _make_use_case()
    await use_case.execute(name="Ada", email="ada@example.com", password="supersecret")
    user = await repo.get_by_email_including_pending("ada@example.com")
    user.email_verified_at = NOW  # direct entity mutation: FakeUserRepository stores by reference

    await use_case.execute(name="Ada 2", email="ada@example.com", password="anotherpass")

    assert email_sender.sent == [("ada@example.com", "token-1")]  # no second send


async def test_register_pending_email_reissues_token_outside_cooldown() -> None:
    """Edge case (spec.md): re-POSTing a pending email reissues a token."""
    use_case, repo, tokens, email_sender = _make_use_case()
    await use_case.execute(name="Ada", email="ada@example.com", password="supersecret")

    later = NOW + timedelta(seconds=61)
    use_case2, _, _, _ = _make_use_case(now=later)
    use_case2.repository = repo
    use_case2.token_repository = tokens
    use_case2.email_sender = email_sender
    await use_case2.execute(name="Ada", email="ada@example.com", password="differentpass")

    assert len(email_sender.sent) == 2


async def test_register_pending_email_within_cooldown_does_not_reissue() -> None:
    """FR-009: register-on-pending path respects the same 60s cooldown as
    resend, but always returns silently (no 429 here, unlike /resend)."""
    use_case, repo, tokens, email_sender = _make_use_case()
    await use_case.execute(name="Ada", email="ada@example.com", password="supersecret")

    soon = NOW + timedelta(seconds=30)
    use_case2, _, _, _ = _make_use_case(now=soon)
    use_case2.repository = repo
    use_case2.token_repository = tokens
    use_case2.email_sender = email_sender
    await use_case2.execute(name="Ada", email="ada@example.com", password="differentpass")

    assert len(email_sender.sent) == 1  # no second send, still no exception


async def test_register_pending_email_does_not_overwrite_password() -> None:
    """Edge case (spec.md): password from a duplicate POST never overwrites
    the pending account's original password."""
    use_case, repo, _, _ = _make_use_case()
    await use_case.execute(name="Ada", email="ada@example.com", password="supersecret")
    original = await repo.get_by_email_including_pending("ada@example.com")

    later = NOW + timedelta(seconds=61)
    use_case2, _, _, _ = _make_use_case(now=later)
    use_case2.repository = repo
    use_case2.token_repository = FakeEmailVerificationTokenRepository(repo)
    await use_case2.execute(name="Ada", email="ada@example.com", password="attackerpass")

    unchanged = await repo.get_by_email_including_pending("ada@example.com")
    assert unchanged.password_hash == original.password_hash


async def test_register_concurrent_add_race_swallows_duplicate_email_silently() -> None:
    """FR-010 regression: two concurrent registrations of the same new email
    can both pass get_by_email_including_pending before either commits; the
    repository's UNIQUE constraint (DuplicateEmailError) is the real guard,
    and the loser must still return silently, not leak a 409."""

    class _RaceRepository(FakeUserRepository):
        async def add(self, user: User) -> None:
            raise DuplicateEmailError(user.email)

    repo = _RaceRepository()
    tokens = FakeEmailVerificationTokenRepository(repo)
    email_sender = FakeEmailSender()
    use_case = RegisterUser(
        repository=repo,
        token_repository=tokens,
        hasher=FakePasswordHasher(),
        token_generator=FakeTokenGenerator(),
        email_sender=email_sender,
        clock=FixedClock(NOW),
    )

    await use_case.execute(name="Ada", email="race@example.com", password="supersecret")

    assert email_sender.sent == []  # loser never sends a confirmation token


async def test_register_hashes_password_exactly_once_regardless_of_email_existence() -> None:
    """Timing-leak regression: hashing must run on both the new-email path
    and the already-registered path, so the two responses take the same
    time and don't let a caller distinguish "new" from "existing" by
    latency."""
    hasher = CountingPasswordHasher()
    repo = FakeUserRepository()
    tokens = FakeEmailVerificationTokenRepository(repo)
    use_case_new = RegisterUser(
        repository=repo,
        token_repository=tokens,
        hasher=hasher,
        token_generator=FakeTokenGenerator(),
        email_sender=FakeEmailSender(),
        clock=FixedClock(NOW),
    )
    await use_case_new.execute(name="Ada", email="timing@example.com", password="supersecret")
    assert hasher.calls == 1

    use_case_existing = RegisterUser(
        repository=repo,
        token_repository=tokens,
        hasher=hasher,
        token_generator=FakeTokenGenerator(),
        email_sender=FakeEmailSender(),
        clock=FixedClock(NOW + timedelta(seconds=61)),
    )
    await use_case_existing.execute(name="Ada", email="timing@example.com", password="anotherpw")
    assert hasher.calls == 2
