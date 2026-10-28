"""Small helpers so tests read as steps ("register a user") instead of raw HTTP calls."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from httpx import AsyncClient, Response

API = "/api/v1"
DEFAULT_PASSWORD = "Str0ng-pass-word"


@dataclass
class Account:
    """A logged-in user, their tokens, and their first organization (from /auth/me)."""

    email: str
    password: str
    access_token: str
    refresh_token: str
    user_id: UUID
    org_id: UUID | None

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


class AuthActions:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    @staticmethod
    def new_email() -> str:
        return f"user-{uuid4().hex[:8]}@demo-hack.io"

    async def register(
        self,
        email: str | None = None,
        password: str = DEFAULT_PASSWORD,
        organization_name: str = "Acme Motors",
    ) -> Account:
        """New account and organization; the account is that organization's admin."""
        email = email or self.new_email()
        response = await self._client.post(
            f"{API}/auth/register",
            json={"email": email, "password": password, "organization_name": organization_name},
        )
        assert response.status_code == 201, response.text
        return await self._account(email, password, response.json()["data"])

    async def login(self, email: str, password: str = DEFAULT_PASSWORD) -> Account:
        response = await self._client.post(
            f"{API}/auth/login", json={"email": email, "password": password}
        )
        assert response.status_code == 200, response.text
        return await self._account(email, password, response.json()["data"])

    async def _account(self, email: str, password: str, tokens: dict) -> Account:
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        me = (await self._client.get(f"{API}/auth/me", headers=headers)).json()["data"]
        orgs = me["organizations"]
        return Account(
            email=email,
            password=password,
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            user_id=UUID(me["user"]["id"]),
            org_id=UUID(orgs[0]["id"]) if orgs else None,
        )


class OrgActions:
    def __init__(self, client: AsyncClient, auth: AuthActions) -> None:
        self._client = client
        self._auth = auth

    async def add_new_member(self, admin: Account, role: str) -> Account:
        """An admin creates a brand-new account in their organization; returns it logged in."""
        email = self._auth.new_email()
        response = await self._client.post(
            f"{API}/orgs/{admin.org_id}/members",
            headers=admin.headers,
            json={"email": email, "role": role, "password": DEFAULT_PASSWORD},
        )
        assert response.status_code == 201, response.text
        return await self._auth.login(email)


class ProjectActions:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def create(self, admin: Account, name: str = "Car App", **fields) -> dict:
        """Returns {"project": {...}, "api_key": {... "key": "pk_live_..."}}."""
        response = await self._client.post(
            f"{API}/orgs/{admin.org_id}/projects",
            headers=admin.headers,
            json={"name": name, "platform": "flutter", **fields},
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]


def make_event(event: str = "app_open", distinct_id: str = "anon-1", minutes_ago: float = 1, **fields) -> dict:
    """An event as an SDK sends it, with a fresh id. Override any field with keyword arguments."""
    timestamp = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return {"id": str(uuid4()), "event": event, "distinct_id": distinct_id, "timestamp": timestamp.isoformat(), **fields}


class IngestActions:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def send(
        self,
        api_key: str | None,
        events: list[dict],
        context: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        body: dict = {"events": events}
        if context is not None:
            body["context"] = context
        key_header = {"X-API-Key": api_key} if api_key else {}
        return await self._client.post(f"{API}/ingest/batch", json=body, headers={**key_header, **(headers or {})})
