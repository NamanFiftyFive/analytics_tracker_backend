import asyncpg

from app.db.database import Executor, db


class StatsRepository:
    """Platform-wide numbers for the super admin."""

    def __init__(self, conn: Executor = db) -> None:
        self.conn = conn

    async def platform_totals(self) -> asyncpg.Record:
        row = await self.conn.fetchrow(
            """
            SELECT
                (SELECT count(*) FROM organizations)                         AS organizations,
                (SELECT count(*) FROM organizations WHERE is_active)         AS active_organizations,
                (SELECT count(*) FROM users)                                 AS users,
                (SELECT count(*) FROM users WHERE is_active)                 AS active_users,
                (SELECT count(*) FROM projects)                              AS projects,
                (SELECT count(*) FROM events
                  WHERE occurred_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')
                                                                             AS events_today
            """
        )
        assert row is not None
        return row
