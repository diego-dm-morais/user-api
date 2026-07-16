"""Shared FastAPI dependency providers used by both routers.py (001, /users,
API-key protected) and auth_router.py (002, /auth, public) — a single
Argon2PasswordHasher/SystemClock instance for the whole process instead of
one per router (both routers wired the same singletons independently)."""

from functools import lru_cache

from user_api.adapters.outbound.clock import SystemClock
from user_api.adapters.outbound.security.argon2_hasher import Argon2PasswordHasher
from user_api.domain.ports import Clock, PasswordHasher


@lru_cache
def get_password_hasher() -> PasswordHasher:
    return Argon2PasswordHasher()


@lru_cache
def get_clock() -> Clock:
    return SystemClock()
