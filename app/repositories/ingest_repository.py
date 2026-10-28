"""Bulk writes for event ingestion.

Each method writes a whole batch in ONE statement: Python lists are sent as Postgres arrays and
turned back into rows with unnest(...). Rows are sorted before upserting so concurrent batches
lock rows in the same order and can't deadlock each other. Call inside a transaction.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.db.database import Executor
from app.schemas.ingest import IngestContext


@dataclass
class PersonRow:
    distinct_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class EventRow:
    id: UUID
    event_name: str
    distinct_id: str
    session_id: UUID | None
    occurred_at: datetime
    path: str | None
    screen_name: str | None
    properties: dict[str, Any]
    person_id: UUID | None = None


@dataclass
class SessionRow:
    id: UUID
    person_id: UUID | None
    started_at: datetime
    ended_at: datetime
    event_count: int
    entry_path: str | None
    exit_path: str | None
    referrer: str | None
    utm_source: str | None
    utm_medium: str | None
    utm_campaign: str | None


@dataclass
class DefinitionRow:
    event_name: str
    first_seen_at: datetime
    last_seen_at: datetime


class IngestRepository:
    def __init__(self, conn: Executor) -> None:
        self.conn = conn

    async def upsert_persons(self, project_id: UUID, persons: list[PersonRow]) -> dict[str, UUID]:
        """Creates new persons or widens first/last seen of existing ones; $identify traits are
        merged into properties. Returns {distinct_id: person_id}."""
        persons = sorted(persons, key=lambda p: p.distinct_id)
        rows = await self.conn.fetch(
            """
            INSERT INTO persons (project_id, distinct_id, properties, first_seen_at, last_seen_at)
            SELECT $1, t.distinct_id, t.properties::jsonb, t.first_seen_at, t.last_seen_at
            FROM unnest($2::text[], $3::text[], $4::timestamptz[], $5::timestamptz[])
                 AS t(distinct_id, properties, first_seen_at, last_seen_at)
            ON CONFLICT (project_id, distinct_id) DO UPDATE
            SET first_seen_at = LEAST(persons.first_seen_at, excluded.first_seen_at),
                last_seen_at  = GREATEST(persons.last_seen_at, excluded.last_seen_at),
                properties    = persons.properties || excluded.properties
            RETURNING id, distinct_id
            """,
            project_id,
            [p.distinct_id for p in persons],
            [json.dumps(p.properties, default=str) for p in persons],
            [p.first_seen_at for p in persons],
            [p.last_seen_at for p in persons],
        )
        return {row["distinct_id"]: row["id"] for row in rows}

    async def insert_events(
        self, project_id: UUID, context: IngestContext, events: list[EventRow]
    ) -> set[UUID]:
        """Inserts events; ones already stored in the project (same id, at any time) are skipped.
        Returns the ids actually inserted.

        NOT EXISTS catches retries whose occurred_at changed (e.g. a fast device clock replaced
        with the arrival time); ON CONFLICT covers the primary key for everything else."""
        rows = await self.conn.fetch(
            """
            INSERT INTO events (id, project_id, event_name, distinct_id, person_id, session_id,
                                occurred_at, path, screen_name, properties,
                                platform, os, browser, device_type, app_version, country)
            SELECT e.id, $1, e.event_name, e.distinct_id, e.person_id, e.session_id,
                   e.occurred_at, e.path, e.screen_name, e.properties::jsonb,
                   $2, $3, $4, $5, $6, $7
            FROM unnest($8::uuid[], $9::text[], $10::text[], $11::uuid[], $12::uuid[],
                        $13::timestamptz[], $14::text[], $15::text[], $16::text[])
                 AS e(id, event_name, distinct_id, person_id, session_id,
                      occurred_at, path, screen_name, properties)
            WHERE NOT EXISTS (SELECT 1 FROM events x WHERE x.project_id = $1 AND x.id = e.id)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            project_id,
            context.platform,
            context.os,
            context.browser,
            context.device_type,
            context.app_version,
            context.country,
            [e.id for e in events],
            [e.event_name for e in events],
            [e.distinct_id for e in events],
            [e.person_id for e in events],
            [e.session_id for e in events],
            [e.occurred_at for e in events],
            [e.path for e in events],
            [e.screen_name for e in events],
            [json.dumps(e.properties, default=str) for e in events],
        )
        return {row["id"] for row in rows}

    async def upsert_sessions(
        self, project_id: UUID, context: IngestContext, sessions: list[SessionRow]
    ) -> None:
        """Creates sessions or extends existing ones (earlier start, later end, more events).
        Entry/exit path follow whichever events are earliest/latest overall."""
        sessions = sorted(sessions, key=lambda s: str(s.id))
        await self.conn.execute(
            """
            INSERT INTO sessions (id, project_id, person_id, started_at, ended_at, event_count,
                                  entry_path, exit_path, referrer, utm_source, utm_medium, utm_campaign,
                                  device_type, os, browser, app_version, country)
            SELECT s.id, $1, s.person_id, s.started_at, s.ended_at, s.event_count,
                   s.entry_path, s.exit_path, s.referrer, s.utm_source, s.utm_medium, s.utm_campaign,
                   $2, $3, $4, $5, $6
            FROM unnest($7::uuid[], $8::uuid[], $9::timestamptz[], $10::timestamptz[], $11::int[],
                        $12::text[], $13::text[], $14::text[], $15::text[], $16::text[], $17::text[])
                 AS s(id, person_id, started_at, ended_at, event_count,
                      entry_path, exit_path, referrer, utm_source, utm_medium, utm_campaign)
            ON CONFLICT (id) DO UPDATE
            SET entry_path  = CASE WHEN excluded.started_at < sessions.started_at
                                   THEN excluded.entry_path ELSE sessions.entry_path END,
                exit_path   = CASE WHEN excluded.ended_at >= sessions.ended_at
                                   THEN excluded.exit_path ELSE sessions.exit_path END,
                started_at  = LEAST(sessions.started_at, excluded.started_at),
                ended_at    = GREATEST(sessions.ended_at, excluded.ended_at),
                event_count = sessions.event_count + excluded.event_count,
                person_id   = COALESCE(excluded.person_id, sessions.person_id)
            WHERE sessions.project_id = excluded.project_id
            """,
            project_id,
            context.device_type,
            context.os,
            context.browser,
            context.app_version,
            context.country,
            [s.id for s in sessions],
            [s.person_id for s in sessions],
            [s.started_at for s in sessions],
            [s.ended_at for s in sessions],
            [s.event_count for s in sessions],
            [s.entry_path for s in sessions],
            [s.exit_path for s in sessions],
            [s.referrer for s in sessions],
            [s.utm_source for s in sessions],
            [s.utm_medium for s in sessions],
            [s.utm_campaign for s in sessions],
        )

    async def upsert_definitions(self, project_id: UUID, definitions: list[DefinitionRow]) -> None:
        """Keeps the catalog of event names seen in the project (for dashboard dropdowns)."""
        definitions = sorted(definitions, key=lambda d: d.event_name)
        await self.conn.execute(
            """
            INSERT INTO event_definitions (project_id, event_name, first_seen_at, last_seen_at)
            SELECT $1, t.event_name, t.first_seen_at, t.last_seen_at
            FROM unnest($2::text[], $3::timestamptz[], $4::timestamptz[])
                 AS t(event_name, first_seen_at, last_seen_at)
            ON CONFLICT (project_id, event_name) DO UPDATE
            SET first_seen_at = LEAST(event_definitions.first_seen_at, excluded.first_seen_at),
                last_seen_at  = GREATEST(event_definitions.last_seen_at, excluded.last_seen_at)
            """,
            project_id,
            [d.event_name for d in definitions],
            [d.first_seen_at for d in definitions],
            [d.last_seen_at for d in definitions],
        )
