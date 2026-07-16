from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

MIN_PASSWORD_LENGTH = 8
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _lowercase_email(v: str) -> str:
    """Normalizes email case (RFC 5321 domain part is case-insensitive in
    practice; treating the whole address as case-insensitive is the common,
    safe convention) so "User@X.com" and "user@x.com" dedupe and match on
    lookup/resend instead of silently being two different accounts."""
    return v.lower()


class UserCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)

    _normalize_email = field_validator("email")(_lowercase_email)


class UserUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str | None) -> str | None:
        return v.lower() if v is not None else v


class ChangePasswordRequest(BaseModel):
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class UserResponse(BaseModel):
    """Public representation of a User. Never includes password_hash (FR-009)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    created_at: datetime
    updated_at: datetime
    email_verified: bool


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)

    _normalize_email = field_validator("email")(_lowercase_email)


class ResendRequest(BaseModel):
    email: EmailStr

    _normalize_email = field_validator("email")(_lowercase_email)


class GenericAcceptedResponse(BaseModel):
    """FR-010: identical body regardless of whether the email exists, is
    pending, or is already active — never signals which case occurred."""

    message: str = (
        "If this email can receive a confirmation, it will shortly."
    )
