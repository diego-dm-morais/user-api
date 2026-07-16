"""In-memory fakes for domain Ports, used by unit tests (no I/O)."""

from datetime import datetime
from uuid import UUID

from user_api.domain.entities import EmailVerificationToken, User
from user_api.domain.exceptions import DuplicateEmailError, UserNotFoundError


class FakeUserRepository:
    def __init__(self) -> None:
        self._users: dict[UUID, User] = {}
        self.reset_email_verification_calls: list[UUID] = []

    async def add(self, user: User) -> None:
        for existing in self._users.values():
            if existing.email == user.email and existing.deleted_at is None:
                raise DuplicateEmailError(user.email)
        self._users[user.id] = user

    async def get_by_id(self, user_id: UUID) -> User | None:
        user = self._users.get(user_id)
        if user is None or user.deleted_at is not None:
            return None
        return user

    async def get_by_email(self, email: str) -> User | None:
        for user in self._users.values():
            if user.email == email and user.deleted_at is None:
                return user
        return None

    async def get_by_email_including_pending(self, email: str) -> User | None:
        return await self.get_by_email(email)

    async def reset_email_verification(self, user_id: UUID) -> None:
        self.reset_email_verification_calls.append(user_id)
        user = self._users.get(user_id)
        if user is not None:
            user.email_verified_at = None

    async def list_paginated(self, page: int, page_size: int) -> tuple[list[User], int]:
        active = [u for u in self._users.values() if u.deleted_at is None]
        active.sort(key=lambda u: u.created_at)
        start = (page - 1) * page_size
        return active[start : start + page_size], len(active)

    async def update(self, user: User) -> None:
        current = self._users.get(user.id)
        if current is None or current.deleted_at is not None:
            raise UserNotFoundError(user.id)
        for existing in self._users.values():
            if (
                existing.id != user.id
                and existing.email == user.email
                and existing.deleted_at is None
            ):
                raise DuplicateEmailError(user.email)
        self._users[user.id] = user

    async def soft_delete(self, user_id: UUID, deleted_at: datetime) -> bool:
        user = self._users.get(user_id)
        if user is None or user.deleted_at is not None:
            return False
        user.deleted_at = deleted_at
        return True


class FakePasswordHasher:
    def hash(self, plain_password: str) -> str:
        return f"hashed:{plain_password}"


class CountingPasswordHasher(FakePasswordHasher):
    """Spy on top of FakePasswordHasher: records how many times hash() ran,
    used to assert the argon2 cost is paid on every code path (timing-leak
    regression, see test_register_user.py)."""

    def __init__(self) -> None:
        self.calls = 0

    def hash(self, plain_password: str) -> str:
        self.calls += 1
        return super().hash(plain_password)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeEmailVerificationTokenRepository:
    """Mirrors SqlAlchemyEmailVerificationTokenRepository: consume_and_verify
    also marks the owning user verified (ADR-004), so it needs a reference
    to the user repository it's paired with."""

    def __init__(self, user_repository: "FakeUserRepository") -> None:
        self._tokens: dict[UUID, EmailVerificationToken] = {}
        self._user_repository = user_repository

    async def add(self, token: EmailVerificationToken) -> None:
        self._tokens[token.id] = token

    async def get_latest_for_user(self, user_id: UUID) -> EmailVerificationToken | None:
        candidates = [t for t in self._tokens.values() if t.user_id == user_id]
        if not candidates:
            return None
        return max(candidates, key=lambda t: t.created_at)

    async def consume_and_verify(self, token_hash: str, now: datetime) -> UUID | None:
        for token in self._tokens.values():
            if token.token_hash == token_hash:
                if not token.is_valid(now):
                    return None
                token.used_at = now
                # Mirrors the real repository (token_repository.py): writes
                # email_verified_at directly, crossing the User aggregate
                # boundary on purpose (ADR-004) -- not via a Port method.
                user = self._user_repository._users.get(token.user_id)
                if user is not None:
                    user.email_verified_at = now
                return token.user_id
        return None


class FakeTokenGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self) -> str:
        self.calls += 1
        return f"token-{self.calls}"


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_verification_email(self, to: str, token: str) -> None:
        self.sent.append((to, token))
