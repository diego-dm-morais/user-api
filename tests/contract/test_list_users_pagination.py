import pytest
from httpx import AsyncClient


@pytest.mark.parametrize(
    "query",
    [
        "page=-1",
        "page=0",
        "page=abc",
        "page_size=-1",
        "page_size=0",
        "page_size=abc",
        "page_size=999999999",
    ],
)
async def test_list_users_invalid_pagination_returns_422_never_500(
    client: AsyncClient, auth_headers: dict[str, str], query: str
) -> None:
    response = await client.get(f"/users?{query}", headers=auth_headers)

    assert response.status_code == 422
