"""Registration/confirmation use cases for the public self-signup flow
(distinct from the admin flow in use_cases.py — see plan.md)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from user_api.application.use_cases import _check_password_policy
from user_api.domain.entities import EmailVerificationToken, User
from user_api.domain.exceptions import (
    DuplicateEmailError,
    InvalidOrExpiredTokenError,
    ResendCooldownError,
)
from user_api.domain.ports import (
    Clock,
    EmailSender,
    EmailVerificationTokenRepository,
    PasswordHasher,
    TokenGenerator,
    UserRepository,
)

TOKEN_TTL_HOURS = 24
RESEND_COOLDOWN_SECONDS = 60


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _in_cooldown(last: EmailVerificationToken | None, now: datetime) -> bool:
    if last is None:
        return False
    return (now - last.created_at).total_seconds() < RESEND_COOLDOWN_SECONDS


async def _issue_token(
    user: User,
    now: datetime,
    token_repository: EmailVerificationTokenRepository,
    token_generator: TokenGenerator,
    email_sender: EmailSender,
) -> None:
    plaintext = token_generator.generate()
    token = EmailVerificationToken(
        id=uuid4(),
        user_id=user.id,
        token_hash=_hash_token(plaintext),
        created_at=now,
        expires_at=now + timedelta(hours=TOKEN_TTL_HOURS),
    )
    await token_repository.add(token)
    await email_sender.send_verification_email(user.email, plaintext)


@dataclass
class RegisterUser:
    repository: UserRepository
    token_repository: EmailVerificationTokenRepository
    hasher: PasswordHasher
    token_generator: TokenGenerator
    email_sender: EmailSender
    clock: Clock

    async def execute(self, name: str, email: str, password: str) -> None:
        _check_password_policy(password)
        # Always hash, even on the existing-email branch that never persists
        # it: hashing is the expensive step (~50ms argon2id), so skipping it
        # only for "email already taken" makes that branch measurably faster
        # than "new email" and leaks account existence via response timing.
        password_hash = self.hasher.hash(password)
        existing = await self.repository.get_by_email_including_pending(email)
        if existing is not None:
            if existing.email_verified_at is None:
                # FR-009: same 60s cooldown check as ResendVerificationEmail,
                # but no 429 here — always silent (FR-010, no bypass exception).
                last = await self.token_repository.get_latest_for_user(existing.id)
                now = self.clock.now()
                if not _in_cooldown(last, now):
                    await _issue_token(
                        existing,
                        now,
                        self.token_repository,
                        self.token_generator,
                        self.email_sender,
                    )
            return  # FR-010: always silent, whether active, pending, or cooldown-skipped

        now = self.clock.now()
        user = User(
            id=uuid4(),
            name=name,
            email=email,
            password_hash=password_hash,
            created_at=now,
            updated_at=now,
            email_verified_at=None,
        )
        try:
            await self.repository.add(user)
        except DuplicateEmailError:
            # FR-010: two concurrent registrations of the same new email can
            # both pass the get_by_email_including_pending check above before
            # either commits; the DB's UNIQUE constraint is the real guard.
            # The loser must still return silently, never leak the 409 the
            # repository raises (that's only for the authenticated admin
            # flow in 001, where FR-002 wants an explicit conflict).
            return
        await _issue_token(
            user, now, self.token_repository, self.token_generator, self.email_sender
        )


@dataclass
class ConfirmEmail:
    token_repository: EmailVerificationTokenRepository
    clock: Clock

    async def execute(self, token: str) -> None:
        now = self.clock.now()
        user_id = await self.token_repository.consume_and_verify(_hash_token(token), now)
        if user_id is None:
            raise InvalidOrExpiredTokenError()


@dataclass
class ResendVerificationEmail:
    repository: UserRepository
    token_repository: EmailVerificationTokenRepository
    token_generator: TokenGenerator
    email_sender: EmailSender
    clock: Clock

    async def execute(self, email: str) -> None:
        user = await self.repository.get_by_email_including_pending(email)
        if user is None or user.email_verified_at is not None:
            return  # FR-010: silent success, no account-existence signal

        last = await self.token_repository.get_latest_for_user(user.id)
        now = self.clock.now()
        if _in_cooldown(last, now):
            raise ResendCooldownError()  # FR-009/FR-010 documented exception: 429

        await _issue_token(
            user, now, self.token_repository, self.token_generator, self.email_sender
        )
