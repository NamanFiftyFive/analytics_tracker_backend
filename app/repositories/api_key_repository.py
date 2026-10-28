from uuid import UUID

import asyncpg

from app.db.database import Executor, db

_COLUMNS = """
    id, name, key_prefix, (revoked_at IS NULL) AS is_active, last_used_at, revoked_at, created_at
"""


class ApiKeyRepository:
    def __init__(self, conn: Executor = db) -> None:
        self.conn = conn

    async def list_for_project(self, project_id: UUID) -> list[asyncpg.Record]:
        """Active keys first, then revoked ones; newest first within each group."""
        return await self.conn.fetch(
            f"""
            SELECT {_COLUMNS} FROM api_keys
            WHERE project_id = $1
            ORDER BY revoked_at IS NOT NULL, created_at DESC
            """,
            project_id,
        )

    async def create(self, project_id: UUID, name: str, key_prefix: str, key_hash: str) -> asyncpg.Record:
        row = await self.conn.fetchrow(
            f"""
            INSERT INTO api_keys (project_id, name, key_prefix, key_hash)
            VALUES ($1, $2, $3, $4)
            RETURNING {_COLUMNS}
            """,
            project_id,
            name,
            key_prefix,
            key_hash,
        )
        assert row is not None
        return row

    async def revoke(self, project_id: UUID, key_id: UUID) -> asyncpg.Record | None:
        """Marks the key revoked (kept for history). None if no such key in this project.
        Revoking an already revoked key keeps the original revoked_at."""
        return await self.conn.fetchrow(
            f"""
            UPDATE api_keys
            SET revoked_at = COALESCE(revoked_at, now())
            WHERE project_id = $1 AND id = $2
            RETURNING {_COLUMNS}
            """,
            project_id,
            key_id,
        )

    # ── Used by ingestion ────────────────────────────────────────────────────

    async def get_ingest_target(self, key_hash: str) -> asyncpg.Record | None:
        """The project an active key sends to, with what ingestion needs to check.
        None if the key doesn't exist or is revoked."""
        return await self.conn.fetchrow(
            """
            SELECT k.id AS key_id, p.id AS project_id, p.allowed_origins,
                   o.is_active AS organization_active
            FROM api_keys k
            JOIN projects p ON p.id = k.project_id
            JOIN organizations o ON o.id = p.organization_id
            WHERE k.key_hash = $1 AND k.revoked_at IS NULL
            """,
            key_hash,
        )

    async def touch_last_used(self, key_id: UUID) -> None:
        """Updates last_used_at at most once a minute, so busy keys don't cause a write on
        every batch (and lock contention on this one row)."""
        await self.conn.execute(
            """
            UPDATE api_keys SET last_used_at = now()
            WHERE id = $1 AND (last_used_at IS NULL OR last_used_at < now() - interval '1 minute')
            """,
            key_id,
        )
