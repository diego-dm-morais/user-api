"""Domain entities. No framework imports allowed here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class User:
    id: UUID
    name: str
    email: str
    password_hash: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    email_verified_at: datetime | None = None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


@dataclass
class EmailVerificationToken:
    id: UUID
    user_id: UUID
    token_hash: str  # sha256(token); plaintext token is never persisted
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None

    def is_valid(self, now: datetime) -> bool:
        return self.used_at is None and now < self.expires_at
