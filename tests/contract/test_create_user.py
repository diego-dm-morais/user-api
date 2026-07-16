from httpx import AsyncClient


async def test_create_user_returns_201_without_password(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/users",
        json={"name": "Ada", "email": "ada@example.com", "password": "supersecret"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ada@example.com"
    assert "password" not in body
    assert "password_hash" not in body
    assert "password" not in response.text
    assert "password_hash" not in response.text


async def test_create_user_is_email_verified_true(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """001/plan.md ADR-006: admin-created accounts are verified at creation."""
    response = await client.post(
        "/users",
        json={"name": "Ada", "email": "ada-verified@example.com", "password": "supersecret"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["email_verified"] is True


async def test_create_user_normalizes_email_case_for_dedup(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Case-insensitive dedup: "User@X.com" and "user@x.com" must collide."""
    first = await client.post(
        "/users",
        json={"name": "Ada", "email": "CaseTest@Example.COM", "password": "supersecret"},
        headers=auth_headers,
    )
    assert first.status_code == 201
    assert first.json()["email"] == "casetest@example.com"

    second = await client.post(
        "/users",
        json={"name": "Ada 2", "email": "casetest@example.com", "password": "supersecret"},
        headers=auth_headers,
    )
    assert second.status_code == 409


async def test_create_user_duplicate_email_returns_409(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {"name": "Ada", "email": "dup@example.com", "password": "supersecret"}
    await client.post("/users", json=payload, headers=auth_headers)

    response = await client.post("/users", json=payload, headers=auth_headers)

    assert response.status_code == 409


async def test_create_user_invalid_email_returns_422(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/users",
        json={"name": "Ada", "email": "not-an-email", "password": "supersecret"},
        headers=auth_headers,
    )

    assert response.status_code == 422


async def test_create_user_weak_password_returns_422(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/users",
        json={"name": "Ada", "email": "ada2@example.com", "password": "short"},
        headers=auth_headers,
    )

    assert response.status_code == 422
