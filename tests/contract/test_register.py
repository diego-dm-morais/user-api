from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_api.adapters.outbound.persistence.models import UserModel


def _token_for(sent_emails: list[tuple[str, str]], email: str) -> str:
    for to, token in sent_emails:
        if to == email:
            return token
    raise AssertionError(f"No verification email captured for {email}")


async def test_register_returns_202_generic_body(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={"name": "Ada", "email": "ada@example.com", "password": "supersecret"},
    )

    assert response.status_code == 202
    body = response.json()
    assert "id" not in body
    assert "password" not in response.text
    assert "token" not in response.text


async def test_register_never_leaks_password_or_token_in_response(client: AsyncClient) -> None:
    """FR-012: response body must never contain the plaintext password,
    a hash, or the confirmation token — only the EmailSender side channel
    (ConsoleEmailSender, ADR-003) carries the plaintext token."""
    response = await client.post(
        "/auth/register",
        json={"name": "Ada", "email": "secret-check@example.com", "password": "supersecret123"},
    )

    assert "supersecret123" not in response.text
    assert "password_hash" not in response.text
    assert "password" not in response.text


async def test_register_weak_password_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={"name": "Ada", "email": "ada2@example.com", "password": "short"},
    )

    assert response.status_code == 422


async def test_register_invalid_email_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={"name": "Ada", "email": "not-an-email", "password": "supersecret"},
    )

    assert response.status_code == 422


async def test_register_no_api_key_required(client: AsyncClient) -> None:
    """US1: public endpoint, no X-API-Key header needed."""
    response = await client.post(
        "/auth/register",
        json={"name": "Ada", "email": "noauth@example.com", "password": "supersecret"},
    )

    assert response.status_code == 202


async def test_register_duplicate_active_email_returns_identical_generic_response(
    client: AsyncClient, db_session: AsyncSession, sent_emails: list[tuple[str, str]]
) -> None:
    """SC-001/FR-010: response is indistinguishable whether the email is new
    or already registered (and active)."""
    email = "dup-active@example.com"
    first = await client.post(
        "/auth/register", json={"name": "Ada", "email": email, "password": "supersecret"}
    )
    token = _token_for(sent_emails, email)
    await client.get(f"/auth/confirm?token={token}")

    second = await client.post(
        "/auth/register", json={"name": "Ada", "email": email, "password": "anotherpass"}
    )

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()


async def test_register_creates_pending_account_invisible_as_verified(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    """Independent Test (spec.md US1): account created pending, email_verified
    false via 001's admin GET /users/{id}, until confirmed."""
    email = "pending-check@example.com"
    await client.post(
        "/auth/register", json={"name": "Ada", "email": email, "password": "supersecret"}
    )

    stmt = select(UserModel).where(UserModel.email == email)
    model = (await db_session.execute(stmt)).scalar_one()

    response = await client.get(f"/users/{model.id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email_verified"] is False


async def test_register_normalizes_email_case_so_resend_matches(
    client: AsyncClient, sent_emails: list[tuple[str, str]]
) -> None:
    """Case-insensitive email: registering with "Test@Example.COM" must be
    the same account as resending with "test@example.com"."""
    await client.post(
        "/auth/register",
        json={"name": "Ada", "email": "CaseReg@Example.COM", "password": "supersecret"},
    )

    resend = await client.post(
        "/auth/register/resend", json={"email": "casereg@example.com"}
    )

    assert resend.status_code == 429  # same account, still in the resend cooldown
    assert _token_for(sent_emails, "casereg@example.com")  # stored lowercased
