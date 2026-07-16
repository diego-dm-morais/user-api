"""Ports (Protocols) the application layer depends on. No framework imports."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from user_api.domain.entities import EmailVerificationToken, User


class UserRepository(Protocol):
    async def add(self, user: User) -> None: ...

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Returns the active user (deleted_at IS NULL) or None."""
        ...

    async def get_by_email_including_pending(self, email: str) -> User | None:
        """Returns the user with this email (deleted_at IS NULL), active or pending
        (email_verified_at IS NULL) — used by the registration/resend flow (FR-009/FR-010)."""
        ...

    async def list_paginated(self, page: int, page_size: int) -> tuple[list[User], int]:
        """Returns (items, total) for active users only, ordered by created_at."""
        ...

    async def update(self, user: User) -> None:
        """Persists all mutable fields of `user` (name, email, password_hash, updated_at)."""
        ...

    async def soft_delete(self, user_id: UUID, deleted_at: datetime) -> bool:
        """Marks the active user as deleted. Returns False if not found/already deleted."""
        ...

    async def reset_email_verification(self, user_id: UUID) -> None:
        """Atomically clears email_verified_at (e.g. after an email address
        change requires re-confirmation). No-op if user not found. Sole
        writer of this column outside EmailVerificationTokenRepository.
        consume_and_verify -- update() never touches it, to avoid a
        lost-update race between the two."""
        ...


class EmailVerificationTokenRepository(Protocol):
    async def add(self, token: EmailVerificationToken) -> None: ...

    async def get_latest_for_user(self, user_id: UUID) -> EmailVerificationToken | None:
        """Returns the most recently created token for this user, or None."""
        ...

    async def consume_and_verify(self, token_hash: str, now: datetime) -> UUID | None:
        """Atomically marks the token used and the owning user as verified
        (ADR-004). Returns the user_id on success, or None if the token is
        nonexistent, expired, already used, or the owning user has been
        soft-deleted in the meantime (FR-011 — caller never learns which)."""
        ...


class PasswordHasher(Protocol):
    def hash(self, plain_password: str) -> str: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class TokenGenerator(Protocol):
    def generate(self) -> str:
        """Returns a high-entropy, URL-safe token in plaintext."""
        ...


class EmailSender(Protocol):
    async def send_verification_email(self, to: str, token: str) -> None:
        """Sends the confirmation link/token. Failures should raise; the
        caller does not roll back account creation on send failure."""
        ...
