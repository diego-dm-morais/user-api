from user_api.config import Settings


def _make_settings(**overrides: str) -> Settings:
    defaults = {
        "database_url": "postgresql+asyncpg://unused/unused",
        "api_key_hashes": "hash-a, hash-b",
        "auth_register_rate_limit": "10/60s",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_auth_register_rate_limit_parsed_returns_correct_value() -> None:
    settings = _make_settings(auth_register_rate_limit="5/30s")

    assert settings.auth_register_rate_limit_parsed == (5, 30.0)


def test_auth_register_rate_limit_parsed_is_cached_across_calls() -> None:
    """Regression: must be a cached_property (computed once), not a plain
    @property that reparses the string on every access."""
    settings = _make_settings(auth_register_rate_limit="5/30s")

    first = settings.auth_register_rate_limit_parsed
    second = settings.auth_register_rate_limit_parsed

    assert first is second  # same tuple object -- proof the parse ran once
    assert "auth_register_rate_limit_parsed" in settings.__dict__


def test_api_key_hash_set_is_cached_across_calls() -> None:
    settings = _make_settings(api_key_hashes="hash-a, hash-b")

    first = settings.api_key_hash_set
    second = settings.api_key_hash_set

    assert first is second
    assert first == frozenset({"hash-a", "hash-b"})
