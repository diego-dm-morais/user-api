from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from user_api.adapters.outbound.persistence.models import UserModel
from user_api.domain.entities import User
from user_api.domain.exceptions import DuplicateEmailError, UserNotFoundError
from user_api.domain.ports import UserRepository

# Name of the partial UNIQUE index guarding active-user emails (models.py).
# Only an IntegrityError raised by *this* constraint means "duplicate email";
# any other IntegrityError (NOT NULL, a future FK, ...) must propagate as a
# real 500, not be masked as a 409 (cyber-sec finding).
_EMAIL_UNIQUE_INDEX = "ix_users_email_active_unique"


def _is_duplicate_email_violation(exc: IntegrityError) -> bool:
    return _EMAIL_UNIQUE_INDEX in str(exc.orig)


def _to_entity(model: UserModel) -> User:
    return User(
        id=model.id,
        name=model.name,
        email=model.email,
        password_hash=model.password_hash,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        email_verified_at=model.email_verified_at,
    )


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> None:
        model = UserModel(
            id=user.id,
            name=user.name,
            email=user.email,
            password_hash=user.password_hash,
            created_at=user.created_at,
            updated_at=user.updated_at,
            deleted_at=user.deleted_at,
            email_verified_at=user.email_verified_at,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            if _is_duplicate_email_violation(exc):
                raise DuplicateEmailError(user.email) from exc
            raise

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(UserModel).where(
            UserModel.id == user_id, UserModel.deleted_at.is_(None)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(model) if model else None

    async def get_by_email_including_pending(self, email: str) -> User | None:
        stmt = select(UserModel).where(
            UserModel.email == email, UserModel.deleted_at.is_(None)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(model) if model else None

    async def reset_email_verification(self, user_id: UUID) -> None:
        # Sole owner of email_verified_at outside consume_and_verify (item
        # #1 lost-update fix): a dedicated atomic UPDATE on just this
        # column, never routed through update()'s in-memory User snapshot.
        await self._session.execute(
            update(UserModel).where(UserModel.id == user_id).values(email_verified_at=None)
        )
        await self._session.commit()

    async def list_paginated(self, page: int, page_size: int) -> tuple[list[User], int]:
        base = select(UserModel).where(UserModel.deleted_at.is_(None))

        total = (
            await self._session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()

        stmt = (
            base.order_by(UserModel.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        models = (await self._session.execute(stmt)).scalars().all()
        return [_to_entity(m) for m in models], total

    async def update(self, user: User) -> None:
        stmt = select(UserModel).where(
            UserModel.id == user.id, UserModel.deleted_at.is_(None)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise UserNotFoundError(user.id)

        model.name = user.name
        model.email = user.email
        model.password_hash = user.password_hash
        model.updated_at = user.updated_at
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            if _is_duplicate_email_violation(exc):
                raise DuplicateEmailError(user.email) from exc
            raise

    async def soft_delete(self, user_id: UUID, deleted_at: datetime) -> bool:
        stmt = select(UserModel).where(
            UserModel.id == user_id, UserModel.deleted_at.is_(None)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return False
        model.deleted_at = deleted_at
        await self._session.commit()
        return True
