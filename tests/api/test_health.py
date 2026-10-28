from httpx import AsyncClient

from tests.helpers import API


async def test_health(client: AsyncClient):
    response = await client.get(f"{API}/health")
    assert response.status_code == 200
    assert response.json() == {"status": 200, "data": {"api": "ok"}}


async def test_health_db(client: AsyncClient):
    response = await client.get(f"{API}/health/db")
    assert response.status_code == 200
    assert response.json()["data"]["database"] == "ok"


async def test_unknown_url_uses_the_error_envelope(client: AsyncClient):
    response = await client.get(f"{API}/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"status": 404, "error": "Not Found"}
