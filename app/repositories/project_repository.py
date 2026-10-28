from uuid import UUID

import asyncpg

from app.db.database import Executor, db

# Every query filters by organization_id as well as id, so a project can only be reached
# through the organization that owns it.
_COLUMNS = """
    p.id, p.organization_id, p.name, p.platform, p.timezone, p.allowed_origins, p.created_at,
    (SELECT count(*) FROM api_keys k WHERE k.project_id = p.id AND k.revoked_at IS NULL)
        AS active_api_keys
"""


class ProjectRepository:
    def __init__(self, conn: Executor = db) -> None:
        self.conn = conn

    async def list_for_organization(self, organization_id: UUID) -> list[asyncpg.Record]:
        return await self.conn.fetch(
            f"SELECT {_COLUMNS} FROM projects p WHERE p.organization_id = $1 ORDER BY p.created_at",
            organization_id,
        )

    async def get(self, organization_id: UUID, project_id: UUID) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            f"SELECT {_COLUMNS} FROM projects p WHERE p.organization_id = $1 AND p.id = $2",
            organization_id,
            project_id,
        )

    async def exists(self, organization_id: UUID, project_id: UUID) -> bool:
        return await self.conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM projects WHERE organization_id = $1 AND id = $2)",
            organization_id,
            project_id,
        )

    async def create(
        self,
        organization_id: UUID,
        name: str,
        platform: str,
        timezone: str,
        allowed_origins: list[str],
    ) -> UUID:
        return await self.conn.fetchval(
            """
            INSERT INTO projects (organization_id, name, platform, timezone, allowed_origins)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            organization_id,
            name,
            platform,
            timezone,
            allowed_origins,
        )

    async def update(
        self,
        organization_id: UUID,
        project_id: UUID,
        name: str | None,
        platform: str | None,
        timezone: str | None,
        allowed_origins: list[str] | None,
    ) -> bool:
        """Changes only the fields that are not None. Returns False if the project wasn't found."""
        status = await self.conn.execute(
            """
            UPDATE projects
            SET name            = COALESCE($3, name),
                platform        = COALESCE($4, platform),
                timezone        = COALESCE($5, timezone),
                allowed_origins = COALESCE($6, allowed_origins)
            WHERE organization_id = $1 AND id = $2
            """,
            organization_id,
            project_id,
            name,
            platform,
            timezone,
            allowed_origins,
        )
        return status == "UPDATE 1"

    async def delete_with_data(self, organization_id: UUID, project_id: UUID) -> bool:
        """Deletes the project and everything it owns. Tables with foreign keys (api_keys,
        persons, sessions, dashboards, alert_rules, ...) go by ON DELETE CASCADE; events and
        the rollup tables have no foreign keys, so they are deleted explicitly first.
        Call inside a transaction."""
        if not await self.exists(organization_id, project_id):
            return False
        await self.conn.execute("DELETE FROM events WHERE project_id = $1", project_id)
        await self.conn.execute("DELETE FROM event_daily_stats WHERE project_id = $1", project_id)
        await self.conn.execute("DELETE FROM project_daily_stats WHERE project_id = $1", project_id)
        await self.conn.execute("DELETE FROM projects WHERE id = $1", project_id)
        return True
