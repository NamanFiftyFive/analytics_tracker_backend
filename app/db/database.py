import json
from collections.abc import AsyncGenerator, Iterable, Sequence
from contextlib import asynccontextmanager
from typing import Any
from app.core.config import settings
import asyncpg
from asyncpg.pool import PoolConnectionProxy

# What pool.acquire() hands out: a wrapper that forwards every call to a real
# asyncpg.Connection. Use this type for connections borrowed from the pool.
PooledConnection = PoolConnectionProxy


class Database:
    """Owns the asyncpg connection pool and exposes raw-SQL helpers.

    Use the query helpers (fetch, fetchrow, ...) for single statements; each one
    borrows a connection from the pool and returns it right away. Use
    `connection()` to run several statements on the same connection, and
    `transaction()` when they must succeed or fail together.
    """

    def __init__(
        self,
        dsn: str,
        min_size: int = 2,
        max_size: int = 20,
        command_timeout: float = 60,
    ) -> None:
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._command_timeout = command_timeout
        self._pool: asyncpg.Pool | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
            command_timeout=self._command_timeout,
            init=self._init_connection,
        )

    async def disconnect(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def is_connected(self) -> bool:
        return self._pool is not None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return self._pool

    @staticmethod
    async def _init_connection(conn: asyncpg.Connection) -> None:
        # Return json/jsonb columns as Python dicts/lists instead of strings.
        for type_name in ("json", "jsonb"):
            await conn.set_type_codec(
                type_name, encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
            )

    # ── Connections & transactions ───────────────────────────────────────────

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[PooledConnection, None]:
        async with self.pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[PooledConnection, None]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    # ── Query helpers ────────────────────────────────────────────────────────

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        """All matching rows."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        """First row, or None."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any, column: int = 0) -> Any:
        """A single value from the first row."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args, column=column)

    async def execute(self, query: str, *args: Any) -> str:
        """INSERT/UPDATE/DELETE/DDL. Returns the status tag, e.g. 'UPDATE 3'."""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def executemany(self, query: str, args: Iterable[Sequence[Any]]) -> None:
        """Run one statement for each parameter tuple."""
        async with self.pool.acquire() as conn:
            await conn.executemany(query, args)

    async def copy_records(
        self, table: str, records: Iterable[Sequence[Any]], columns: Sequence[str]
    ) -> str:
        """Bulk insert with COPY; much faster than INSERT for large batches (e.g. events)."""
        async with self.pool.acquire() as conn:
            return await conn.copy_records_to_table(table, records=records, columns=columns)


# Anything repositories can run SQL on: the shared `db` (one pooled connection
# per call) or a connection from `db.transaction()` / `db.connection()`.
Executor = Database | PooledConnection


db = Database(
    dsn=settings.database_url,
    min_size=settings.DB_POOL_MIN_SIZE,
    max_size=settings.DB_POOL_MAX_SIZE,
)


async def get_db() -> AsyncGenerator[PooledConnection, None]:
    """FastAPI dependency: one pooled connection for the whole request."""
    async with db.connection() as conn:
        yield conn
