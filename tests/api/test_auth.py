from httpx import AsyncClient

from app.db.database import db
from tests.helpers import API, DEFAULT_PASSWORD, AuthActions


class TestRegister:
    async def test_creates_user_and_org_with_user_as_admin(self, client: AsyncClient, auth: AuthActions):
        account = await auth.register(organization_name="Acme Motors")

        response = await client.get(f"{API}/auth/me", headers=account.headers)
        assert response.status_code == 200
        me = response.json()["data"]
        assert me["user"]["email"] == account.email
        assert me["user"]["is_superadmin"] is False
        assert [(org["name"], org["role"]) for org in me["organizations"]] == [("Acme Motors", "admin")]

    async def test_password_is_stored_hashed(self, auth: AuthActions):
        account = await auth.register()
        stored = await db.fetchval("SELECT password_hash FROM users WHERE email = $1", account.email)
        assert stored != account.password
        assert stored.startswith("$argon2")

    async def test_duplicate_email_is_rejected(self, client: AsyncClient, auth: AuthActions):
        account = await auth.register()
        response = await client.post(
            f"{API}/auth/register",
            json={"email": account.email, "password": DEFAULT_PASSWORD, "organization_name": "Other"},
        )
        assert response.status_code == 409

    async def test_short_password_gives_a_validation_error(self, client: AsyncClient, auth: AuthActions):
        response = await client.post(
            f"{API}/auth/register",
            json={"email": auth.new_email(), "password": "short", "organization_name": "Acme"},
        )
        assert response.status_code == 422
        body = response.json()
        assert body["status"] == 422
        assert body["error"].startswith("password:")


class TestLogin:
    async def test_correct_password(self, client: AsyncClient, auth: AuthActions):
        account = await auth.register()
        response = await client.post(
            f"{API}/auth/login", json={"email": account.email, "password": account.password}
        )
        assert response.status_code == 200
        assert response.json()["data"]["token_type"] == "bearer"

    async def test_wrong_password_and_unknown_email_give_the_same_error(
        self, client: AsyncClient, auth: AuthActions
    ):
        # Same message for both, so the API doesn't reveal which emails have accounts.
        account = await auth.register()
        wrong_password = await client.post(
            f"{API}/auth/login", json={"email": account.email, "password": "wrong-password"}
        )
        unknown_email = await client.post(
            f"{API}/auth/login", json={"email": auth.new_email(), "password": "wrong-password"}
        )
        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json()["error"] == unknown_email.json()["error"]

    async def test_disabled_account_cannot_log_in(self, client: AsyncClient, auth: AuthActions):
        account = await auth.register()
        await db.execute("UPDATE users SET is_active = false WHERE email = $1", account.email)
        response = await client.post(
            f"{API}/auth/login", json={"email": account.email, "password": account.password}
        )
        assert response.status_code == 403


class TestMe:
    async def test_without_token(self, client: AsyncClient):
        response = await client.get(f"{API}/auth/me")
        assert response.status_code == 401

    async def test_with_invalid_token(self, client: AsyncClient):
        response = await client.get(f"{API}/auth/me", headers={"Authorization": "Bearer nonsense"})
        assert response.status_code == 401

    async def test_disabled_account_is_blocked_immediately(self, client: AsyncClient, auth: AuthActions):
        # The access token is still valid, but the user is reloaded on every request.
        account = await auth.register()
        await db.execute("UPDATE users SET is_active = false WHERE email = $1", account.email)
        response = await client.get(f"{API}/auth/me", headers=account.headers)
        assert response.status_code == 403


class TestRefreshAndLogout:
    async def test_refresh_gives_new_tokens_and_uses_up_the_old_one(
        self, client: AsyncClient, auth: AuthActions
    ):
        account = await auth.register()

        first = await client.post(f"{API}/auth/refresh", json={"refresh_token": account.refresh_token})
        assert first.status_code == 200
        assert first.json()["data"]["refresh_token"] != account.refresh_token

        reused = await client.post(f"{API}/auth/refresh", json={"refresh_token": account.refresh_token})
        assert reused.status_code == 401

    async def test_logout_revokes_the_refresh_token(self, client: AsyncClient, auth: AuthActions):
        account = await auth.register()

        logout = await client.post(f"{API}/auth/logout", json={"refresh_token": account.refresh_token})
        assert logout.status_code == 200

        refresh = await client.post(f"{API}/auth/refresh", json={"refresh_token": account.refresh_token})
        assert refresh.status_code == 401

    async def test_unknown_refresh_token(self, client: AsyncClient):
        response = await client.post(f"{API}/auth/refresh", json={"refresh_token": "made-up"})
        assert response.status_code == 401
