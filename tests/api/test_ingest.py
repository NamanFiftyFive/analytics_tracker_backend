import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.db.database import db
from tests.helpers import API, AuthActions, IngestActions, ProjectActions, make_event


@pytest.fixture
async def project(auth: AuthActions, projects: ProjectActions) -> dict:
    """A project with no origin restriction; `project["key"]` is its API key."""
    admin = await auth.register()
    created = await projects.create(admin)
    return {**created["project"], "key": created["api_key"]["key"], "key_id": created["api_key"]["id"]}


async def count(table: str) -> int:
    return await db.fetchval(f"SELECT count(*) FROM {table}")


class TestStoring:
    async def test_stores_events_with_device_context(self, ingest: IngestActions, project: dict):
        context = {"platform": "flutter", "os": "Android 14", "device_type": "mobile", "app_version": "2.3.1", "country": "in"}
        response = await ingest.send(
            project["key"],
            [make_event("app_open", screen_name="Home"), make_event("test_drive_booked", properties={"model": "Nexon EV"})],
            context=context,
        )
        assert response.status_code == 202
        assert response.json()["data"] == {"accepted": 2, "duplicates": 0, "rejected": []}

        rows = await db.fetch("SELECT event_name, platform, os, app_version, country, properties FROM events ORDER BY occurred_at")
        assert len(rows) == 2
        assert {r["country"] for r in rows} == {"IN"}  # upper-cased
        assert {(r["platform"], r["os"], r["app_version"]) for r in rows} == {("flutter", "Android 14", "2.3.1")}
        booked = next(r for r in rows if r["event_name"] == "test_drive_booked")
        assert booked["properties"] == {"model": "Nexon EV"}

    async def test_creates_person_and_event_definitions(self, ingest: IngestActions, project: dict):
        await ingest.send(
            project["key"],
            [make_event("app_open", minutes_ago=5), make_event("app_open", minutes_ago=2), make_event("purchase")],
        )
        assert await count("persons") == 1
        names = await db.fetch("SELECT event_name FROM event_definitions ORDER BY event_name")
        assert [r["event_name"] for r in names] == ["app_open", "purchase"]
        person = await db.fetchrow("SELECT first_seen_at, last_seen_at FROM persons")
        assert person["first_seen_at"] < person["last_seen_at"]

    async def test_naive_timestamp_is_treated_as_utc(self, ingest: IngestActions, project: dict):
        naive = (datetime.now(UTC) - timedelta(minutes=3)).replace(tzinfo=None, microsecond=0)
        await ingest.send(project["key"], [make_event(timestamp=naive.isoformat())])
        stored = await db.fetchval("SELECT occurred_at FROM events")
        assert stored == naive.replace(tzinfo=UTC)

    async def test_referrer_and_utm_are_kept_as_properties(self, ingest: IngestActions, project: dict):
        session_id = str(uuid4())
        await ingest.send(
            project["key"],
            [make_event("$pageview", session_id=session_id, path="/cars", referrer="https://google.com", utm_source="newsletter")],
        )
        properties = await db.fetchval("SELECT properties FROM events")
        assert properties == {"$referrer": "https://google.com", "$utm_source": "newsletter"}
        session = await db.fetchrow("SELECT referrer, utm_source, entry_path FROM sessions")
        assert tuple(session) == ("https://google.com", "newsletter", "/cars")

    async def test_identify_saves_traits_on_the_person(self, ingest: IngestActions, project: dict):
        await ingest.send(project["key"], [make_event("$identify", distinct_id="user-42", properties={"plan": "pro"})])
        await ingest.send(project["key"], [make_event("$identify", distinct_id="user-42", properties={"city": "Pune"})])
        assert await db.fetchval("SELECT properties FROM persons") == {"plan": "pro", "city": "Pune"}

    async def test_same_event_id_in_two_projects_is_stored_in_both(
        self, ingest: IngestActions, project: dict, auth: AuthActions, projects: ProjectActions
    ):
        other_admin = await auth.register()
        other_key = (await projects.create(other_admin))["api_key"]["key"]
        event = make_event()
        await ingest.send(project["key"], [event])
        await ingest.send(other_key, [event])
        assert await count("events") == 2


