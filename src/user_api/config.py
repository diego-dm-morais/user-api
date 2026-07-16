from functools import cached_property, lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    api_key_hashes: str
    auth_register_rate_limit: str = "10/60s"

    @cached_property
    def api_key_hash_set(self) -> frozenset[str]:
        return frozenset(h.strip() for h in self.api_key_hashes.split(",") if h.strip())

    @cached_property
    def auth_register_rate_limit_parsed(self) -> tuple[int, float]:
        """Parses "N/Ws" (e.g. "10/60s") into (max_requests, window_seconds)."""
        count_str, _, window_str = self.auth_register_rate_limit.partition("/")
        return int(count_str), float(window_str.removesuffix("s"))


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
