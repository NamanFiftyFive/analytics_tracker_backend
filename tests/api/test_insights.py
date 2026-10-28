"""Insights overview. The numbers are checked through InsightsService with a fixed "now" and
events written straight into the tables at exact times, so day boundaries and the previous
period are predictable. The HTTP tests cover access rules and the response shape."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.db.database import db
from app.services.insights_service import InsightsService, TimeWindow
from tests.helpers import API, Account, AuthActions, OrgActions, ProjectActions

NOW = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)  # a Tuesday, 10:00 UTC (15:30 in India)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


class EventWriter:
    """Writes rows directly, bypassing ingest's "not older than 31 days" rule."""

    def __init__(self, project_id: UUID) -> None:
        self.project_id = project_id

    async def event(self, when: datetime, name: str = "app_open", user: str = "u1", screen: str | None = None) -> None:
        await db.execute(
            "INSERT INTO events (id, project_id, event_name, distinct_id, occurred_at, screen_name) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            uuid4(), self.project_id, name, user, when, screen,
        )

    async def session(self, started: datetime, seconds: int) -> None:
        await db.execute(
            "INSERT INTO sessions (id, project_id, started_at, ended_at) VALUES ($1, $2, $3, $4)",
            uuid4(), self.project_id, started, started + timedelta(seconds=seconds),
        )


class Setup:
    def __init__(self, admin: Account, project_id: UUID) -> None:
        self.admin = admin
        self.project_id = project_id
        self.write = EventWriter(project_id)

    async def overview(self, range_: str = "7d", now: datetime = NOW):
        assert self.admin.org_id is not None
        return await InsightsService().overview(self.admin.org_id, self.project_id, range_, now=now)  # type: ignore[arg-type]


async def make_setup(auth: AuthActions, projects: ProjectActions, timezone: str = "UTC") -> Setup:
    admin = await auth.register()
    project = (await projects.create(admin, timezone=timezone))["project"]
    return Setup(admin, UUID(project["id"]))


class TestTimeWindow:
    def test_7_days_ends_now_and_starts_at_midnight_6_days_ago(self):
        window = TimeWindow.for_range("7d", "UTC", NOW)
        assert (window.start, window.end, window.days) == (at(14, 0), NOW, 7)
        assert window.first_day == date(2026, 10, 14)

    def test_days_start_at_midnight_in_the_project_timezone(self):
        # Midnight in India is 18:30 UTC the evening before.
        window = TimeWindow.for_range("today", "Asia/Kolkata", NOW)
        assert window.start == at(19, 18, 30)
        assert window.first_day == date(2026, 10, 20)

    def test_previous_window_is_the_same_hours_one_period_earlier(self):
        window = TimeWindow.for_range("7d", "UTC", NOW)
        assert (window.previous_start, window.previous_end) == (at(7, 0), at(13, 10))


class TestKpis:
    async def test_counts_events_and_users_in_the_range_only(self, auth: AuthActions, projects: ProjectActions):
        s = await make_setup(auth, projects)
        await s.write.event(at(14, 0, 1), user="a")
        await s.write.event(at(18, 12), user="a")
        await s.write.event(at(20, 9), user="b")
        await s.write.event(at(13, 9), user="c")  # previous period: Oct 7 00:00 to Oct 13 10:00
        await s.write.event(at(13, 23), user="e")  # after the previous period's "now": not counted
        await s.write.event(at(20, 11), user="d")  # after "now": not counted

        kpis = (await s.overview()).kpis
        assert (kpis.events.value, kpis.active_users.value) == (3, 2)
        assert (kpis.events.previous, kpis.active_users.previous) == (1, 1)
        assert kpis.events.change_percent == 200.0

    async def test_change_is_none_when_the_previous_period_is_empty(self, auth: AuthActions, projects: ProjectActions):
        s = await make_setup(auth, projects)
        await s.write.event(at(19, 12))
        assert (await s.overview()).kpis.events.change_percent is None

    async def test_sessions_and_average_length(self, auth: AuthActions, projects: ProjectActions):
        s = await make_setup(auth, projects)
        await s.write.session(at(15, 8), seconds=60)
        await s.write.session(at(19, 8), seconds=180)
        await s.write.session(at(10, 8), seconds=30)  # previous period

        kpis = (await s.overview()).kpis
        assert (kpis.sessions.value, kpis.avg_session_seconds.value) == (2, 120)
        assert (kpis.sessions.previous, kpis.avg_session_seconds.previous) == (1, 30)

    async def test_other_projects_are_not_counted(self, auth: AuthActions, projects: ProjectActions):
        s = await make_setup(auth, projects)
        other = await make_setup(auth, projects)
        await other.write.event(at(19, 12))
        assert (await s.overview()).kpis.events.value == 0

    async def test_today_is_compared_with_the_same_hours_yesterday(self, auth: AuthActions, projects: ProjectActions):
        # At 10:00, "today" covers 00:00-10:00. A fair comparison is yesterday 00:00-10:00,
        # not yesterday 14:00-24:00 (evening traffic is different).
        s = await make_setup(auth, projects)
        await s.write.event(at(19, 8))
        await s.write.event(at(19, 9))
        await s.write.event(at(19, 21))
        assert (await s.overview("today")).kpis.events.previous == 2