class TestSessions:
    async def test_session_spans_batches(self, ingest: IngestActions, project: dict):
        session_id = str(uuid4())
        await ingest.send(
            project["key"],
            [make_event(session_id=session_id, minutes_ago=10, screen_name="Home"),
             make_event(session_id=session_id, minutes_ago=8, screen_name="CarList")],
        )
        await ingest.send(project["key"], [make_event(session_id=session_id, minutes_ago=2, screen_name="Checkout")])

        session = await db.fetchrow("SELECT event_count, entry_path, exit_path, started_at, ended_at FROM sessions")
        assert (session["event_count"], session["entry_path"], session["exit_path"]) == (3, "Home", "Checkout")
        assert session["ended_at"] - session["started_at"] > timedelta(minutes=7)

    async def test_late_event_moves_the_session_start(self, ingest: IngestActions, project: dict):
        # An older event arriving later (e.g. from an offline queue) becomes the entry screen.
        session_id = str(uuid4())
        await ingest.send(project["key"], [make_event(session_id=session_id, minutes_ago=2, screen_name="CarList")])
        await ingest.send(project["key"], [make_event(session_id=session_id, minutes_ago=9, screen_name="Splash")])
        session = await db.fetchrow("SELECT event_count, entry_path, exit_path FROM sessions")
        assert tuple(session) == (2, "Splash", "CarList")


class TestDuplicates:
    async def test_resending_a_batch_stores_nothing_twice(self, ingest: IngestActions, project: dict):
        # What the SDK does after a timeout: send the very same batch again.
        session_id = str(uuid4())
        events = [make_event(session_id=session_id), make_event("purchase", session_id=session_id)]
        await ingest.send(project["key"], events)

        retry = await ingest.send(project["key"], events)
        assert retry.json()["data"] == {"accepted": 0, "duplicates": 2, "rejected": []}
        assert await count("events") == 2
        assert await db.fetchval("SELECT event_count FROM sessions") == 2

    async def test_same_id_twice_in_one_batch(self, ingest: IngestActions, project: dict):
        event = make_event()
        response = await ingest.send(project["key"], [event, event])
        assert response.json()["data"] == {"accepted": 1, "duplicates": 1, "rejected": []}
        assert await count("events") == 1

    async def test_resending_an_event_from_a_fast_device_clock_stores_it_once(self, ingest: IngestActions, project: dict):
        # A phone whose clock is 1 hour ahead: its timestamp is replaced with "now" on arrival.
        # A retry of the same event must still count as a duplicate.
        event = make_event(minutes_ago=-60)
        await ingest.send(project["key"], [event])
        retry = await ingest.send(project["key"], [event])
        assert retry.json()["data"]["duplicates"] == 1
        assert await count("events") == 1


class TestValidation:
    async def test_bad_events_are_rejected_one_by_one(self, ingest: IngestActions, project: dict):
        events = [
            make_event("good_one"),
            {"id": "not-a-uuid", "event": "x", "distinct_id": "a", "timestamp": datetime.now(UTC).isoformat()},
            make_event("missing_user", distinct_id=""),
            make_event("good_two"),
        ]
        response = await ingest.send(project["key"], events)
        assert response.status_code == 202
        data = response.json()["data"]
        assert data["accepted"] == 2
        assert [r["index"] for r in data["rejected"]] == [1, 2]
        assert data["rejected"][0]["error"].startswith("id:")

    async def test_events_older_than_31_days_are_rejected(self, ingest: IngestActions, project: dict):
        response = await ingest.send(project["key"], [make_event(minutes_ago=32 * 24 * 60)])
        assert response.json()["data"]["rejected"] == [{"index": 0, "error": "timestamp: older than 31 days"}]
        assert await count("events") == 0

    async def test_slightly_fast_clock_is_kept(self, ingest: IngestActions, project: dict):
        event = make_event(minutes_ago=-5)
        await ingest.send(project["key"], [event])
        stored = await db.fetchval("SELECT occurred_at FROM events")
        assert stored == datetime.fromisoformat(event["timestamp"])

    async def test_very_fast_clock_is_replaced_with_arrival_time(self, ingest: IngestActions, project: dict):
        await ingest.send(project["key"], [make_event(minutes_ago=-60)])
        stored = await db.fetchval("SELECT occurred_at FROM events")
        assert abs(stored - datetime.now(UTC)) < timedelta(minutes=1)

    async def test_too_large_properties_are_rejected(self, ingest: IngestActions, project: dict):
        response = await ingest.send(project["key"], [make_event(properties={"blob": "x" * 17_000})])
        assert response.json()["data"]["rejected"][0]["index"] == 0

    @pytest.mark.parametrize("events", [[], [make_event() for _ in range(101)]], ids=["empty", "101-events"])
    async def test_batch_size_limits(self, ingest: IngestActions, project: dict, events: list):
        response = await ingest.send(project["key"], events)
        assert response.status_code == 422

    async def test_bad_context_rejects_the_whole_batch(self, ingest: IngestActions, project: dict):
        response = await ingest.send(project["key"], [make_event()], context={"country": "India"})
        assert response.status_code == 422


