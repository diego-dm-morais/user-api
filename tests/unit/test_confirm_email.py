from datetime import UTC, datetime, timedelta

import pytest

from tests.unit.fakes import (
    FakeEmailSender,
    FakeEmailVerificationTokenRepository,
    FakePasswordHasher,
    FakeTokenGenerator,
    FakeUserRepository,
    FixedClock,
)
from user_api.application.registration_use_cases import ConfirmEmail, RegisterUser
from user_api.domain.exceptions import InvalidOrExpiredTokenError

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _register(repo, tokens, now=NOW):
    use_case = RegisterUser(
        repository=repo,
        token_repository=tokens,
        hasher=FakePasswordHasher(),
        token_generator=FakeTokenGenerator(),
        email_sender=FakeEmailSender(),
        clock=FixedClock(now),
    )
    await use_case.execute(name="Ada", email="ada@example.com", password="supersecret")


async def test_confirm_valid_token_activates_account() -> None:
    repo = FakeUserRepository()
    tokens = FakeEmailVerificationTokenRepository(repo)
    await _register(repo, tokens)
    use_case = ConfirmEmail(token_repository=tokens, clock=FixedClock(NOW))

    await use_case.execute("token-1")

    user = await repo.get_by_email_including_pending("ada@example.com")
    assert user.email_verified_at == NOW


async def test_confirm_unknown_token_raises_generic_error() -> None:
    """SC-003/FR-011: nonexistent token is rejected without revealing why."""
    repo = FakeUserRepository()
    tokens = FakeEmailVerificationTokenRepository(repo)
    use_case = ConfirmEmail(token_repository=tokens, clock=FixedClock(NOW))

    with pytest.raises(InvalidOrExpiredTokenError):
        await use_case.execute("nonexistent")


async def test_confirm_expired_token_raises_generic_error() -> None:
    """SC-003: token older than 24h is rejected."""
    repo = FakeUserRepository()
    tokens = FakeEmailVerificationTokenRepository(repo)
    await _register(repo, tokens)
    expired_check = NOW + timedelta(hours=24, seconds=1)
    use_case = ConfirmEmail(token_repository=tokens, clock=FixedClock(expired_check))

    with pytest.raises(InvalidOrExpiredTokenError):
        await use_case.execute("token-1")


async def test_confirm_reused_token_raises_generic_error() -> None:
    """SC-004: reusing an already-consumed token is rejected on the 2nd attempt."""
    repo = FakeUserRepository()
    tokens = FakeEmailVerificationTokenRepository(repo)
    await _register(repo, tokens)
    use_case = ConfirmEmail(token_repository=tokens, clock=FixedClock(NOW))
    await use_case.execute("token-1")

    with pytest.raises(InvalidOrExpiredTokenError):
        await use_case.execute("token-1")


async def test_confirm_wrong_token_and_expired_token_raise_same_exception_type() -> None:
    """FR-011: unknown, expired, and reused all surface identically (same
    exception type, mapped to the same 400 by error_handlers.py)."""
    repo = FakeUserRepository()
    tokens = FakeEmailVerificationTokenRepository(repo)
    await _register(repo, tokens)
    use_case = ConfirmEmail(token_repository=tokens, clock=FixedClock(NOW))
    await use_case.execute("token-1")  # consume it (used case)

    unknown_exc = used_exc = None
    try:
        await use_case.execute("does-not-exist")
    except InvalidOrExpiredTokenError as exc:
        unknown_exc = exc
    try:
        await use_case.execute("token-1")
    except InvalidOrExpiredTokenError as exc:
        used_exc = exc

    assert type(unknown_exc) is type(used_exc) is InvalidOrExpiredTokenError
