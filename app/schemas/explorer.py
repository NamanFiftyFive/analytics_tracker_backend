"""Browsing raw data: the event feed, event names, users (persons) and one user's timeline."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

PersonFilter = Literal["all", "identified", "new"]


class EventOut(BaseModel):
    id: UUID
    event_name: str
    distinct_id: str
    person_id: UUID | None
    session_id: UUID | None
    occurred_at: datetime
    screen_name: str | None
    path: str | None
    platform: str | None
    os: str | None
    browser: str | None
    device_type: str | None
    app_version: str | None
    country: str | None
    properties: dict[str, Any]


class EventPage(BaseModel):
    items: list[EventOut]
    next_cursor: str | None = Field(description="Pass as `cursor` to get older events; null at the end")


class EventDefinitionOut(BaseModel):
    event_name: str
    first_seen_at: datetime
    last_seen_at: datetime


class PersonOut(BaseModel):
    id: UUID
    distinct_id: str
    properties: dict[str, Any]
    is_identified: bool = Field(description="Has traits from identify(); anonymous visitors have none")
    first_seen_at: datetime
    last_seen_at: datetime
    event_count: int
    last_os: str | None


class PersonCounts(BaseModel):
    all: int
    identified: int
    new: int = Field(description="First seen in the last 7 days")


class PersonPage(BaseModel):
    items: list[PersonOut]
    total: int = Field(description="Matching the current filter and search")
    limit: int
    offset: int
    counts: PersonCounts


class SessionWithEvents(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int
    event_count: int
    entry_path: str | None
    exit_path: str | None
    os: str | None
    app_version: str | None
    events: list[EventOut] = Field(description="Newest first, at most 100")


class PersonStats(BaseModel):
    sessions: int
    events: int


class PersonDetail(BaseModel):
    person: PersonOut
    stats: PersonStats
    sessions: list[SessionWithEvents] = Field(description="The 5 most recent sessions")
