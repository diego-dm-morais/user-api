import secrets

from user_api.domain.ports import TokenGenerator


class SecretsTokenGenerator(TokenGenerator):
    """TokenGenerator Port implementation using stdlib `secrets` (high entropy, URL-safe)."""

    def generate(self) -> str:
        return secrets.token_urlsafe(32)