class TestApiKeyAndOrigin:
    async def test_missing_and_wrong_key(self, ingest: IngestActions, project: dict):
        assert (await ingest.send(None, [make_event()])).status_code == 401
        assert (await ingest.send("pk_live_made-up", [make_event()])).status_code == 401

    async def test_key_in_body_for_send_beacon(self, client: AsyncClient, project: dict):
        response = await client.post(f"{API}/ingest/batch", json={"api_key": project["key"], "events": [make_event()]})
        assert response.status_code == 202

    async def test_records_when_the_key_was_last_used(self, ingest: IngestActions, project: dict):
        await ingest.send(project["key"], [make_event()])
        assert await db.fetchval("SELECT last_used_at FROM api_keys") is not None

    async def test_allowed_origins(self, auth: AuthActions, projects: ProjectActions, ingest: IngestActions):
        admin = await auth.register()
        key = (await projects.create(admin, allowed_origins=["https://cars.example.com"]))["api_key"]["key"]

        allowed = await ingest.send(key, [make_event()], headers={"Origin": "https://Cars.Example.com/"})
        other = await ingest.send(key, [make_event()], headers={"Origin": "https://evil.example.com"})
        mobile_app = await ingest.send(key, [make_event()])  # apps send no Origin header
        assert (allowed.status_code, other.status_code, mobile_app.status_code) == (202, 403, 202)

    async def test_no_allowed_origins_means_any_website(self, ingest: IngestActions, project: dict):
        response = await ingest.send(project["key"], [make_event()], headers={"Origin": "https://any.example.com"})
        assert response.status_code == 202


class TestBrowserSupport:
    async def test_preflight_is_answered_for_any_origin(self, client: AsyncClient):
        response = await client.options(
            f"{API}/ingest/batch",
            headers={"Origin": "https://shop.example.com", "Access-Control-Request-Method": "POST"},
        )
        assert response.status_code == 204
        assert response.headers["access-control-allow-origin"] == "https://shop.example.com"
        assert "X-API-Key" in response.headers["access-control-allow-headers"]

    async def test_response_has_cors_headers_without_credentials(self, ingest: IngestActions, project: dict):
        response = await ingest.send(project["key"], [make_event()], headers={"Origin": "http://localhost:3000"})
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "access-control-allow-credentials" not in response.headers

    async def test_text_plain_body_from_send_beacon(self, client: AsyncClient, project: dict):
        body = json.dumps({"api_key": project["key"], "events": [make_event()]})
        response = await client.post(f"{API}/ingest/batch", content=body, headers={"Content-Type": "text/plain;charset=UTF-8"})
        assert response.status_code == 202

    async def test_body_over_1_mb_is_refused(self, ingest: IngestActions, project: dict):
        response = await ingest.send(project["key"], [make_event(properties={"blob": "x" * 1_100_000})])
        assert response.status_code == 413

    async def test_other_routes_keep_the_strict_cors_rules(self, client: AsyncClient):
        response = await client.get(f"{API}/health", headers={"Origin": "https://evil.example.com"})
        assert "access-control-allow-origin" not in response.headers
