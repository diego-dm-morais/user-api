from uuid import uuid4

from httpx import AsyncClient


async def _create_user(client: AsyncClient, headers: dict[str, str], email: str) -> str:
    response = await client.post(
        "/users",
        json={"name": "Ada", "email": email, "password": "supersecret"},
        headers=headers,
    )
    return response.json()["id"]


async def test_update_user_name_only_returns_200_without_password(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    user_id = await _create_user(client, auth_headers, "ada@example.com")

    response = await client.patch(
        f"/users/{user_id}", json={"name": "New Name"}, headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New Name"
    assert body["email"] == "ada@example.com"
    assert "password" not in body
    assert "password_hash" not in body
    assert "password" not in response.text
    assert "password_hash" not in response.text


async def test_update_user_email_conflict_returns_409(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _create_user(client, auth_headers, "taken@example.com")
    user2_id = await _create_user(client, auth_headers, "free@example.com")

    response = await client.patch(
        f"/users/{user2_id}", json={"email": "taken@example.com"}, headers=auth_headers
    )

    assert response.status_code == 409


async def test_update_user_email_change_unverifies_account(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Regression: PATCH-ing a new email must reset email_verified to False
    -- the old confirmation doesn't prove ownership of the new address."""
    user_id = await _create_user(client, auth_headers, "verified-then-changed@example.com")
    created = await client.get(f"/users/{user_id}", headers=auth_headers)
    assert created.json()["email_verified"] is True  # 001/plan.md ADR-006

    response = await client.patch(
        f"/users/{user_id}", json={"email": "changed-address@example.com"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["email_verified"] is False


async def test_update_nonexistent_user_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.patch(
        f"/users/{uuid4()}", json={"name": "X"}, headers=auth_headers
    )

    assert response.status_code == 404