class TestCharts:
    async def test_every_day_is_listed_with_zeros(self, auth: AuthActions, projects: ProjectActions):
        s = await make_setup(auth, projects)
        await s.write.event(at(16, 12), user="a")
        await s.write.event(at(16, 13), user="b")
        await s.write.event(at(20, 9), user="a")

        days = {p.day.day: (p.events, p.users) for p in (await s.overview()).events_per_day}
        assert days == {14: (0, 0), 15: (0, 0), 16: (2, 2), 17: (0, 0), 18: (0, 0), 19: (0, 0), 20: (1, 1)}

    async def test_days_follow_the_project_timezone(self, auth: AuthActions, projects: ProjectActions):
        # 20:00 UTC on the 19th is 01:30 on the 20th in India.
        s = await make_setup(auth, projects, timezone="Asia/Kolkata")
        await s.write.event(at(19, 20))
        per_day = (await s.overview()).events_per_day
        assert {p.day.day: p.events for p in per_day if p.events} == {20: 1}

    async def test_top_screens_count_screen_views_only(self, auth: AuthActions, projects: ProjectActions):
        s = await make_setup(auth, projects)
        for user in ("a", "b", "a"):
            await s.write.event(at(19, 12), name="$screen", user=user, screen="Home")
        await s.write.event(at(19, 12), name="$screen", screen="Checkout")
        await s.write.event(at(19, 12), name="tap", screen="Home")  # not a screen view

        screens = [(t.screen_name, t.views, t.users) for t in (await s.overview()).top_screens]
        assert screens == [("Home", 3, 2), ("Checkout", 1, 1)]

    async def test_top_events_skip_automatic_ones_and_keep_five(self, auth: AuthActions, projects: ProjectActions):
        s = await make_setup(auth, projects)
        for count, name in enumerate(["e1", "e2", "e3", "e4", "e5", "e6"], start=1):
            for _ in range(count):
                await s.write.event(at(19, 12), name=name)
        await s.write.event(at(19, 12), name="$screen")

        top = [(t.event_name, t.count) for t in (await s.overview()).top_events]
        assert top == [("e6", 6), ("e5", 5), ("e4", 4), ("e3", 3), ("e2", 2)]


class TestOverviewApi:
    @pytest.mark.parametrize("range_", ["today", "7d", "30d", "90d"])
    async def test_each_range(self, client: AsyncClient, auth: AuthActions, projects: ProjectActions, range_: str):
        s = await make_setup(auth, projects, timezone="Asia/Kolkata")
        url = f"{API}/orgs/{s.admin.org_id}/projects/{s.project_id}/insights/overview?range={range_}"
        response = await client.get(url, headers=s.admin.headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert (data["range"], data["timezone"]) == (range_, "Asia/Kolkata")
        assert len(data["events_per_day"]) == {"today": 1, "7d": 7, "30d": 30, "90d": 90}[range_]

    async def test_unknown_range(self, client: AsyncClient, auth: AuthActions, projects: ProjectActions):
        s = await make_setup(auth, projects)
        url = f"{API}/orgs/{s.admin.org_id}/projects/{s.project_id}/insights/overview?range=1y"
        assert (await client.get(url, headers=s.admin.headers)).status_code == 422

    async def test_viewer_can_read(self, client: AsyncClient, auth: AuthActions, projects: ProjectActions, orgs: OrgActions):
        s = await make_setup(auth, projects)
        viewer = await orgs.add_new_member(s.admin, "viewer")
        url = f"{API}/orgs/{s.admin.org_id}/projects/{s.project_id}/insights/overview"
        assert (await client.get(url, headers=viewer.headers)).status_code == 200

    async def test_project_of_another_org(self, client: AsyncClient, auth: AuthActions, projects: ProjectActions):
        s = await make_setup(auth, projects)
        other = await auth.register()
        url = f"{API}/orgs/{other.org_id}/projects/{s.project_id}/insights/overview"
        assert (await client.get(url, headers=other.headers)).status_code == 404
