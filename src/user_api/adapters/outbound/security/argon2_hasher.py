from argon2 import PasswordHasher as Argon2Lib

from user_api.domain.ports import PasswordHasher


class Argon2PasswordHasher(PasswordHasher):
    """PasswordHasher Port implementation using argon2id (ADR-002)."""

    def __init__(self) -> None:
        self._hasher = Argon2Lib()

    def hash(self, plain_password: str) -> str:
        return self._hasher.hash(plain_password)
