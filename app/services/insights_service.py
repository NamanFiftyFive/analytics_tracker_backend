from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.exceptions import NotFoundError
from app.repositories.insights_repository import InsightsRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.insights import (
    DayPoint,
    Kpi,
    OverviewKpis,
    OverviewOut,
    OverviewRange,
    TopEvent,
    TopScreen,
)

_RANGE_DAYS: dict[str, int] = {"today": 1, "7d": 7, "30d": 30, "90d": 90}


@dataclass(frozen=True)
class TimeWindow:
    """[start, end) in UTC, plus the previous window [previous_start, previous_end) to compare with.
    Days begin at midnight in the project's timezone, so "today" means the project's today.

    The previous window is the same hours `days` earlier: at 10:00, "today" (00:00-10:00) is
    compared with yesterday 00:00-10:00, and "7d" with the 7 days before up to the same time."""

    start: datetime
    end: datetime
    previous_start: datetime
    previous_end: datetime
    first_day: date
    days: int

    @classmethod
    def for_range(cls, range_: str, timezone: str, now: datetime | None = None) -> "TimeWindow":
        tz = ZoneInfo(timezone)
        now = (now or datetime.now(UTC)).astimezone(tz)
        days = _RANGE_DAYS[range_]
        first_day = now.date() - timedelta(days=days - 1)
        local_start = datetime.combine(first_day, time.min, tzinfo=tz)
        # Shifted in local time, so a daylight-saving change keeps the same clock hours.
        shift = timedelta(days=days)
        return cls(
            start=local_start.astimezone(UTC),
            end=now.astimezone(UTC),
            previous_start=(local_start - shift).astimezone(UTC),
            previous_end=(now - shift).astimezone(UTC),
            first_day=first_day,
            days=days,
        )


def _kpi(value: float, previous: float) -> Kpi:
    change = None if previous == 0 else round((value - previous) / previous * 100, 1)
    return Kpi(value=round(value, 1), previous=round(previous, 1), change_percent=change)


class InsightsService:
    async def overview(
        self, organization_id: UUID, project_id: UUID, range_: OverviewRange, now: datetime | None = None
    ) -> OverviewOut:
        project = await ProjectRepository().get(organization_id, project_id)
        if project is None:
            raise NotFoundError("Project not found")

        timezone = project["timezone"]
        window = TimeWindow.for_range(range_, timezone, now)
        repo = InsightsRepository()

        bounds = (window.start, window.end, window.previous_start, window.previous_end)
        events = await repo.event_totals(project_id, *bounds)
        sessions = await repo.session_totals(project_id, *bounds)
        daily = {row["day"]: row for row in await repo.events_per_day(project_id, window.start, window.end, timezone)}
        screens = await repo.top_screens(project_id, window.start, window.end)
        top_events = await repo.top_events(project_id, window.start, window.end)

        # Every day in the range, with 0 for days without events, so charts have no gaps.
        per_day = []
        for offset in range(window.days):
            day = window.first_day + timedelta(days=offset)
            row = daily.get(day)
            per_day.append(DayPoint(day=day, events=row["events"] if row else 0, users=row["users"] if row else 0))

        return OverviewOut(
            range=range_,
            timezone=timezone,
            start=window.start,
            end=window.end,
            kpis=OverviewKpis(
                active_users=_kpi(events["active_users"], events["previous_active_users"]),
                events=_kpi(events["events"], events["previous_events"]),
                sessions=_kpi(sessions["sessions"], sessions["previous_sessions"]),
                avg_session_seconds=_kpi(
                    float(sessions["avg_session_seconds"]), float(sessions["previous_avg_session_seconds"])
                ),
            ),
            events_per_day=per_day,
            top_screens=[TopScreen(**dict(r)) for r in screens],
            top_events=[TopEvent(**dict(r)) for r in top_events],
        )
