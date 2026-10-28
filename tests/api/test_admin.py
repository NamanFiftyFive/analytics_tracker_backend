from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.db.database import db
from tests.helpers import API, DEFAULT_PASSWORD, Account, AuthActions, IngestActions, ProjectActions, make_event


@pytest.fixture
async def super_admin(auth: AuthActions) -> Account:
    """Super admin is set in the database only (scripts/create_superadmin.py), never via the API."""
    account = await auth.register(organization_name="Platform Owner")
    await db.execute("UPDATE users SET is_superadmin = true WHERE id = $1", account.user_id)
    return account


async def admin_get(client: AsyncClient, super_admin: Account, path: str, **params) -> dict:
    response = await client.get(f"{API}/admin{path}", headers=super_admin.headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


class TestAccess:
    ROUTES = [
        ("GET", "/stats"),
        ("GET", "/organizations"),
        ("POST", "/organizations"),
        ("GET", f"/organizations/{uuid4()}"),
        ("PATCH", f"/organizations/{uuid4()}"),
        ("GET", "/users"),
        ("PATCH", f"/users/{uuid4()}"),
    ]

    @pytest.mark.parametrize(("method", "path"), ROUTES)
    async def test_org_admins_are_refused(self, client: AsyncClient, auth: AuthActions, method: str, path: str):
        org_admin = await auth.register()
        response = await client.request(method, f"{API}/admin{path}", headers=org_admin.headers, json={})
        assert response.status_code == 403

    @pytest.mark.parametrize(("method", "path"), ROUTES)
    async def test_needs_login(self, client: AsyncClient, method: str, path: str):
        response = await client.request(method, f"{API}/admin{path}", json={})
        assert response.status_code == 401

    async def test_me_shows_the_flag(self, client: AsyncClient, super_admin: Account):
        me = await client.get(f"{API}/auth/me", headers=super_admin.headers)
        assert me.json()["data"]["user"]["is_superadmin"] is True


class TestStats:
    async def test_platform_totals(
        self, client: AsyncClient, super_admin: Account, auth: AuthActions, projects: ProjectActions, ingest: IngestActions
    ):
        customer = await auth.register()
        key = (await projects.create(customer))["api_key"]["key"]
        await ingest.send(key, [make_event(minutes_ago=0.1), make_event(minutes_ago=0.1)])
        await db.execute("UPDATE organizations SET is_active = false WHERE id = $1", customer.org_id)
        await db.execute("UPDATE users SET is_active = false WHERE id = $1", customer.user_id)

        stats = await admin_get(client, super_admin, "/stats")
        assert stats == {
            "organizations": 2, "active_organizations": 1,
            "users": 2, "active_users": 1,
            "projects": 1, "events_today": 2,
        }


class TestOrganizations:
    async def test_list_with_counts_newest_first(
        self, client: AsyncClient, super_admin: Account, auth: AuthActions, projects: ProjectActions
    ):
        customer = await auth.register(organization_name="Acme Motors")
        await projects.create(customer)

        page = await admin_get(client, super_admin, "/organizations")
        assert page["total"] == 2
        newest = page["items"][0]
        assert (newest["name"], newest["member_count"], newest["project_count"]) == ("Acme Motors", 1, 1)

    async def test_search_and_pagination(self, client: AsyncClient, super_admin: Account, auth: AuthActions):
        for name in ("Acme Motors", "Acme Bikes", "Zeta Labs"):
            await auth.register(organization_name=name)
        page = await admin_get(client, super_admin, "/organizations", search="acme", limit=1, offset=1)
        assert (len(page["items"]), page["total"]) == (1, 2)
        assert page["items"][0]["name"] == "Acme Motors"  # older of the two

    async def test_create_with_a_new_admin_account(self, client: AsyncClient, super_admin: Account, auth: AuthActions):
        email = auth.new_email()
        response = await client.post(
            f"{API}/admin/organizations",
            headers=super_admin.headers,
            json={"organization_name": "Big Customer", "plan": "pro", "admin_email": email, "admin_password": DEFAULT_PASSWORD},
        )
        assert response.status_code == 201
        org = response.json()["data"]["organization"]
        assert (org["name"], org["plan"], org["member_count"]) == ("Big Customer", "pro", 1)

        # The new admin can log in and manage that organization.
        owner = await auth.login(email)
        assert str(owner.org_id) == org["id"]
        detail = await client.get(f"{API}/orgs/{owner.org_id}", headers=owner.headers)
        assert detail.json()["data"]["your_role"] == "admin"

    async def test_create_for_an_existing_account(self, client: AsyncClient, super_admin: Account, auth: AuthActions):
        existing = await auth.register()
        response = await client.post(
            f"{API}/admin/organizations",
            headers=super_admin.headers,
            json={"organization_name": "Second Org", "admin_email": existing.email},
        )
        assert response.status_code == 201
        listed = await client.get(f"{API}/orgs", headers=existing.headers)
        assert len(listed.json()["data"]) == 2

    async def test_create_for_a_new_email_needs_a_password(self, client: AsyncClient, super_admin: Account, auth: AuthActions):
        response = await client.post(
            f"{API}/admin/organizations",
            headers=super_admin.headers,
            json={"organization_name": "No Password", "admin_email": auth.new_email()},
        )
        assert response.status_code == 400
        assert await db.fetchval("SELECT count(*) FROM organizations WHERE name = 'No Password'") == 0

    async def test_detail_lists_members(self, client: AsyncClient, super_admin: Account, auth: AuthActions):
        customer = await auth.register()
        detail = await admin_get(client, super_admin, f"/organizations/{customer.org_id}")
        assert [(m["email"], m["role"]) for m in detail["members"]] == [(customer.email, "admin")]

    async def test_unknown_org(self, client: AsyncClient, super_admin: Account):
        get = await client.get(f"{API}/admin/organizations/{uuid4()}", headers=super_admin.headers)
        patch = await client.patch(f"{API}/admin/organizations/{uuid4()}", headers=super_admin.headers, json={"name": "New"})
        assert get.status_code == patch.status_code == 404

    async def test_rename_and_change_plan(self, client: AsyncClient, super_admin: Account, auth: AuthActions):
        customer = await auth.register(organization_name="Acme")
        response = await client.patch(
            f"{API}/admin/organizations/{customer.org_id}",
            headers=super_admin.headers,
            json={"name": "Acme Group", "plan": "enterprise"},
        )
        org = response.json()["data"]["organization"]
        assert (org["name"], org["plan"], org["is_active"]) == ("Acme Group", "enterprise", True)

    async def test_suspend_and_reactivate(self, client: AsyncClient, super_admin: Account, auth: AuthActions):
        customer = await auth.register()
        org_url = f"{API}/admin/organizations/{customer.org_id}"

        await client.patch(org_url, headers=super_admin.headers, json={"is_active": False})
        blocked = await client.get(f"{API}/orgs/{customer.org_id}", headers=customer.headers)
        assert blocked.status_code == 403

        await client.patch(org_url, headers=super_admin.headers, json={"is_active": True})
        allowed = await client.get(f"{API}/orgs/{customer.org_id}", headers=customer.headers)
        assert allowed.status_code == 200

    async def test_unknown_plan(self, client: AsyncClient, super_admin: Account, auth: AuthActions):
        customer = await auth.register()
        response = await client.patch(
            f"{API}/admin/organizations/{customer.org_id}", headers=super_admin.headers, json={"plan": "gold"}
        )
        assert response.status_code == 422


class TestUsers:
    async def test_list_and_search(self, client: AsyncClient, super_admin: Account, auth: AuthActions):
        customer = await auth.register()
        everyone = await admin_get(client, super_admin, "/users")
        found = await admin_get(client, super_admin, "/users", search=customer.email.split("@")[0])
        assert everyone["total"] == 2
        assert [(u["email"], u["organization_count"]) for u in found["items"]] == [(customer.email, 1)]

    async def test_search_treats_percent_as_plain_text(self, client: AsyncClient, super_admin: Account, auth: AuthActions):
        await auth.register(organization_name="Acme 100% Motors")
        await auth.register(organization_name="Acme 1000 Motors")
        page = await admin_get(client, super_admin, "/organizations", search="100%")
        assert [o["name"] for o in page["items"]] == ["Acme 100% Motors"]

    async def test_deactivate_logs_the_user_out_everywhere(self, client: AsyncClient, super_admin: Account, auth: AuthActions):
        customer = await auth.register()
        response = await client.patch(
            f"{API}/admin/users/{customer.user_id}", headers=super_admin.headers, json={"is_active": False}
        )
        assert response.status_code == 200
        assert response.json()["data"]["is_active"] is False

        me = await client.get(f"{API}/auth/me", headers=customer.headers)
        refresh = await client.post(f"{API}/auth/refresh", json={"refresh_token": customer.refresh_token})
        login = await client.post(f"{API}/auth/login", json={"email": customer.email, "password": customer.password})
        assert (me.status_code, refresh.status_code, login.status_code) == (403, 401, 403)

    async def test_reactivate(self, client: AsyncClient, super_admin: Account, auth: AuthActions):
        customer = await auth.register()
        url = f"{API}/admin/users/{customer.user_id}"
        await client.patch(url, headers=super_admin.headers, json={"is_active": False})
        await client.patch(url, headers=super_admin.headers, json={"is_active": True})
        await auth.login(customer.email)  # asserts 200

    async def test_cannot_deactivate_yourself(self, client: AsyncClient, super_admin: Account):
        response = await client.patch(
            f"{API}/admin/users/{super_admin.user_id}", headers=super_admin.headers, json={"is_active": False}
        )
        assert response.status_code == 400

    async def test_unknown_user(self, client: AsyncClient, super_admin: Account):
        response = await client.patch(f"{API}/admin/users/{uuid4()}", headers=super_admin.headers, json={"is_active": False})
        assert response.status_code == 404
