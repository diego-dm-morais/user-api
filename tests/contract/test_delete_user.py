from uuid import uuid4

from httpx import AsyncClient


async def test_delete_existing_user_returns_204_then_get_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create = await client.post(
        "/users",
        json={"name": "Ada", "email": "ada@example.com", "password": "supersecret"},
        headers=auth_headers,
    )
    user_id = create.json()["id"]

    delete_response = await client.delete(f"/users/{user_id}", headers=auth_headers)
    get_response = await client.get(f"/users/{user_id}", headers=auth_headers)

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


async def test_delete_nonexistent_user_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.delete(f"/users/{uuid4()}", headers=auth_headers)

    assert response.status_code == 404


async def test_delete_already_deleted_user_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create = await client.post(
        "/users",
        json={"name": "Ada", "email": "ada2@example.com", "password": "supersecret"},
        headers=auth_headers,
    )
    user_id = create.json()["id"]
    await client.delete(f"/users/{user_id}", headers=auth_headers)

    response = await client.delete(f"/users/{user_id}", headers=auth_headers)

    assert response.status_code == 404
