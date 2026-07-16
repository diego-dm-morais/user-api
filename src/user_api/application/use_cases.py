"""Use cases: orchestrate ports only. No SQL/HTTP here."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from user_api.domain.entities import User
from user_api.domain.exceptions import UserNotFoundError, WeakPasswordError
from user_api.domain.ports import Clock, PasswordHasher, UserRepository

MIN_PASSWORD_LENGTH = 8


def _check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(MIN_PASSWORD_LENGTH)


@dataclass
class CreateUser:
    repository: UserRepository
    hasher: PasswordHasher
    clock: Clock

    async def execute(self, name: str, email: str, password: str) -> User:
        _check_password_policy(password)
        now = self.clock.now()
        user = User(
            id=uuid4(),
            name=name,
            email=email,
            password_hash=self.hasher.hash(password),
            created_at=now,
            updated_at=now,
            # Admin-created accounts are trusted (API key caller, ADR-004 of
            # 001/plan.md) and never go through email confirmation, so they
            # are considered verified at creation — see 001/plan.md ADR-006,
            # consistent with the backfill decision in 002/plan.md ADR-001.
            email_verified_at=now,
        )
        await self.repository.add(user)
        return user


@dataclass
class GetUser:
    repository: UserRepository

    async def execute(self, user_id: UUID) -> User:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user


@dataclass
class ListUsers:
    repository: UserRepository

    async def execute(self, page: int, page_size: int) -> tuple[list[User], int]:
        return await self.repository.list_paginated(page, page_size)


@dataclass
class UpdateUser:
    repository: UserRepository
    clock: Clock

    async def execute(
        self, user_id: UUID, name: str | None = None, email: str | None = None
    ) -> User:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)

        if name is not None:
            user.name = name
        email_changed = email is not None and email != user.email
        if email_changed and email is not None:
            user.email = email
            # Email changed: the previous confirmation no longer proves
            # ownership of the new address, so it must be re-confirmed.
            # Reflected in memory for the response; persisted via a
            # dedicated atomic UPDATE below, never through update() (that
            # would race with EmailVerificationTokenRepository.
            # consume_and_verify writing the same column concurrently).
            user.email_verified_at = None
        user.updated_at = self.clock.now()

        await self.repository.update(user)
        if email_changed:
            await self.repository.reset_email_verification(user.id)
        return user


@dataclass
class ChangePassword:
    repository: UserRepository
    hasher: PasswordHasher
    clock: Clock

    async def execute(self, user_id: UUID, new_password: str) -> User:
        _check_password_policy(new_password)
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)

        user.password_hash = self.hasher.hash(new_password)
        user.updated_at = self.clock.now()

        await self.repository.update(user)
        return user


@dataclass
class DeleteUser:
    repository: UserRepository
    clock: Clock

    async def execute(self, user_id: UUID) -> None:
        deleted = await self.repository.soft_delete(user_id, self.clock.now())
        if not deleted:
            raise UserNotFoundError(user_id)
