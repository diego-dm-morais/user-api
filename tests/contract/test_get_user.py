from uuid import uuid4

from httpx import AsyncClient


async def test_get_existing_user_returns_200_without_password(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create = await client.post(
        "/users",
        json={"name": "Ada", "email": "ada@example.com", "password": "supersecret"},
        headers=auth_headers,
    )
    user_id = create.json()["id"]

    response = await client.get(f"/users/{user_id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user_id
    assert "password" not in body
    assert "password_hash" not in body
    assert "password" not in response.text
    assert "password_hash" not in response.text


async def test_get_nonexistent_user_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get(f"/users/{uuid4()}", headers=auth_headers)

    assert response.status_code == 404
