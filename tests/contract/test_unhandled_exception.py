"""Regression tests for the catch-all 500 handler and security headers
(low-priority hardening findings #10/#11 from the security review)."""

import json
import logging
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def test_unhandled_exception_returns_500_generic_envelope_and_logs(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """A real bug (not a mapped domain exception) must never leak str(exc)
    or a stack trace to the client, must use the same error envelope as
    every other endpoint (FR-011/SC-002), and logging_middleware.py must log
    the structured failure line (with the request's X-Request-ID) before
    the exception is re-raised to become this 500 -- so a crash is never
    silently missing from the logs even though it skips the normal
    "request_completed" log line."""
    from user_api.adapters.inbound.http.app import app
    from user_api.adapters.outbound.persistence.session import get_db_session

    async def _broken_session() -> AsyncIterator[AsyncSession]:
        raise RuntimeError("simulated unexpected failure - must never reach the client")
        yield  # pragma: no cover - unreachable, keeps this an async generator

    app.dependency_overrides[get_db_session] = _broken_session

    with caplog.at_level(logging.ERROR, logger="user_api.http"):
        response = await client.get("/health/ready")

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "error": {
            "type": "internal_error",
            "message": "An unexpected error occurred",
            "details": [],
        }
    }
    assert "simulated unexpected failure" not in response.text
    assert "RuntimeError" not in response.text
    # ALTO 2 regression: ServerErrorMiddleware sits above the security-headers
    # middleware, so an unmapped exception's 500 must set these directly on
    # the JSONResponse in error_handlers.py, not rely on middleware.
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"

    failure_records = [r for r in caplog.records if r.name == "user_api.http"]
    assert failure_records, "logging_middleware.py must log before re-raising"
    logged = json.loads(failure_records[0].getMessage())
    assert logged["event"] == "request_failed"
    assert logged["path"] == "/health/ready"
    assert logged["request_id"]  # generated before the exception was logged


async def test_responses_include_security_headers(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
