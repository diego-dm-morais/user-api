from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from user_api.adapters.inbound.http.auth_router import router as auth_router
from user_api.adapters.inbound.http.error_handlers import register_error_handlers
from user_api.adapters.inbound.http.logging_middleware import register_logging
from user_api.adapters.inbound.http.routers import router as users_router
from user_api.adapters.outbound.persistence.session import get_db_session


def _register_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def _security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response


def create_app() -> FastAPI:
    """Composition root: builds the FastAPI app, wires error handlers and routers."""
    app = FastAPI(title="User CRUD API")
    register_error_handlers(app)
    register_logging(app)
    _register_security_headers(app)
    app.include_router(users_router)
    app.include_router(auth_router)

    @app.get("/health", tags=["health"])
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def readiness(session: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
        await session.execute(text("SELECT 1"))
        return {"status": "ready"}

    return app


app = create_app()
