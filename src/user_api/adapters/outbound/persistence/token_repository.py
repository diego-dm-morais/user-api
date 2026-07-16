from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from user_api.adapters.outbound.persistence.models import (
    EmailVerificationTokenModel,
    UserModel,
)
from user_api.domain.entities import EmailVerificationToken


def _to_entity(model: EmailVerificationTokenModel) -> EmailVerificationToken:
    return EmailVerificationToken(
        id=model.id,
        user_id=model.user_id,
        token_hash=model.token_hash,
        created_at=model.created_at,
        expires_at=model.expires_at,
        used_at=model.used_at,
    )


class SqlAlchemyEmailVerificationTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: EmailVerificationToken) -> None:
        model = EmailVerificationTokenModel(
            id=token.id,
            user_id=token.user_id,
            token_hash=token.token_hash,
            created_at=token.created_at,
            expires_at=token.expires_at,
            used_at=token.used_at,
        )
        self._session.add(model)
        await self._session.commit()

    async def get_latest_for_user(self, user_id: UUID) -> EmailVerificationToken | None:
        stmt = (
            select(EmailVerificationTokenModel)
            .where(EmailVerificationTokenModel.user_id == user_id)
            .order_by(EmailVerificationTokenModel.created_at.desc())
            .limit(1)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(model) if model else None

    async def consume_and_verify(self, token_hash: str, now: datetime) -> UUID | None:
        """Marks the token used and the owning user verified in one transaction
        (ADR-004). Returns user_id on success, None if the token is nonexistent,
        expired, already used, or the owning user is deleted (FR-011 — caller
        never learns which).

        The single conditional UPDATE...RETURNING is the atomicity guard
        (SC-004): two concurrent calls for the same token both race on this
        one UPDATE; the DB row lock means only one can match
        `used_at IS NULL` and flip it — the other gets zero rows back and
        None. A prior SELECT-then-check-then-UPDATE let both callers pass
        the Python-side check before either had committed.
        """
        stmt = (
            update(EmailVerificationTokenModel)
            .where(
                EmailVerificationTokenModel.token_hash == token_hash,
                EmailVerificationTokenModel.used_at.is_(None),
                EmailVerificationTokenModel.expires_at > now,
            )
            .values(used_at=now)
            .returning(EmailVerificationTokenModel.user_id)
        )
        user_id = (await self._session.execute(stmt)).scalar_one_or_none()
        if user_id is None:
            await self._session.rollback()
            return None

        user_stmt = select(UserModel).where(
            UserModel.id == user_id, UserModel.deleted_at.is_(None)
        )
        user_model = (await self._session.execute(user_stmt)).scalar_one_or_none()
        if user_model is None:
            await self._session.rollback()
            return None

        user_model.email_verified_at = now
        await self._session.commit()
        return user_id
