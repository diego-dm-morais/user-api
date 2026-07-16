from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_api.adapters.outbound.persistence.models import EmailVerificationTokenModel


def _token_for(sent_emails: list[tuple[str, str]], email: str) -> str:
    for to, token in sent_emails:
        if to == email:
            return token
    raise AssertionError(f"No verification email captured for {email}")


async def _register(client: AsyncClient, sent_emails: list[tuple[str, str]], email: str) -> str:
    await client.post(
        "/auth/register", json={"name": "Ada", "email": email, "password": "supersecret"}
    )
    return _token_for(sent_emails, email)


async def test_resend_unknown_email_returns_202_generic(client: AsyncClient) -> None:
    """US3.3/FR-010: unregistered email gets the same generic 202, no
    account-existence signal."""
    response = await client.post(
        "/auth/register/resend", json={"email": "nobody@example.com"}
    )

    assert response.status_code == 202


async def test_resend_already_active_email_returns_202_generic(
    client: AsyncClient, sent_emails: list[tuple[str, str]]
) -> None:
    email = "resend-active@example.com"
    token = await _register(client, sent_emails, email)
    await client.get(f"/auth/confirm?token={token}")

    response = await client.post("/auth/register/resend", json={"email": email})

    assert response.status_code == 202


async def test_resend_within_cooldown_returns_429(
    client: AsyncClient, sent_emails: list[tuple[str, str]]
) -> None:
    """US3.2/SC-005: 2nd resend within 60s is the one documented exception
    to the generic-response rule (FR-010)."""
    email = "resend-cooldown@example.com"
    await _register(client, sent_emails, email)

    response = await client.post("/auth/register/resend", json={"email": email})

    assert response.status_code == 429


async def test_resend_outside_cooldown_issues_new_token(
    client: AsyncClient,
    sent_emails: list[tuple[str, str]],
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """US3.1: once the 60s cooldown has elapsed, resend succeeds and a
    second (distinct) confirmation token exists for the account."""
    email = "resend-fresh@example.com"
    await _register(client, sent_emails, email)

    stmt = select(EmailVerificationTokenModel)
    first_token = (await db_session.execute(stmt)).scalar_one()
    first_token.created_at = datetime.now(UTC) - timedelta(seconds=61)
    await db_session.commit()

    response = await client.post("/auth/register/resend", json={"email": email})

    assert response.status_code == 202
    stmt = select(EmailVerificationTokenModel).where(
        EmailVerificationTokenModel.user_id == first_token.user_id
    )
    tokens = (await db_session.execute(stmt)).scalars().all()
    assert len(tokens) == 2


async def test_resend_response_never_leaks_secrets(client: AsyncClient) -> None:
    """FR-012."""
    response = await client.post(
        "/auth/register/resend", json={"email": "resend-leak@example.com"}
    )

    assert "password" not in response.text
    assert "token" not in response.text


async def test_resend_normalizes_email_case_to_match_registration(
    client: AsyncClient, sent_emails: list[tuple[str, str]]
) -> None:
    """Case-insensitive email: resending with "Test@Example.COM" must find
    the account registered as "test@example.com"."""
    await _register(client, sent_emails, "caseresend@example.com")

    response = await client.post(
        "/auth/register/resend", json={"email": "CaseResend@Example.COM"}
    )

    assert response.status_code == 429  # same account, matched despite case difference
