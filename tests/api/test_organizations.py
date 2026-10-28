from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.db.database import db
from tests.helpers import API, DEFAULT_PASSWORD, Account, AuthActions, OrgActions


def org_url(account: Account, path: str = "") -> str:
    return f"{API}/orgs/{account.org_id}{path}"


async def member_emails(client: AsyncClient, account: Account) -> set[str]:
    response = await client.get(org_url(account, "/members"), headers=account.headers)
    assert response.status_code == 200, response.text
    return {m["email"] for m in response.json()["data"]}


class TestReadOrganization:
    async def test_list_my_organizations(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register(organization_name="Acme Motors")
        response = await client.get(f"{API}/orgs", headers=admin.headers)
        assert response.status_code == 200
        assert [(o["name"], o["role"]) for o in response.json()["data"]] == [("Acme Motors", "admin")]

    async def test_get_organization_shows_your_role(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register(organization_name="Acme Motors")
        response = await client.get(org_url(admin), headers=admin.headers)
        assert response.status_code == 200
        org = response.json()["data"]
        assert (org["name"], org["slug"], org["your_role"]) == ("Acme Motors", "acme-motors", "admin")

    async def test_same_name_gets_a_different_slug(self, client: AsyncClient, auth: AuthActions):
        first = await auth.register(organization_name="Acme Motors")
        second = await auth.register(organization_name="Acme Motors")
        slugs = [
            (await client.get(org_url(a), headers=a.headers)).json()["data"]["slug"] for a in (first, second)
        ]
        assert slugs[0] == "acme-motors"
        assert slugs[1].startswith("acme-motors-") and slugs[1] != slugs[0]

    async def test_non_member_gets_404_same_as_missing_org(self, client: AsyncClient, auth: AuthActions):
        # Same answer for "exists but not yours" and "doesn't exist", so org ids can't be probed.
        owner = await auth.register()
        outsider = await auth.register()
        not_yours = await client.get(org_url(owner), headers=outsider.headers)
        missing = await client.get(f"{API}/orgs/{uuid4()}", headers=outsider.headers)
        assert not_yours.status_code == missing.status_code == 404
        assert not_yours.json() == missing.json()

    async def test_suspended_org_is_blocked(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register()
        await db.execute("UPDATE organizations SET is_active = false WHERE id = $1", admin.org_id)
        response = await client.get(org_url(admin), headers=admin.headers)
        assert response.status_code == 403

    async def test_needs_login(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register()
        response = await client.get(org_url(admin))
        assert response.status_code == 401


class TestRoles:
    @pytest.mark.parametrize("role", ["viewer", "analyst"])
    async def test_non_admins_can_read(self, client: AsyncClient, auth: AuthActions, orgs: OrgActions, role: str):
        admin = await auth.register()
        member = await orgs.add_new_member(admin, role)

        org = await client.get(org_url(member), headers=member.headers)
        assert org.status_code == 200
        assert org.json()["data"]["your_role"] == role
        assert await member_emails(client, member) == {admin.email, member.email}

    @pytest.mark.parametrize("role", ["viewer", "analyst"])
    async def test_non_admins_cannot_manage_members(
        self, client: AsyncClient, auth: AuthActions, orgs: OrgActions, role: str
    ):
        admin = await auth.register()
        member = await orgs.add_new_member(admin, role)

        add = await client.post(
            org_url(member, "/members"),
            headers=member.headers,
            json={"email": auth.new_email(), "password": DEFAULT_PASSWORD},
        )
        change = await client.patch(
            org_url(member, f"/members/{admin.user_id}"), headers=member.headers, json={"role": "viewer"}
        )
        remove = await client.delete(org_url(member, f"/members/{admin.user_id}"), headers=member.headers)
        assert add.status_code == change.status_code == remove.status_code == 403

    async def test_super_admin_acts_as_admin_in_any_org(self, client: AsyncClient, auth: AuthActions):
        owner = await auth.register()
        super_admin = await auth.register()
        await db.execute("UPDATE users SET is_superadmin = true WHERE id = $1", super_admin.user_id)

        response = await client.get(org_url(owner), headers=super_admin.headers)
        assert response.status_code == 200
        assert response.json()["data"]["your_role"] == "admin"


class TestAddMember:
    async def test_new_email_creates_an_account_that_can_log_in(
        self, client: AsyncClient, auth: AuthActions, orgs: OrgActions
    ):
        admin = await auth.register(organization_name="Acme Motors")
        analyst = await orgs.add_new_member(admin, "analyst")

        assert analyst.org_id == admin.org_id
        listed = await client.get(f"{API}/orgs", headers=analyst.headers)
        assert [(o["name"], o["role"]) for o in listed.json()["data"]] == [("Acme Motors", "analyst")]

    async def test_new_email_without_password_is_rejected(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register()
        response = await client.post(
            org_url(admin, "/members"), headers=admin.headers, json={"email": auth.new_email()}
        )
        assert response.status_code == 400

    async def test_existing_account_is_added_without_password(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register()
        other = await auth.register(organization_name="Other Co")

        response = await client.post(
            org_url(admin, "/members"), headers=admin.headers, json={"email": other.email, "role": "viewer"}
        )
        assert response.status_code == 201
        listed = await client.get(f"{API}/orgs", headers=other.headers)
        assert len(listed.json()["data"]) == 2

    async def test_default_role_is_viewer(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register()
        response = await client.post(
            org_url(admin, "/members"),
            headers=admin.headers,
            json={"email": auth.new_email(), "password": DEFAULT_PASSWORD},
        )
        assert response.json()["data"]["role"] == "viewer"

    async def test_adding_a_member_twice_is_rejected(self, client: AsyncClient, auth: AuthActions, orgs: OrgActions):
        admin = await auth.register()
        member = await orgs.add_new_member(admin, "viewer")
        response = await client.post(
            org_url(admin, "/members"), headers=admin.headers, json={"email": member.email}
        )
        assert response.status_code == 409

    async def test_unknown_role_gives_a_validation_error(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register()
        response = await client.post(
            org_url(admin, "/members"),
            headers=admin.headers,
            json={"email": auth.new_email(), "password": DEFAULT_PASSWORD, "role": "owner"},
        )
        assert response.status_code == 422


class TestChangeRole:
    async def test_admin_promotes_a_viewer(self, client: AsyncClient, auth: AuthActions, orgs: OrgActions):
        admin = await auth.register()
        viewer = await orgs.add_new_member(admin, "viewer")

        response = await client.patch(
            org_url(admin, f"/members/{viewer.user_id}"), headers=admin.headers, json={"role": "analyst"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["role"] == "analyst"

        # Takes effect on the member's next request, with the same access token.
        org = await client.get(org_url(viewer), headers=viewer.headers)
        assert org.json()["data"]["your_role"] == "analyst"

    async def test_last_admin_cannot_be_demoted(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register()
        response = await client.patch(
            org_url(admin, f"/members/{admin.user_id}"), headers=admin.headers, json={"role": "viewer"}
        )
        assert response.status_code == 409

    async def test_admin_can_step_down_when_another_admin_exists(
        self, client: AsyncClient, auth: AuthActions, orgs: OrgActions
    ):
        admin = await auth.register()
        await orgs.add_new_member(admin, "admin")
        response = await client.patch(
            org_url(admin, f"/members/{admin.user_id}"), headers=admin.headers, json={"role": "viewer"}
        )
        assert response.status_code == 200

    async def test_unknown_member(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register()
        response = await client.patch(
            org_url(admin, f"/members/{uuid4()}"), headers=admin.headers, json={"role": "viewer"}
        )
        assert response.status_code == 404


class TestRemoveMember:
    async def test_admin_removes_a_member(self, client: AsyncClient, auth: AuthActions, orgs: OrgActions):
        admin = await auth.register()
        viewer = await orgs.add_new_member(admin, "viewer")

        response = await client.delete(org_url(admin, f"/members/{viewer.user_id}"), headers=admin.headers)
        assert response.status_code == 200
        assert await member_emails(client, admin) == {admin.email}

        # The removed user loses access at once.
        org = await client.get(org_url(viewer), headers=viewer.headers)
        assert org.status_code == 404

    async def test_member_can_leave(self, client: AsyncClient, auth: AuthActions, orgs: OrgActions):
        admin = await auth.register()
        viewer = await orgs.add_new_member(admin, "viewer")

        response = await client.delete(org_url(viewer, f"/members/{viewer.user_id}"), headers=viewer.headers)
        assert response.status_code == 200
        assert await member_emails(client, admin) == {admin.email}

    async def test_last_admin_cannot_leave(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register()
        response = await client.delete(org_url(admin, f"/members/{admin.user_id}"), headers=admin.headers)
        assert response.status_code == 409

    async def test_unknown_member(self, client: AsyncClient, auth: AuthActions):
        admin = await auth.register()
        response = await client.delete(org_url(admin, f"/members/{uuid4()}"), headers=admin.headers)
        assert response.status_code == 404
