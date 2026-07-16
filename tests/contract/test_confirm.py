from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_api.adapters.outbound.persistence.models import EmailVerificationTokenModel, UserModel


def _token_for(sent_emails: list[tuple[str, str]], email: str) -> str:
    for to, token in sent_emails:
        if to == email:
            return token
    raise AssertionError(f"No verification email captured for {email}")


async def _register_and_get_token(
    client: AsyncClient, sent_emails: list[tuple[str, str]], email: str
) -> str:
    await client.post(
        "/auth/register", json={"name": "Ada", "email": email, "password": "supersecret"}
    )
    return _token_for(sent_emails, email)


async def test_confirm_valid_token_returns_200_and_activates_account(
    client: AsyncClient,
    sent_emails: list[tuple[str, str]],
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    email = "confirm-ok@example.com"
    token = await _register_and_get_token(client, sent_emails, email)

    response = await client.get(f"/auth/confirm?token={token}")

    assert response.status_code == 200
    stmt = select(UserModel).where(UserModel.email == email)
    model = (await db_session.execute(stmt)).scalar_one()
    admin_view = await client.get(f"/users/{model.id}", headers=auth_headers)
    assert admin_view.json()["email_verified"] is True


async def test_confirm_unknown_token_returns_400_generic(client: AsyncClient) -> None:
    """US2.2/FR-011: never 410, always the generic 400."""
    response = await client.get("/auth/confirm?token=does-not-exist")

    assert response.status_code == 400
    assert response.status_code != 410


async def test_confirm_reused_token_returns_400_generic(
    client: AsyncClient, sent_emails: list[tuple[str, str]]
) -> None:
    """SC-004: token reuse rejected on the 2nd attempt, same 400 as any
    other invalid-token case (FR-011 — indistinguishable from unknown)."""
    token = await _register_and_get_token(client, sent_emails, "confirm-reuse@example.com")
    first = await client.get(f"/auth/confirm?token={token}")
    assert first.status_code == 200

    second = await client.get(f"/auth/confirm?token={token}")

    assert second.status_code == 400


async def test_confirm_expired_token_returns_400_generic(
    client: AsyncClient, sent_emails: list[tuple[str, str]], db_session: AsyncSession
) -> None:
    """SC-003: token older than the 24h window is rejected, same 400."""
    token = await _register_and_get_token(client, sent_emails, "confirm-expired@example.com")
    stmt = select(EmailVerificationTokenModel)
    model = (await db_session.execute(stmt)).scalar_one()
    model.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    response = await client.get(f"/auth/confirm?token={token}")

    assert response.status_code == 400


async def test_confirm_response_never_leaks_token_or_password(
    client: AsyncClient, sent_emails: list[tuple[str, str]]
) -> None:
    """FR-012: neither the 200 success body nor the 400 error body ever
    includes a password hash or the confirmation token itself."""
    token = await _register_and_get_token(client, sent_emails, "confirm-leak@example.com")

    ok_response = await client.get(f"/auth/confirm?token={token}")
    error_response = await client.get("/auth/confirm?token=whatever-invalid")

    for response in (ok_response, error_response):
        assert "password_hash" not in response.text
        assert token not in response.text
