from datetime import datetime
from uuid import UUID

import asyncpg

from app.db.database import Executor, db


class RefreshTokenRepository:
    def __init__(self, conn: Executor = db) -> None:
        self.conn = conn

    async def create(self, user_id: UUID, token_hash: str, expires_at: datetime) -> None:
        await self.conn.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES ($1, $2, $3)",
            user_id,
            token_hash,
            expires_at,
        )

    async def get_active_for_update(self, token_hash: str) -> asyncpg.Record | None:
        """Locks the row so two refreshes with the same token can't both succeed.
        Must run inside a transaction."""
        return await self.conn.fetchrow(
            """
            SELECT id, user_id
            FROM refresh_tokens
            WHERE token_hash = $1 AND revoked_at IS NULL AND expires_at > now()
            FOR UPDATE
            """,
            token_hash,
        )

    async def revoke(self, token_id: UUID) -> None:
        await self.conn.execute(
            "UPDATE refresh_tokens SET revoked_at = now() WHERE id = $1",
            token_id,
        )

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        """Logs the user out everywhere (used when an account is deactivated)."""
        await self.conn.execute(
            "UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = $1 AND revoked_at IS NULL",
            user_id,
        )

    async def revoke_by_hash(self, token_hash: str) -> None:
        await self.conn.execute(
            "UPDATE refresh_tokens SET revoked_at = now() WHERE token_hash = $1 AND revoked_at IS NULL",
            token_hash,
        )
