"""Aggregate queries over raw events and sessions for one project and time window.

For now these read `events` directly (fine for POC volumes); the rollup tables can replace
them later without changing the API.
"""

from datetime import datetime
from uuid import UUID

import asyncpg

from app.db.database import Executor, db


class InsightsRepository:
    def __init__(self, conn: Executor = db) -> None:
        self.conn = conn

    async def event_totals(
        self,
        project_id: UUID,
        start: datetime,
        end: datetime,
        previous_start: datetime,
        previous_end: datetime,
    ) -> asyncpg.Record:
        """Events and unique users in [start, end) and in [previous_start, previous_end)."""
        row = await self.conn.fetchrow(
            """
            SELECT
                count(*) FILTER (WHERE occurred_at >= $2)                          AS events,
                count(DISTINCT distinct_id) FILTER (WHERE occurred_at >= $2)       AS active_users,
                count(*) FILTER (WHERE occurred_at < $5)                           AS previous_events,
                count(DISTINCT distinct_id) FILTER (WHERE occurred_at < $5)        AS previous_active_users
            FROM events
            WHERE project_id = $1
              AND ((occurred_at >= $2 AND occurred_at < $3) OR (occurred_at >= $4 AND occurred_at < $5))
            """,
            project_id,
            start,
            end,
            previous_start,
            previous_end,
        )
        assert row is not None
        return row

    async def session_totals(
        self,
        project_id: UUID,
        start: datetime,
        end: datetime,
        previous_start: datetime,
        previous_end: datetime,
    ) -> asyncpg.Record:
        """Sessions started and their average length, for both windows."""
        row = await self.conn.fetchrow(
            """
            SELECT
                count(*) FILTER (WHERE started_at >= $2) AS sessions,
                coalesce(avg(extract(epoch FROM ended_at - started_at)) FILTER (WHERE started_at >= $2), 0)
                    AS avg_session_seconds,
                count(*) FILTER (WHERE started_at < $5) AS previous_sessions,
                coalesce(avg(extract(epoch FROM ended_at - started_at)) FILTER (WHERE started_at < $5), 0)
                    AS previous_avg_session_seconds
            FROM sessions
            WHERE project_id = $1
              AND ((started_at >= $2 AND started_at < $3) OR (started_at >= $4 AND started_at < $5))
            """,
            project_id,
            start,
            end,
            previous_start,
            previous_end,
        )
        assert row is not None
        return row

    async def events_per_day(
        self, project_id: UUID, start: datetime, end: datetime, timezone: str
    ) -> list[asyncpg.Record]:
        """Days that had events, counted in the project's timezone."""
        return await self.conn.fetch(
            """
            SELECT (occurred_at AT TIME ZONE $4)::date AS day,
                   count(*) AS events,
                   count(DISTINCT distinct_id) AS users
            FROM events
            WHERE project_id = $1 AND occurred_at >= $2 AND occurred_at < $3
            GROUP BY 1
            ORDER BY 1
            """,
            project_id,
            start,
            end,
            timezone,
        )

    async def top_screens(self, project_id: UUID, start: datetime, end: datetime, limit: int = 5) -> list[asyncpg.Record]:
        return await self.conn.fetch(
            """
            SELECT screen_name, count(*) AS views, count(DISTINCT distinct_id) AS users
            FROM events
            WHERE project_id = $1 AND occurred_at >= $2 AND occurred_at < $3
              AND event_name = '$screen' AND screen_name IS NOT NULL
            GROUP BY screen_name
            ORDER BY views DESC, screen_name
            LIMIT $4
            """,
            project_id,
            start,
            end,
            limit,
        )

    async def top_events(self, project_id: UUID, start: datetime, end: datetime, limit: int = 5) -> list[asyncpg.Record]:
        """Custom events only: names starting with $ are the SDK's automatic ones."""
        return await self.conn.fetch(
            """
            SELECT event_name, count(*) AS count, count(DISTINCT distinct_id) AS users
            FROM events
            WHERE project_id = $1 AND occurred_at >= $2 AND occurred_at < $3
              AND left(event_name, 1) <> '$'
            GROUP BY event_name
            ORDER BY count DESC, event_name
            LIMIT $4
            """,
            project_id,
            start,
            end,
            limit,
        )
