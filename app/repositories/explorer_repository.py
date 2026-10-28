"""Read queries for browsing a project's raw data: events, event names, persons."""

from datetime import datetime
from uuid import UUID

import asyncpg

from app.db.database import Executor, db
from app.repositories.search import contains_pattern

EVENT_COLUMNS = """
    id, event_name, distinct_id, person_id, session_id, occurred_at, screen_name, path,
    platform, os, browser, device_type, app_version, country, properties
"""

# A person counts as identified when identify() stored traits on them; anonymous have none.
_IDENTIFIED = "p.properties <> '{}'::jsonb"


class ExplorerRepository:
    def __init__(self, conn: Executor = db) -> None:
        self.conn = conn

    # ── Events ───────────────────────────────────────────────────────────────

    async def list_events(
        self,
        project_id: UUID,
        *,
        event_name: str | None,
        person_id: UUID | None,
        search: str | None,
        before: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[asyncpg.Record]:
        """Newest first. `before` = (occurred_at, id) of the last event already shown (keyset
        pagination: stays fast and stable while new events keep arriving)."""
        return await self.conn.fetch(
            f"""
            SELECT {EVENT_COLUMNS}
            FROM events
            WHERE project_id = $1
              AND ($2::text IS NULL OR event_name = $2)
              AND ($3::uuid IS NULL OR person_id = $3)
              AND ($4::text IS NULL
                   OR distinct_id ILIKE $4
                   OR screen_name ILIKE $4
                   OR properties::text ILIKE $4)
              AND ($5::timestamptz IS NULL OR (occurred_at, id) < ($5, $6::uuid))
            ORDER BY occurred_at DESC, id DESC
            LIMIT $7
            """,
            project_id,
            event_name,
            person_id,
            contains_pattern(search),
            before[0] if before else None,
            before[1] if before else None,
            limit,
        )

    async def list_definitions(self, project_id: UUID) -> list[asyncpg.Record]:
        return await self.conn.fetch(
            """
            SELECT event_name, first_seen_at, last_seen_at
            FROM event_definitions
            WHERE project_id = $1
            ORDER BY last_seen_at DESC, event_name
            """,
            project_id,
        )

    # ── Persons ──────────────────────────────────────────────────────────────

    _PERSON_COLUMNS = f"""
        p.id, p.distinct_id, p.properties, p.first_seen_at, p.last_seen_at,
        ({_IDENTIFIED}) AS is_identified,
        (SELECT count(*) FROM events e WHERE e.project_id = p.project_id AND e.distinct_id = p.distinct_id)
            AS event_count,
        (SELECT s.os FROM sessions s WHERE s.person_id = p.id ORDER BY s.started_at DESC LIMIT 1) AS last_os
    """

    async def list_persons(
        self,
        project_id: UUID,
        *,
        person_filter: str,
        search: str | None,
        new_since: datetime,
        limit: int,
        offset: int,
    ) -> list[asyncpg.Record]:
        """Most recently active first. Each row carries `total` = rows matching the filter."""
        return await self.conn.fetch(
            f"""
            SELECT {self._PERSON_COLUMNS}, count(*) OVER () AS total
            FROM persons p
            WHERE p.project_id = $1
              AND ($2::text IS NULL OR p.distinct_id ILIKE $2 OR p.properties::text ILIKE $2)
              AND ($3 = 'all'
                   OR ($3 = 'identified' AND {_IDENTIFIED})
                   OR ($3 = 'new' AND p.first_seen_at >= $4))
            ORDER BY p.last_seen_at DESC, p.id
            LIMIT $5 OFFSET $6
            """,
            project_id,
            contains_pattern(search),
            person_filter,
            new_since,
            limit,
            offset,
        )

    async def person_counts(self, project_id: UUID, new_since: datetime) -> asyncpg.Record:
        row = await self.conn.fetchrow(
            f"""
            SELECT count(*) AS all,
                   count(*) FILTER (WHERE {_IDENTIFIED}) AS identified,
                   count(*) FILTER (WHERE p.first_seen_at >= $2) AS new
            FROM persons p
            WHERE p.project_id = $1
            """,
            project_id,
            new_since,
        )
        assert row is not None
        return row

    async def get_person(self, project_id: UUID, person_id: UUID) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            f"SELECT {self._PERSON_COLUMNS} FROM persons p WHERE p.project_id = $1 AND p.id = $2",
            project_id,
            person_id,
        )

    async def person_session_count(self, person_id: UUID) -> int:
        return await self.conn.fetchval("SELECT count(*) FROM sessions WHERE person_id = $1", person_id)

    async def recent_sessions(self, person_id: UUID, limit: int = 5) -> list[asyncpg.Record]:
        return await self.conn.fetch(
            """
            SELECT id, started_at, ended_at, event_count, entry_path, exit_path, os, app_version,
                   coalesce(extract(epoch FROM ended_at - started_at), 0)::int AS duration_seconds
            FROM sessions
            WHERE person_id = $1
            ORDER BY started_at DESC
            LIMIT $2
            """,
            person_id,
            limit,
        )

    async def events_for_sessions(
        self, project_id: UUID, session_ids: list[UUID], per_session: int = 100
    ) -> list[asyncpg.Record]:
        """Up to `per_session` newest events of each session."""
        return await self.conn.fetch(
            f"""
            SELECT {EVENT_COLUMNS}
            FROM (
                SELECT {EVENT_COLUMNS},
                       row_number() OVER (PARTITION BY session_id ORDER BY occurred_at DESC, id DESC) AS rn
                FROM events
                WHERE project_id = $1 AND session_id = ANY($2::uuid[])
            ) ranked
            WHERE rn <= $3
            ORDER BY occurred_at DESC, id DESC
            """,
            project_id,
            session_ids,
            per_session,
        )
