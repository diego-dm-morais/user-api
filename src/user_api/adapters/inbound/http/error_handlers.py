import logging
from collections.abc import Mapping

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from user_api.domain.exceptions import (
    DuplicateEmailError,
    InvalidOrExpiredTokenError,
    ResendCooldownError,
    UserNotFoundError,
    WeakPasswordError,
)

logger = logging.getLogger("user_api.http")

# ServerErrorMiddleware (Starlette's outermost layer) sits above the
# BaseHTTPMiddleware that normally sets these headers (app.py), so an
# unmapped exception's 500 response never passes through it. Setting them
# here, directly on every error JSONResponse, is the only way that's
# reliable for all error paths, not just the happy path (ALTO 2).
_SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}


def _error_body(
    error_type: str, message: str, details: list[dict[str, object]] | None = None
) -> dict[str, object]:
    """Consistent error format across all endpoints (FR-011, SC-002)."""
    return {"error": {"type": error_type, "message": message, "details": details or []}}


def _json_error(
    status_code: int,
    error_type: str,
    message: str,
    details: list[dict[str, object]] | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    headers = {**_SECURITY_HEADERS, **(extra_headers or {})}
    return JSONResponse(
        status_code=status_code,
        content=_error_body(error_type, message, details),
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DuplicateEmailError)
    async def _duplicate_email(request: Request, exc: DuplicateEmailError) -> JSONResponse:
        return _json_error(status.HTTP_409_CONFLICT, "conflict", str(exc))

    @app.exception_handler(UserNotFoundError)
    async def _user_not_found(request: Request, exc: UserNotFoundError) -> JSONResponse:
        return _json_error(status.HTTP_404_NOT_FOUND, "not_found", str(exc))

    @app.exception_handler(WeakPasswordError)
    async def _weak_password(request: Request, exc: WeakPasswordError) -> JSONResponse:
        return _json_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error", str(exc))

    @app.exception_handler(InvalidOrExpiredTokenError)
    async def _invalid_or_expired_token(
        request: Request, exc: InvalidOrExpiredTokenError
    ) -> JSONResponse:
        # FR-011: always 400, never distinguishes nonexistent/expired/used tokens.
        return _json_error(status.HTTP_400_BAD_REQUEST, "invalid_token", str(exc))

    @app.exception_handler(ResendCooldownError)
    async def _resend_cooldown(request: Request, exc: ResendCooldownError) -> JSONResponse:
        # Documented exception to FR-010's generic-response rule (spec.md FR-010/SC-001):
        # only reachable when a genuinely pending account exists in active cooldown.
        return _json_error(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _json_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "Invalid request",
            details=jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(HTTPException)
    async def _http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        # Normalizes FastAPI's default {"detail": ...} (e.g. 401 from verify_api_key)
        # into the same envelope as domain errors below (FR-011, SC-002).
        error_type = {401: "unauthorized"}.get(exc.status_code, "http_error")
        return _json_error(
            exc.status_code, error_type, str(exc.detail), extra_headers=exc.headers
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        # Catch-all for anything not already mapped above (a real bug, not a
        # known domain error): never leak str(exc)/stack trace to the
        # client, always the same envelope as every other error response
        # (FR-011, SC-002). logging_middleware.py already logged the full
        # exception with the request_id before this re-raise reaches here.
        logger.exception("Unhandled exception")
        return _json_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "An unexpected error occurred",
        )
