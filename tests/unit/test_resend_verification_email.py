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
from user_api.application.registration_use_cases import RegisterUser, ResendVerificationEmail
from user_api.domain.exceptions import ResendCooldownError

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _register(repo, tokens, email_sender, now=NOW):
    use_case = RegisterUser(
        repository=repo,
        token_repository=tokens,
        hasher=FakePasswordHasher(),
        token_generator=FakeTokenGenerator(),
        email_sender=email_sender,
        clock=FixedClock(now),
    )
    await use_case.execute(name="Ada", email="ada@example.com", password="supersecret")


async def test_resend_unknown_email_is_silent_noop() -> None:
    """US3.3/FR-010: unknown email returns silently, no error, no send."""
    repo = FakeUserRepository()
    tokens = FakeEmailVerificationTokenRepository(repo)
    email_sender = FakeEmailSender()
    use_case = ResendVerificationEmail(
        repository=repo,
        token_repository=tokens,
        token_generator=FakeTokenGenerator(),
        email_sender=email_sender,
        clock=FixedClock(NOW),
    )

    await use_case.execute("nobody@example.com")

    assert email_sender.sent == []


async def test_resend_already_active_email_is_silent_noop() -> None:
    repo = FakeUserRepository()
    tokens = FakeEmailVerificationTokenRepository(repo)
    email_sender = FakeEmailSender()
    await _register(repo, tokens, email_sender)
    user = await repo.get_by_email_including_pending("ada@example.com")
    user.email_verified_at = NOW  # direct entity mutation: FakeUserRepository stores by reference

    use_case = ResendVerificationEmail(
        repository=repo,
        token_repository=tokens,
        token_generator=FakeTokenGenerator(),
        email_sender=email_sender,
        clock=FixedClock(NOW),
    )
    await use_case.execute("ada@example.com")

    assert len(email_sender.sent) == 1  # only the original registration send


async def test_resend_pending_email_outside_cooldown_issues_new_token() -> None:
    """US3.1: resend for a pending account issues a new token, returns success."""
    repo = FakeUserRepository()
    tokens = FakeEmailVerificationTokenRepository(repo)
    email_sender = FakeEmailSender()
    await _register(repo, tokens, email_sender)

    later = NOW + timedelta(seconds=61)
    use_case = ResendVerificationEmail(
        repository=repo,
        token_repository=tokens,
        token_generator=FakeTokenGenerator(),
        email_sender=email_sender,
        clock=FixedClock(later),
    )
    await use_case.execute("ada@example.com")

    assert len(email_sender.sent) == 2


async def test_resend_within_cooldown_raises_429_exception() -> None:
    """SC-005/US3.2: second resend within 60s raises ResendCooldownError (429)."""
    repo = FakeUserRepository()
    tokens = FakeEmailVerificationTokenRepository(repo)
    email_sender = FakeEmailSender()
    await _register(repo, tokens, email_sender)

    soon = NOW + timedelta(seconds=30)
    use_case = ResendVerificationEmail(
        repository=repo,
        token_repository=tokens,
        token_generator=FakeTokenGenerator(),
        email_sender=email_sender,
        clock=FixedClock(soon),
    )

    with pytest.raises(ResendCooldownError):
        await use_case.execute("ada@example.com")

    assert len(email_sender.sent) == 1  # exactly 1 email actually sent (SC-005)
