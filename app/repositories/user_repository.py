from uuid import UUID

import asyncpg

from app.db.database import Executor, db
from app.repositories.search import contains_pattern

_PUBLIC_COLUMNS = "id, email, full_name, is_active, is_superadmin, last_login_at, created_at"


class UserRepository:
    def __init__(self, conn: Executor = db) -> None:
        self.conn = conn

    async def get_by_id(self, user_id: UUID) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            f"SELECT {_PUBLIC_COLUMNS} FROM users WHERE id = $1",
            user_id,
        )

    async def get_by_email(self, email: str) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            f"SELECT {_PUBLIC_COLUMNS} FROM users WHERE lower(email) = lower($1)",
            email,
        )

    async def get_by_email_with_password(self, email: str) -> asyncpg.Record | None:
        """Includes password_hash; only for login."""
        return await self.conn.fetchrow(
            f"SELECT {_PUBLIC_COLUMNS}, password_hash FROM users WHERE lower(email) = lower($1)",
            email,
        )

    async def email_exists(self, email: str) -> bool:
        return await self.conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM users WHERE lower(email) = lower($1))",
            email,
        )

    async def create(self, email: str, password_hash: str, full_name: str | None) -> asyncpg.Record:
        row = await self.conn.fetchrow(
            f"""
            INSERT INTO users (email, password_hash, full_name)
            VALUES ($1, $2, $3)
            RETURNING {_PUBLIC_COLUMNS}
            """,
            email,
            password_hash,
            full_name,
        )
        assert row is not None
        return row

    async def touch_last_login(self, user_id: UUID) -> None:
        await self.conn.execute("UPDATE users SET last_login_at = now() WHERE id = $1", user_id)

    async def set_superadmin(self, user_id: UUID, value: bool) -> None:
        await self.conn.execute("UPDATE users SET is_superadmin = $2 WHERE id = $1", user_id, value)

    async def set_active(self, user_id: UUID, value: bool) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            f"UPDATE users SET is_active = $2 WHERE id = $1 RETURNING {_PUBLIC_COLUMNS}",
            user_id,
            value,
        )

    # ── Super admin listing ──────────────────────────────────────────────────

    _ADMIN_COLUMNS = f"""{_PUBLIC_COLUMNS},
        (SELECT count(*) FROM organization_members m WHERE m.user_id = users.id) AS organization_count"""

    async def get_with_org_count(self, user_id: UUID) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            f"SELECT {self._ADMIN_COLUMNS} FROM users WHERE id = $1",
            user_id,
        )

    async def search(self, search: str | None, limit: int, offset: int) -> list[asyncpg.Record]:
        """All users (newest first), optionally filtered by email or name, with how many orgs each is in."""
        return await self.conn.fetch(
            f"""
            SELECT {self._ADMIN_COLUMNS}
            FROM users
            WHERE $1::text IS NULL OR email ILIKE $1 OR full_name ILIKE $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            contains_pattern(search),
            limit,
            offset,
        )

    async def count(self, search: str | None) -> int:
        return await self.conn.fetchval(
            """
            SELECT count(*) FROM users
            WHERE $1::text IS NULL OR email ILIKE $1 OR full_name ILIKE $1
            """,
            contains_pattern(search),
        )
