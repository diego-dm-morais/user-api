from httpx import AsyncClient


async def test_list_users_paginated_with_metadata_and_no_password(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    for i in range(3):
        await client.post(
            "/users",
            json={"name": f"User {i}", "email": f"user{i}@example.com", "password": "supersecret"},
            headers=auth_headers,
        )

    response = await client.get("/users?page=1&page_size=2", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2
    for item in body["items"]:
        assert "password" not in item
        assert "password_hash" not in item
    assert "password" not in response.text
    assert "password_hash" not in response.text


async def test_list_users_omits_soft_deleted(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create = await client.post(
        "/users",
        json={"name": "Ada", "email": "del@example.com", "password": "supersecret"},
        headers=auth_headers,
    )
    user_id = create.json()["id"]
    await client.delete(f"/users/{user_id}", headers=auth_headers)

    response = await client.get("/users", headers=auth_headers)

    ids = [item["id"] for item in response.json()["items"]]
    assert user_id not in ids
