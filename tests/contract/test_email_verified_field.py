"""FR-015/SC-007: GET /users and GET /users/{id} expose email_verified."""

from httpx import AsyncClient


def _token_for(sent_emails: list[tuple[str, str]], email: str) -> str:
    for to, token in sent_emails:
        if to == email:
            return token
    raise AssertionError(f"No verification email captured for {email}")


async def test_get_user_reflects_verified_true_after_confirmation(
    client: AsyncClient, sent_emails: list[tuple[str, str]], auth_headers: dict[str, str]
) -> None:
    email = "sc007-verified@example.com"
    await client.post(
        "/auth/register", json={"name": "Ada", "email": email, "password": "supersecret"}
    )
    token = _token_for(sent_emails, email)
    await client.get(f"/auth/confirm?token={token}")

    list_response = await client.get("/users", headers=auth_headers)
    item = next(u for u in list_response.json()["items"] if u["email"] == email)

    assert item["email_verified"] is True


async def test_get_user_reflects_verified_false_before_confirmation(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    email = "sc007-pending@example.com"
    await client.post(
        "/auth/register", json={"name": "Ada", "email": email, "password": "supersecret"}
    )

    list_response = await client.get("/users", headers=auth_headers)
    item = next(u for u in list_response.json()["items"] if u["email"] == email)

    assert item["email_verified"] is False
