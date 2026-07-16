from uuid import uuid4

from httpx import AsyncClient


async def _create_user(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/users",
        json={"name": "Ada", "email": "ada@example.com", "password": "supersecret"},
        headers=headers,
    )
    return response.json()["id"]


async def test_change_password_success_returns_200_without_password(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    user_id = await _create_user(client, auth_headers)

    response = await client.patch(
        f"/users/{user_id}/password",
        json={"new_password": "brandnewsecret"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert "password" not in body
    assert "password_hash" not in body
    assert "new_password" not in body
    assert "password" not in response.text
    assert "password_hash" not in response.text


async def test_change_password_weak_password_returns_422(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    user_id = await _create_user(client, auth_headers)

    response = await client.patch(
        f"/users/{user_id}/password", json={"new_password": "short"}, headers=auth_headers
    )

    assert response.status_code == 422


async def test_change_password_nonexistent_user_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.patch(
        f"/users/{uuid4()}/password",
        json={"new_password": "brandnewsecret"},
        headers=auth_headers,
    )

    assert response.status_code == 404
