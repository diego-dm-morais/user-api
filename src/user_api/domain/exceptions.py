"""Domain exceptions. No framework imports allowed here."""


class DomainError(Exception):
    """Base class for domain errors."""


class DuplicateEmailError(DomainError):
    def __init__(self, email: str) -> None:
        super().__init__(f"Email already in use: {email}")
        self.email = email


class UserNotFoundError(DomainError):
    def __init__(self, user_id: object) -> None:
        super().__init__(f"User not found: {user_id}")
        self.user_id = user_id


class WeakPasswordError(DomainError):
    def __init__(self, min_length: int) -> None:
        super().__init__(f"Password must be at least {min_length} characters long")
        self.min_length = min_length


class InvalidOrExpiredTokenError(DomainError):
    """Token is nonexistent, expired, or already used (FR-011 — never distinguishes which)."""

    def __init__(self) -> None:
        super().__init__("Invalid or expired confirmation token")


class ResendCooldownError(DomainError):
    """Resend requested within the 60s cooldown window for the same email (FR-009)."""

    def __init__(self) -> None:
        super().__init__("Please wait before requesting another confirmation email")
