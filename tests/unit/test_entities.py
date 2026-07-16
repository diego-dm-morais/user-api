from datetime import UTC, datetime
from uuid import uuid4

from user_api.domain.entities import User


def _make_user(**overrides: object) -> User:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    defaults: dict[str, object] = dict(
        id=uuid4(),
        name="Ada",
        email="ada@example.com",
        password_hash="hash",
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return User(**defaults)  # type: ignore[arg-type]


def test_is_deleted_false_when_deleted_at_is_none() -> None:
    assert _make_user(deleted_at=None).is_deleted is False


def test_is_deleted_true_when_deleted_at_is_set() -> None:
    assert _make_user(deleted_at=datetime(2026, 1, 2, tzinfo=UTC)).is_deleted is True
