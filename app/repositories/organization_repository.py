from uuid import UUID

import asyncpg

from app.db.database import Executor, db
from app.repositories.search import contains_pattern


class OrganizationRepository:
    def __init__(self, conn: Executor = db) -> None:
        self.conn = conn

    async def slug_exists(self, slug: str) -> bool:
        return await self.conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM organizations WHERE slug = $1)",
            slug,
        )

    async def create(self, name: str, slug: str, plan: str = "free") -> asyncpg.Record:
        row = await self.conn.fetchrow(
            """
            INSERT INTO organizations (name, slug, plan)
            VALUES ($1, $2, $3)
            RETURNING id, name, slug, plan, is_active, created_at
            """,
            name,
            slug,
            plan,
        )
        assert row is not None
        return row

    async def add_member(self, organization_id: UUID, user_id: UUID, role: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO organization_members (organization_id, user_id, role)
            VALUES ($1, $2, $3::member_role)
            """,
            organization_id,
            user_id,
            role,
        )

    async def list_memberships(self, user_id: UUID) -> list[asyncpg.Record]:
        """Every organization the user belongs to, with their role in it."""
        return await self.conn.fetch(
            """
            SELECT o.id, o.name, o.slug, o.plan, o.is_active, m.role::text AS role
            FROM organization_members m
            JOIN organizations o ON o.id = m.organization_id
            WHERE m.user_id = $1
            ORDER BY m.created_at
            """,
            user_id,
        )

    async def get_by_id(self, organization_id: UUID) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            "SELECT id, name, slug, plan, is_active, created_at FROM organizations WHERE id = $1",
            organization_id,
        )

    async def get_access(self, organization_id: UUID, user_id: UUID) -> asyncpg.Record | None:
        """None if the organization doesn't exist; otherwise its is_active flag and the user's
        role in it (role is None when the user is not a member)."""
        return await self.conn.fetchrow(
            """
            SELECT o.is_active, m.role::text AS role
            FROM organizations o
            LEFT JOIN organization_members m ON m.organization_id = o.id AND m.user_id = $2
            WHERE o.id = $1
            """,
            organization_id,
            user_id,
        )

    async def update(
        self, organization_id: UUID, name: str | None, plan: str | None, is_active: bool | None
    ) -> asyncpg.Record | None:
        """Changes only the fields that are not None."""
        return await self.conn.fetchrow(
            """
            UPDATE organizations
            SET name      = COALESCE($2, name),
                plan      = COALESCE($3, plan),
                is_active = COALESCE($4, is_active)
            WHERE id = $1
            RETURNING id
            """,
            organization_id,
            name,
            plan,
            is_active,
        )

    # ── Super admin listing ──────────────────────────────────────────────────

    _ADMIN_COLUMNS = """
        o.id, o.name, o.slug, o.plan, o.is_active, o.created_at,
        (SELECT count(*) FROM organization_members m WHERE m.organization_id = o.id) AS member_count,
        (SELECT count(*) FROM projects p WHERE p.organization_id = o.id) AS project_count
    """

    async def get_with_counts(self, organization_id: UUID) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            f"SELECT {self._ADMIN_COLUMNS} FROM organizations o WHERE o.id = $1",
            organization_id,
        )

    async def search(self, search: str | None, limit: int, offset: int) -> list[asyncpg.Record]:
        """All organizations (newest first), optionally filtered by name or slug."""
        return await self.conn.fetch(
            f"""
            SELECT {self._ADMIN_COLUMNS}
            FROM organizations o
            WHERE $1::text IS NULL OR o.name ILIKE $1 OR o.slug ILIKE $1
            ORDER BY o.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            contains_pattern(search),
            limit,
            offset,
        )

    async def count(self, search: str | None) -> int:
        return await self.conn.fetchval(
            """
            SELECT count(*) FROM organizations o
            WHERE $1::text IS NULL OR o.name ILIKE $1 OR o.slug ILIKE $1
            """,
            contains_pattern(search),
        )

    # ── Members ──────────────────────────────────────────────────────────────

    async def get_member(
        self, organization_id: UUID, user_id: UUID, for_update: bool = False
    ) -> asyncpg.Record | None:
        """One member with their user details. for_update locks the row (use inside a transaction)."""
        return await self.conn.fetchrow(
            f"""
            SELECT u.id AS user_id, u.email, u.full_name, m.role::text AS role, m.created_at AS joined_at
            FROM organization_members m
            JOIN users u ON u.id = m.user_id
            WHERE m.organization_id = $1 AND m.user_id = $2
            {"FOR UPDATE OF m" if for_update else ""}
            """,
            organization_id,
            user_id,
        )

    async def list_members(self, organization_id: UUID) -> list[asyncpg.Record]:
        return await self.conn.fetch(
            """
            SELECT u.id AS user_id, u.email, u.full_name, m.role::text AS role, m.created_at AS joined_at
            FROM organization_members m
            JOIN users u ON u.id = m.user_id
            WHERE m.organization_id = $1
            ORDER BY m.created_at
            """,
            organization_id,
        )

    async def lock_admin_ids(self, organization_id: UUID) -> list[UUID]:
        """Admins of the organization, locked until the transaction ends, so two requests
        can't remove the last two admins at the same time."""
        rows = await self.conn.fetch(
            """
            SELECT user_id FROM organization_members
            WHERE organization_id = $1 AND role = 'admin'
            FOR UPDATE
            """,
            organization_id,
        )
        return [row["user_id"] for row in rows]

    async def update_member_role(self, organization_id: UUID, user_id: UUID, role: str) -> None:
        await self.conn.execute(
            """
            UPDATE organization_members SET role = $3::member_role
            WHERE organization_id = $1 AND user_id = $2
            """,
            organization_id,
            user_id,
            role,
        )

    async def remove_member(self, organization_id: UUID, user_id: UUID) -> None:
        await self.conn.execute(
            "DELETE FROM organization_members WHERE organization_id = $1 AND user_id = $2",
            organization_id,
            user_id,
        )
