"""Error paths that normal use rarely hits: broken JSON, deleted users, database down, bugs."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.database import db
from app.main import app
from app.services.project_service import ProjectService
from tests.helpers import API, AuthActions


async def test_invalid_json_body(client: AsyncClient):
    response = await client.post(
        f"{API}/auth/login", content="{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json() == {"status": 422, "error": "Request body is not valid JSON"}


async def test_token_of_a_deleted_user(client: AsyncClient, auth: AuthActions):
    account = await auth.register()
    await db.execute("DELETE FROM organization_members WHERE user_id = $1", account.user_id)
    await db.execute("DELETE FROM users WHERE id = $1", account.user_id)
    response = await client.get(f"{API}/auth/me", headers=account.headers)
    assert response.status_code == 401


async def test_health_db_when_the_database_is_down(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    async def broken(*args, **kwargs):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(db, "fetchval", broken)
    response = await client.get(f"{API}/health/db")
    assert response.status_code == 503
    assert response.json()["status"] == 503


async def test_unexpected_error_hides_details(auth: AuthActions, monkeypatch: pytest.MonkeyPatch):
    # A bug inside a service: the client gets a plain 500, never the exception text.
    account = await auth.register()

    async def crash(self, organization_id):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(ProjectService, "list_projects", crash)
    # raise_app_exceptions=False: return the 500 response like a real server, instead of re-raising.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get(f"{API}/orgs/{account.org_id}/projects", headers=account.headers)
    assert response.status_code == 500
    assert response.json() == {"status": 500, "error": "Internal server error"}
