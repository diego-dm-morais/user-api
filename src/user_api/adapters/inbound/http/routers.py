from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from user_api.adapters.inbound.http.auth import verify_api_key
from user_api.adapters.inbound.http.dependencies import get_clock, get_password_hasher
from user_api.adapters.inbound.http.schemas import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ChangePasswordRequest,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from user_api.adapters.outbound.persistence.repository import SqlAlchemyUserRepository
from user_api.adapters.outbound.persistence.session import get_db_session
from user_api.application.use_cases import (
    ChangePassword,
    CreateUser,
    DeleteUser,
    GetUser,
    ListUsers,
    UpdateUser,
)
from user_api.domain.ports import Clock, PasswordHasher

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(verify_api_key)])


def get_user_repository(
    session: AsyncSession = Depends(get_db_session),
) -> SqlAlchemyUserRepository:
    return SqlAlchemyUserRepository(session)


# --- Endpoints ---


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    repository: SqlAlchemyUserRepository = Depends(get_user_repository),
    hasher: PasswordHasher = Depends(get_password_hasher),
    clock: Clock = Depends(get_clock),
) -> UserResponse:
    use_case = CreateUser(repository=repository, hasher=hasher, clock=clock)
    user = await use_case.execute(name=payload.name, email=payload.email, password=payload.password)
    return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    repository: SqlAlchemyUserRepository = Depends(get_user_repository),
) -> UserResponse:
    use_case = GetUser(repository=repository)
    user = await use_case.execute(user_id)
    return UserResponse.model_validate(user)


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    repository: SqlAlchemyUserRepository = Depends(get_user_repository),
) -> UserListResponse:
    use_case = ListUsers(repository=repository)
    items, total = await use_case.execute(page=page, page_size=page_size)
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    repository: SqlAlchemyUserRepository = Depends(get_user_repository),
    clock: Clock = Depends(get_clock),
) -> UserResponse:
    use_case = UpdateUser(repository=repository, clock=clock)
    user = await use_case.execute(user_id, name=payload.name, email=payload.email)
    return UserResponse.model_validate(user)


@router.patch("/{user_id}/password", response_model=UserResponse)
async def change_password(
    user_id: UUID,
    payload: ChangePasswordRequest,
    repository: SqlAlchemyUserRepository = Depends(get_user_repository),
    hasher: PasswordHasher = Depends(get_password_hasher),
    clock: Clock = Depends(get_clock),
) -> UserResponse:
    use_case = ChangePassword(repository=repository, hasher=hasher, clock=clock)
    user = await use_case.execute(user_id, new_password=payload.new_password)
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    repository: SqlAlchemyUserRepository = Depends(get_user_repository),
    clock: Clock = Depends(get_clock),
) -> None:
    use_case = DeleteUser(repository=repository, clock=clock)
    await use_case.execute(user_id)
