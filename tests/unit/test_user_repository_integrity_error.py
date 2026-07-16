"""Unit-level (no DB) regression for the IntegrityError -> DuplicateEmailError
mapping in SqlAlchemyUserRepository.add() (BAIXO finding, cyber-sec N1):
only the email-uniqueness constraint should be mapped, anything else must
propagate so it becomes a real 500 instead of a silently-swallowed 202."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from user_api.adapters.outbound.persistence.repository import SqlAlchemyUserRepository
from user_api.domain.entities import User
from user_api.domain.exceptions import DuplicateEmailError


class _FailingSession:
    """Fakes just enough of AsyncSession for add() to exercise the
    commit -> IntegrityError -> rollback path without a real DB."""

    def __init__(self, constraint_name: str) -> None:
        self._constraint_name = constraint_name
        self.rolled_back = False

    def add(self, model: object) -> None:
        pass

    async def commit(self) -> None:
        orig = Exception(
            f'duplicate key value violates unique constraint "{self._constraint_name}"'
        )
        raise IntegrityError("INSERT INTO users ...", {}, orig)

    async def rollback(self) -> None:
        self.rolled_back = True


def _make_user() -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        name="Ada",
        email="ada@example.com",
        password_hash="hash",
        created_at=now,
        updated_at=now,
    )


async def test_add_maps_email_unique_violation_to_duplicate_email_error() -> None:
    session = _FailingSession("ix_users_email_active_unique")
    repo = SqlAlchemyUserRepository(session)  # type: ignore[arg-type]

    with pytest.raises(DuplicateEmailError):
        await repo.add(_make_user())

    assert session.rolled_back is True


async def test_add_propagates_unrelated_integrity_error() -> None:
    session = _FailingSession("some_other_constraint")
    repo = SqlAlchemyUserRepository(session)  # type: ignore[arg-type]

    with pytest.raises(IntegrityError):
        await repo.add(_make_user())

    assert session.rolled_back is True
