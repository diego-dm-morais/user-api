"""Exercises the real production DB wiring in session.py directly. Contract
and other integration tests always override the get_db_session FastAPI
dependency with a testcontainers-backed sessionmaker, so this module (and
its use of Settings.database_url via get_settings()) is otherwise never
executed by the suite."""

import os

import pytest
from sqlalchemy import text

from user_api.adapters.outbound.persistence import session as session_module
from user_api.config import get_settings


def test_make_engine_and_sessionmaker_build_without_connecting() -> None:
    engine = session_module.make_engine("postgresql+asyncpg://unused-host/unused-db")
    try:
        sessionmaker = session_module.make_sessionmaker(engine)
        assert sessionmaker.kw["bind"] is engine
    finally:
        # Sync dispose is fine here: create_async_engine doesn't open a
        # connection until first use, so there is nothing to await-close.
        engine.sync_engine.dispose()


async def test_get_db_session_yields_a_working_session_wired_from_settings(
    postgres_url: str,
) -> None:
    original_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = postgres_url
    get_settings.cache_clear()
    session_module._default_sessionmaker.cache_clear()
    try:
        agen = session_module.get_db_session()
        session = await agen.__anext__()
        try:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
        finally:
            with pytest.raises(StopAsyncIteration):
                await agen.__anext__()
    finally:
        if original_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_url
        get_settings.cache_clear()
        session_module._default_sessionmaker.cache_clear()
