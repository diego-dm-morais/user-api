from functools import lru_cache

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from user_api.adapters.inbound.http.dependencies import get_clock, get_password_hasher
from user_api.adapters.inbound.http.ip_rate_limiter import enforce_register_rate_limit
from user_api.adapters.inbound.http.schemas import (
    GenericAcceptedResponse,
    RegisterRequest,
    ResendRequest,
)
from user_api.adapters.outbound.notifications.console_email_sender import ConsoleEmailSender
from user_api.adapters.outbound.persistence.repository import SqlAlchemyUserRepository
from user_api.adapters.outbound.persistence.session import get_db_session
from user_api.adapters.outbound.persistence.token_repository import (
    SqlAlchemyEmailVerificationTokenRepository,
)
from user_api.adapters.outbound.security.token_generator import SecretsTokenGenerator
from user_api.application.registration_use_cases import (
    ConfirmEmail,
    RegisterUser,
    ResendVerificationEmail,
)
from user_api.domain.ports import Clock, EmailSender, PasswordHasher, TokenGenerator

router = APIRouter(prefix="/auth", tags=["auth"])

_ACCEPTED_BODY = GenericAcceptedResponse()


# --- Dependency providers (composition wiring for this router) ---
# get_password_hasher/get_clock are shared with routers.py (001) via
# dependencies.py — see item #8 fix, avoids a second Argon2/SystemClock
# singleton per router.


@lru_cache
def _token_generator() -> TokenGenerator:
    return SecretsTokenGenerator()


@lru_cache
def _email_sender() -> EmailSender:
    return ConsoleEmailSender()


def get_user_repository(
    session: AsyncSession = Depends(get_db_session),
) -> SqlAlchemyUserRepository:
    return SqlAlchemyUserRepository(session)


def get_token_repository(
    session: AsyncSession = Depends(get_db_session),
) -> SqlAlchemyEmailVerificationTokenRepository:
    return SqlAlchemyEmailVerificationTokenRepository(session)


def get_token_generator() -> TokenGenerator:
    return _token_generator()


def get_email_sender() -> EmailSender:
    return _email_sender()


# --- Endpoints ---


@router.post(
    "/register",
    response_model=GenericAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_register_rate_limit)],
)
async def register(
    payload: RegisterRequest,
    repository: SqlAlchemyUserRepository = Depends(get_user_repository),
    token_repository: SqlAlchemyEmailVerificationTokenRepository = Depends(get_token_repository),
    hasher: PasswordHasher = Depends(get_password_hasher),
    token_generator: TokenGenerator = Depends(get_token_generator),
    email_sender: EmailSender = Depends(get_email_sender),
    clock: Clock = Depends(get_clock),
) -> GenericAcceptedResponse:
    use_case = RegisterUser(
        repository=repository,
        token_repository=token_repository,
        hasher=hasher,
        token_generator=token_generator,
        email_sender=email_sender,
        clock=clock,
    )
    await use_case.execute(name=payload.name, email=payload.email, password=payload.password)
    return _ACCEPTED_BODY  # FR-010: always identical, regardless of what execute() did


@router.get("/confirm", status_code=status.HTTP_200_OK)
async def confirm(
    token: str = Query(...),
    token_repository: SqlAlchemyEmailVerificationTokenRepository = Depends(get_token_repository),
    clock: Clock = Depends(get_clock),
) -> dict[str, str]:
    use_case = ConfirmEmail(token_repository=token_repository, clock=clock)
    await use_case.execute(token)
    return {"status": "confirmed"}


@router.post(
    "/register/resend",
    response_model=GenericAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resend(
    payload: ResendRequest,
    repository: SqlAlchemyUserRepository = Depends(get_user_repository),
    token_repository: SqlAlchemyEmailVerificationTokenRepository = Depends(get_token_repository),
    token_generator: TokenGenerator = Depends(get_token_generator),
    email_sender: EmailSender = Depends(get_email_sender),
    clock: Clock = Depends(get_clock),
) -> GenericAcceptedResponse:
    use_case = ResendVerificationEmail(
        repository=repository,
        token_repository=token_repository,
        token_generator=token_generator,
        email_sender=email_sender,
        clock=clock,
    )
    await use_case.execute(payload.email)  # raises ResendCooldownError -> 429 (FR-009 exception)
    return _ACCEPTED_BODY
