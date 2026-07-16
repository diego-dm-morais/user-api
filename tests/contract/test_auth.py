from uuid import uuid4

from httpx import AsyncClient

# Every declared /users* route, exercised without/with a bad key (FR-014, SC-005).
_ENDPOINTS = [
    ("POST", "/users", {"name": "A", "email": "a@example.com", "password": "supersecret"}),
    ("GET", "/users", None),
    ("GET", f"/users/{uuid4()}", None),
    ("PATCH", f"/users/{uuid4()}", {"name": "B"}),
    ("PATCH", f"/users/{uuid4()}/password", {"new_password": "supersecret"}),
    ("DELETE", f"/users/{uuid4()}", None),
]


async def test_missing_api_key_returns_401_and_no_user_data(client: AsyncClient) -> None:
    for method, path, body in _ENDPOINTS:
        response = await client.request(method, path, json=body)
        assert response.status_code == 401, f"{method} {path}"
        assert "password" not in response.text


async def test_invalid_api_key_returns_401(client: AsyncClient) -> None:
    headers = {"X-API-Key": "not-a-real-key"}
    for method, path, body in _ENDPOINTS:
        response = await client.request(method, path, json=body, headers=headers)
        assert response.status_code == 401, f"{method} {path}"


async def test_missing_and_invalid_key_return_byte_identical_body(client: AsyncClient) -> None:
    missing = await client.get("/users")
    invalid = await client.get("/users", headers={"X-API-Key": "garbage-key"})

    assert missing.status_code == invalid.status_code == 401
    assert missing.content == invalid.content
