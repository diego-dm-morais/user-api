"""Cross-endpoint error format consistency (FR-011, SC-002).

Collects one error case per status code from different endpoints and asserts
they all share the same top-level error schema, produced by error_handlers.py.
"""

from uuid import uuid4

from httpx import AsyncClient, Response


def _assert_error_schema(response: Response) -> None:
    body = response.json()
    assert set(body.keys()) == {"error"}
    error = body["error"]
    assert set(error.keys()) == {"type", "message", "details"}
    assert isinstance(error["type"], str)
    assert isinstance(error["message"], str)
    assert isinstance(error["details"], list)


async def test_401_404_409_422_share_same_error_schema(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    unauthorized = await client.get("/users")

    not_found = await client.get(f"/users/{uuid4()}", headers=auth_headers)

    payload = {"name": "A", "email": "dup@example.com", "password": "supersecret"}
    await client.post("/users", json=payload, headers=auth_headers)
    conflict = await client.post("/users", json=payload, headers=auth_headers)

    invalid = await client.post(
        "/users",
        json={"name": "A", "email": "not-an-email", "password": "supersecret"},
        headers=auth_headers,
    )

    responses = {401: unauthorized, 404: not_found, 409: conflict, 422: invalid}
    for expected_status, response in responses.items():
        assert response.status_code == expected_status, response.text

    for response in (unauthorized, not_found, conflict, invalid):
        _assert_error_schema(response)
