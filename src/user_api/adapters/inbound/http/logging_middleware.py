import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

logger = logging.getLogger("user_api.http")


def register_logging(app: FastAPI) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    @app.middleware("http")
    async def _log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = str(uuid.uuid4())
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            # An unhandled exception below this middleware (a real bug, not
            # a mapped domain error — those are already caught by
            # error_handlers.py before reaching here) would otherwise skip
            # this log line entirely and escape without X-Request-ID ever
            # being recorded anywhere. Log with the request_id generated
            # above, then re-raise so FastAPI's default 500 handling
            # (or a downstream ASGI server) still takes over.
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.exception(
                json.dumps(
                    {
                        "event": "request_failed",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": duration_ms,
                    }
                )
            )
            raise
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        # Structured JSON log line. Never logs request/response bodies, so
        # passwords (create/update payloads) never reach the logs.
        is_password_change = request.url.path.endswith("/password") and request.method == "PATCH"
        logger.info(
            json.dumps(
                {
                    "event": "password_changed" if is_password_change else "request_completed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
            )
        )
        response.headers["X-Request-ID"] = request_id
        return response
