"""add email verification

Revision ID: 20260715222628
Revises: 20260715174647
Create Date: 2026-07-15 22:26:28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260715222628"
down_revision: str | None = "20260715174647"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    # ADR-001: admin-created users (001) never went through email confirmation
    # but are treated as already verified — backfill with their created_at.
    op.execute("UPDATE users SET email_verified_at = created_at")

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_email_verification_tokens_token_hash",
        "email_verification_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_email_verification_tokens_user_id_created_at",
        "email_verification_tokens",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_verification_tokens_user_id_created_at",
        table_name="email_verification_tokens",
    )
    op.drop_index(
        "ix_email_verification_tokens_token_hash", table_name="email_verification_tokens"
    )
    op.drop_table("email_verification_tokens")
    op.drop_column("users", "email_verified_at")
