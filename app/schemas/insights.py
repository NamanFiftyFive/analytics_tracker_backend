"""Overview numbers for one project over a date range."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

OverviewRange = Literal["today", "7d", "30d", "90d"]


class Kpi(BaseModel):
    value: float
    previous: float = Field(description="Same metric for the same hours one period earlier (today: yesterday up to this time)")
    change_percent: float | None = Field(description="None when the previous value is 0")


class OverviewKpis(BaseModel):
    active_users: Kpi
    events: Kpi
    sessions: Kpi
    avg_session_seconds: Kpi


class DayPoint(BaseModel):
    day: date
    events: int
    users: int


class TopScreen(BaseModel):
    screen_name: str
    views: int
    users: int


class TopEvent(BaseModel):
    event_name: str
    count: int
    users: int


class OverviewOut(BaseModel):
    range: OverviewRange
    timezone: str = Field(description="Project timezone; days are counted in it")
    start: datetime
    end: datetime
    kpis: OverviewKpis
    events_per_day: list[DayPoint] = Field(description="Every day in the range, including days with 0")
    top_screens: list[TopScreen]
    top_events: list[TopEvent] = Field(description="Custom events only (names not starting with $)")
