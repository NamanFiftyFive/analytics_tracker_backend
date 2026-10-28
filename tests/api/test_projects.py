from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.db.database import db
from tests.helpers import API, Account, AuthActions, OrgActions, ProjectActions


def projects_url(account: Account, path: str = "") -> str:
    return f"{API}/orgs/{account.org_id}/projects{path}"


async def send_one_event(client: AsyncClient, api_key: str) -> int:
    """Ingest a single event with this key; returns the HTTP status."""
    event = {
        "id": str(uuid4()),
        "event": "app_open",
        "distinct_id": "anon-1",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    response = await client.post(f"{API}/ingest/batch", headers={"X-API-Key": api_key}, json={"events": [event]})
    return response.status_code


class TestCreateProject:
    async def test_creates_project_with_a_working_first_key(
        self, client: AsyncClient, auth: AuthActions, projects: ProjectActions
    ):
        admin = await auth.register()
        created = await projects.create(admin, name="Car App", timezone="Asia/Kolkata")

        project, key = created["project"], created["api_key"]
        assert (project["name"], project["timezone"], project["active_api_keys"]) == ("Car App", "Asia/Kolkata", 1)
        assert key["key"].startswith("pk_live_")
        assert key["key_prefix"] == key["key"][:12]
        assert await send_one_event(client, key["key"]) == 202

    async def test_only_the_key_hash_is_stored(self, auth: AuthActions, projects: ProjectActions):
        admin = await auth.register()
        key = (await projects.create(admin))["api_key"]["key"]
        stored = await db.fetchval("SELECT key_hash FROM api_keys")
        assert stored != key
        assert key not in stored

    async def test_default_timezone_is_utc(self, auth: AuthActions, projects: ProjectActions):
        admin = await auth.register()
        assert (await projects.create(admin))["project"]["timezone"] == "UTC"

    async def test_origins_are_normalized(self, auth: AuthActions, projects: ProjectActions):
        admin = await auth.register()
        created = await projects.create(
            admin, allowed_origins=["https://Cars.Example.com/", "https://cars.example.com"]
        )
        assert created["project"]["allowed_origins"] == ["https://cars.example.com"]

    @pytest.mark.parametrize(
        "fields",
        [
            {"timezone": "Mars/Base"},
            {"platform": "windows"},
            {"allowed_origins": ["cars.example.com"]},
            {"allowed_origins": ["https://cars.example.com/path"]},
            {"name": "x"},
        ],
    )
    async def test_invalid_fields(self, client: AsyncClient, auth: AuthActions, fields: dict):
        admin = await auth.register()
        body = {"name": "Car App", "platform": "flutter", **fields}
        response = await client.post(projects_url(admin), headers=admin.headers, json=body)
        assert response.status_code == 422


class TestProjectAccess:
    @pytest.mark.parametrize("role", ["viewer", "analyst"])
    async def test_non_admins_can_read_but_not_change(
        self, client: AsyncClient, auth: AuthActions, orgs: OrgActions, projects: ProjectActions, role: str
    ):
        admin = await auth.register()
        project_id = (await projects.create(admin))["project"]["id"]
        member = await orgs.add_new_member(admin, role)

        listed = await client.get(projects_url(member), headers=member.headers)
        one = await client.get(projects_url(member, f"/{project_id}"), headers=member.headers)
        assert listed.status_code == one.status_code == 200
        assert [p["id"] for p in listed.json()["data"]] == [project_id]

        create = await client.post(
            projects_url(member), headers=member.headers, json={"name": "New", "platform": "web"}
        )
        update = await client.patch(projects_url(member, f"/{project_id}"), headers=member.headers, json={"name": "X1"})
        delete = await client.delete(projects_url(member, f"/{project_id}"), headers=member.headers)
        keys = await client.get(projects_url(member, f"/{project_id}/api-keys"), headers=member.headers)
        assert create.status_code == update.status_code == delete.status_code == keys.status_code == 403

    async def test_project_of_another_org_is_not_found(
        self, client: AsyncClient, auth: AuthActions, projects: ProjectActions
    ):
        # Using your own org id with someone else's project id must not reach that project.
        owner = await auth.register()
        other = await auth.register()
        project_id = (await projects.create(owner))["project"]["id"]

        get = await client.get(projects_url(other, f"/{project_id}"), headers=other.headers)
        update = await client.patch(projects_url(other, f"/{project_id}"), headers=other.headers, json={"name": "Hacked"})
        delete = await client.delete(projects_url(other, f"/{project_id}"), headers=other.headers)
        keys = await client.get(projects_url(other, f"/{project_id}/api-keys"), headers=other.headers)
        new_key = await client.post(
            projects_url(other, f"/{project_id}/api-keys"), headers=other.headers, json={"name": "Mine"}
        )
        assert {r.status_code for r in (get, update, delete, keys, new_key)} == {404}
        assert await db.fetchval("SELECT name FROM projects") == "Car App"


class TestUpdateProject:
    async def test_changes_only_the_fields_sent(self, client: AsyncClient, auth: AuthActions, projects: ProjectActions):
        admin = await auth.register()
        project = (await projects.create(admin, name="Car App", timezone="Asia/Kolkata"))["project"]

        response = await client.patch(
            projects_url(admin, f"/{project['id']}"), headers=admin.headers, json={"name": "Car App v2"}
        )
        assert response.status_code == 200
        updated = response.json()["data"]
        assert (updated["name"], updated["timezone"], updated["platform"]) == ("Car App v2", "Asia/Kolkata", "flutter")

    async def test_allowed_origins_replaces_the_list(
        self, client: AsyncClient, auth: AuthActions, projects: ProjectActions
    ):
        admin = await auth.register()
        project = (await projects.create(admin, allowed_origins=["https://a.example.com"]))["project"]

        response = await client.patch(
            projects_url(admin, f"/{project['id']}"),
            headers=admin.headers,
            json={"allowed_origins": ["https://b.example.com"]},
        )
        assert response.json()["data"]["allowed_origins"] == ["https://b.example.com"]

    async def test_unknown_project(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register()
        response = await client.patch(projects_url(admin, f"/{uuid4()}"), headers=admin.headers, json={"name": "New"})
        assert response.status_code == 404


class TestDeleteProject:
    async def test_deletes_project_with_its_keys_and_events(
        self, client: AsyncClient, auth: AuthActions, projects: ProjectActions
    ):
        admin = await auth.register()
        created = await projects.create(admin)
        assert await send_one_event(client, created["api_key"]["key"]) == 202

        response = await client.delete(projects_url(admin, f"/{created['project']['id']}"), headers=admin.headers)
        assert response.status_code == 200
        for table in ("projects", "api_keys", "events", "persons"):
            assert await db.fetchval(f"SELECT count(*) FROM {table}") == 0, table

        # Its key no longer works.
        assert await send_one_event(client, created["api_key"]["key"]) == 401

    async def test_unknown_project(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register()
        response = await client.delete(projects_url(admin, f"/{uuid4()}"), headers=admin.headers)
        assert response.status_code == 404


class TestApiKeys:
    async def test_create_list_and_revoke(self, client: AsyncClient, auth: AuthActions, projects: ProjectActions):
        admin = await auth.register()
        created = await projects.create(admin)
        project_id = created["project"]["id"]
        keys_url = projects_url(admin, f"/{project_id}/api-keys")

        new = await client.post(keys_url, headers=admin.headers, json={"name": "Android release"})
        assert new.status_code == 201
        new_key = new.json()["data"]
        assert await send_one_event(client, new_key["key"]) == 202

        # The list never shows full keys again.
        listed = (await client.get(keys_url, headers=admin.headers)).json()["data"]
        assert {k["name"] for k in listed} == {"Default key", "Android release"}
        assert all("key" not in k for k in listed)

        revoked = await client.delete(f"{keys_url}/{new_key['id']}", headers=admin.headers)
        assert revoked.status_code == 200
        assert revoked.json()["data"]["is_active"] is False
        assert revoked.json()["data"]["revoked_at"] is not None

        # Stops working at once; the other key keeps working; the revoked one stays listed.
        assert await send_one_event(client, new_key["key"]) == 401
        assert await send_one_event(client, created["api_key"]["key"]) == 202
        assert len((await client.get(keys_url, headers=admin.headers)).json()["data"]) == 2
        project = (await client.get(projects_url(admin, f"/{project_id}"), headers=admin.headers)).json()["data"]
        assert project["active_api_keys"] == 1

    async def test_revoking_twice_keeps_the_first_revoked_time(
        self, client: AsyncClient, auth: AuthActions, projects: ProjectActions
    ):
        admin = await auth.register()
        created = await projects.create(admin)
        url = projects_url(admin, f"/{created['project']['id']}/api-keys/{created['api_key']['id']}")

        first = (await client.delete(url, headers=admin.headers)).json()["data"]["revoked_at"]
        second = (await client.delete(url, headers=admin.headers)).json()["data"]["revoked_at"]
        assert first == second

    async def test_unknown_key(self, client: AsyncClient, auth: AuthActions, projects: ProjectActions):
        admin = await auth.register()
        project_id = (await projects.create(admin))["project"]["id"]
        response = await client.delete(projects_url(admin, f"/{project_id}/api-keys/{uuid4()}"), headers=admin.headers)
        assert response.status_code == 404

    async def test_key_stops_working_when_org_is_suspended(
        self, client: AsyncClient, auth: AuthActions, projects: ProjectActions
    ):
        admin = await auth.register()
        key = (await projects.create(admin))["api_key"]["key"]
        await db.execute("UPDATE organizations SET is_active = false WHERE id = $1", admin.org_id)
        assert await send_one_event(client, key) == 403
