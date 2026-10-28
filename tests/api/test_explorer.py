"""Event feed, event names, users list and one user's detail. Data goes in through /ingest."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.db.database import db
from tests.helpers import API, Account, AuthActions, IngestActions, OrgActions, ProjectActions, make_event


class Project:
    def __init__(self, admin: Account, project_id: str, key: str, client: AsyncClient, ingest: IngestActions) -> None:
        self.admin = admin
        self.id = project_id
        self.key = key
        self._client = client
        self._ingest = ingest

    def url(self, path: str) -> str:
        return f"{API}/orgs/{self.admin.org_id}/projects/{self.id}{path}"

    async def send(self, *events: dict, context: dict | None = None) -> None:
        response = await self._ingest.send(self.key, list(events), context=context)
        assert response.status_code == 202 and response.json()["data"]["accepted"] == len(events), response.text

    async def get(self, path: str, account: Account | None = None, **params) -> dict:
        response = await self._client.get(self.url(path), headers=(account or self.admin).headers, params=params)
        assert response.status_code == 200, response.text
        return response.json()["data"]


@pytest.fixture
async def project(client: AsyncClient, auth: AuthActions, projects: ProjectActions, ingest: IngestActions) -> Project:
    admin = await auth.register()
    created = await projects.create(admin)
    return Project(admin, created["project"]["id"], created["api_key"]["key"], client, ingest)


async def person_id(distinct_id: str) -> str:
    return str(await db.fetchval("SELECT id FROM persons WHERE distinct_id = $1", distinct_id))


class TestEventFeed:
    async def test_newest_first_with_all_fields(self, project: Project):
        await project.send(
            make_event("first", minutes_ago=3),
            make_event("second", minutes_ago=2, screen_name="Home", properties={"model": "Nexon"}),
            context={"platform": "flutter", "os": "Android 14"},
        )
        items = (await project.get("/events"))["items"]
        assert [e["event_name"] for e in items] == ["second", "first"]
        assert (items[0]["screen_name"], items[0]["os"], items[0]["properties"]) == ("Home", "Android 14", {"model": "Nexon"})

    async def test_filter_by_event_name(self, project: Project):
        await project.send(make_event("app_open"), make_event("purchase"), make_event("app_open"))
        items = (await project.get("/events", event="app_open"))["items"]
        assert {e["event_name"] for e in items} == {"app_open"} and len(items) == 2

    async def test_filter_by_person(self, project: Project):
        await project.send(make_event(distinct_id="alice"), make_event(distinct_id="bob"))
        items = (await project.get("/events", person_id=await person_id("alice")))["items"]
        assert [e["distinct_id"] for e in items] == ["alice"]

    @pytest.mark.parametrize("search", ["alice", "checkout", "nexon"])
    async def test_search_user_screen_and_properties(self, project: Project, search: str):
        await project.send(
            make_event(distinct_id="alice@acme"),
            make_event(screen_name="Checkout"),
            make_event(properties={"model": "Nexon EV"}),
            make_event(distinct_id="someone-else"),
        )
        assert len((await project.get("/events", search=search))["items"]) == 1

    async def test_search_treats_percent_and_underscore_as_plain_text(self, project: Project):
        # "_" and "%" are wildcards in SQL LIKE; a search for "a_b" must not also match "axb".
        await project.send(make_event(distinct_id="a_b"), make_event(distinct_id="axb"))
        items = (await project.get("/events", search="a_b"))["items"]
        assert [e["distinct_id"] for e in items] == ["a_b"]

    async def test_cursor_pages_through_everything_once(self, project: Project):
        await project.send(*[make_event(f"e{i}", minutes_ago=10 - i) for i in range(5)])

        seen, cursor, pages = [], None, 0
        while True:
            params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
            page = await project.get("/events", **params)
            seen += [e["event_name"] for e in page["items"]]
            pages += 1
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert (seen, pages) == (["e4", "e3", "e2", "e1", "e0"], 3)

    async def test_new_events_dont_shift_the_next_page(self, project: Project):
        await project.send(*[make_event(f"e{i}", minutes_ago=10 - i) for i in range(3)])
        first = await project.get("/events", limit=2)
        await project.send(make_event("newer"))  # arrives while the user is scrolling
        second = await project.get("/events", limit=2, cursor=first["next_cursor"])
        assert [e["event_name"] for e in second["items"]] == ["e0"]

    async def test_invalid_cursor_and_limit(self, client: AsyncClient, project: Project):
        headers = project.admin.headers
        assert (await client.get(project.url("/events"), params={"cursor": "garbage"}, headers=headers)).status_code == 400
        assert (await client.get(project.url("/events"), params={"limit": 101}, headers=headers)).status_code == 422


class TestEventDefinitions:
    async def test_most_recently_seen_first(self, project: Project):
        await project.send(make_event("old_one", minutes_ago=30), make_event("new_one", minutes_ago=1))
        names = [d["event_name"] for d in await project.get("/event-definitions")]
        assert names == ["new_one", "old_one"]


class TestPersons:
    async def test_list_with_counts_and_last_os(self, project: Project):
        await project.send(make_event(distinct_id="anon", minutes_ago=5, session_id=str(uuid4())), context={"os": "iOS 18"})
        await project.send(
            make_event("$identify", distinct_id="user-42", properties={"plan": "pro"}),
            make_event(distinct_id="user-42"),
        )
        page = await project.get("/persons")
        assert [p["distinct_id"] for p in page["items"]] == ["user-42", "anon"]  # most recently active first
        by_id = {p["distinct_id"]: p for p in page["items"]}
        assert (by_id["user-42"]["is_identified"], by_id["user-42"]["event_count"]) == (True, 2)
        assert (by_id["anon"]["is_identified"], by_id["anon"]["last_os"]) == (False, "iOS 18")
        assert page["counts"] == {"all": 2, "identified": 1, "new": 2}

    async def test_filters(self, project: Project):
        await project.send(
            make_event(distinct_id="old-visitor", minutes_ago=10 * 24 * 60),
            make_event("$identify", distinct_id="user-42", properties={"plan": "pro"}),
        )
        identified = await project.get("/persons", filter="identified")
        new = await project.get("/persons", filter="new")
        assert [p["distinct_id"] for p in identified["items"]] == ["user-42"]
        assert [p["distinct_id"] for p in new["items"]] == ["user-42"]
        assert new["counts"] == {"all": 2, "identified": 1, "new": 1}

    async def test_search_by_trait(self, project: Project):
        await project.send(
            make_event("$identify", distinct_id="u1", properties={"city": "Pune"}),
            make_event("$identify", distinct_id="u2", properties={"city": "Delhi"}),
        )
        page = await project.get("/persons", search="pune")
        assert ([p["distinct_id"] for p in page["items"]], page["total"]) == (["u1"], 1)

    async def test_search_treats_underscore_as_plain_text(self, project: Project):
        await project.send(make_event(distinct_id="a_b"), make_event(distinct_id="axb"))
        page = await project.get("/persons", search="a_b")
        assert [p["distinct_id"] for p in page["items"]] == ["a_b"]

    async def test_pagination(self, project: Project):
        await project.send(*[make_event(distinct_id=f"u{i}", minutes_ago=10 - i) for i in range(5)])
        page = await project.get("/persons", limit=2, offset=2)
        assert ([p["distinct_id"] for p in page["items"]], page["total"]) == (["u2", "u1"], 5)


class TestPersonDetail:
    async def test_sessions_with_their_events(self, project: Project):
        first, second = str(uuid4()), str(uuid4())
        await project.send(
            make_event("a", distinct_id="alice", session_id=first, minutes_ago=30, screen_name="Home"),
            make_event("b", distinct_id="alice", session_id=first, minutes_ago=28, screen_name="Cars"),
            make_event("c", distinct_id="alice", session_id=second, minutes_ago=5),
        )
        detail = await project.get(f"/persons/{await person_id('alice')}")
        assert detail["stats"] == {"sessions": 2, "events": 3}
        assert [s["id"] for s in detail["sessions"]] == [second, first]  # newest session first
        older = detail["sessions"][1]
        assert (older["entry_path"], older["exit_path"], older["duration_seconds"]) == ("Home", "Cars", 120)
        assert [e["event_name"] for e in older["events"]] == ["b", "a"]

    async def test_unknown_person(self, client: AsyncClient, project: Project):
        response = await client.get(project.url(f"/persons/{uuid4()}"), headers=project.admin.headers)
        assert response.status_code == 404

    async def test_person_of_another_project(
        self, client: AsyncClient, project: Project, auth: AuthActions, projects: ProjectActions, ingest: IngestActions
    ):
        await project.send(make_event(distinct_id="alice"))
        # Same org, second project: the person id must not leak across projects.
        other_id = (await projects.create(project.admin, name="Other App"))["project"]["id"]
        url = f"{API}/orgs/{project.admin.org_id}/projects/{other_id}/persons/{await person_id('alice')}"
        assert (await client.get(url, headers=project.admin.headers)).status_code == 404


class TestAccess:
    @pytest.mark.parametrize("path", ["/events", "/event-definitions", "/persons"])
    async def test_viewer_can_read(self, project: Project, orgs: OrgActions, path: str):
        viewer = await orgs.add_new_member(project.admin, "viewer")
        await project.get(path, account=viewer)

    @pytest.mark.parametrize("path", ["/events", "/event-definitions", "/persons", f"/persons/{uuid4()}"])
    async def test_project_of_another_org(self, client: AsyncClient, project: Project, auth: AuthActions, path: str):
        other = await auth.register()
        url = f"{API}/orgs/{other.org_id}/projects/{project.id}{path}"
        assert (await client.get(url, headers=other.headers)).status_code == 404
