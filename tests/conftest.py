"""Shared fixtures. Tests run against a separate database, hackathon_2026_test, never the real one.

Set before any app module is imported: app.core.config reads settings once, and an environment
variable beats the value in .env. So the whole app (db pool included) points at the test database.
"""

import os

os.environ["POSTGRES_DB"] = "hackathon_2026_test"

import subprocess  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.database import db  # noqa: E402
from app.main import app  # noqa: E402
from tests.helpers import AuthActions, IngestActions, OrgActions, ProjectActions  # noqa: E402


class DatabaseForTests:
    """Brings the test database up to date and empties it between tests."""

    MIGRATIONS_DIR = "migrations"

    @staticmethod
    def check_is_test_database() -> None:
        # Last line of defence: reset() deletes every row, so never point it at real data.
        if not settings.POSTGRES_DB.endswith("_test"):
            raise RuntimeError(f"Refusing to run tests against {settings.POSTGRES_DB!r}")

    @classmethod
    def migrate(cls) -> None:
        """Apply any new migrations, the same .sql files the real database uses."""
        url = settings.database_url.replace("postgresql://", "postgres://", 1) + "?sslmode=disable"
        result = subprocess.run(
            ["dbmate", "--url", url, "--migrations-dir", cls.MIGRATIONS_DIR, "--no-dump-schema", "up"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"dbmate up failed on the test database:\n{result.stderr}")

    @staticmethod
    async def reset() -> None:
        """Delete all rows from every table (not schema_migrations), so each test starts empty.
        TRUNCATE on the partitioned events table also empties its partitions."""
        tables = await db.fetch(
            """
            SELECT format('%I', c.relname) AS name
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'p')
              AND NOT c.relispartition
              AND c.relname <> 'schema_migrations'
            """
        )
        names = ", ".join(row["name"] for row in tables)
        await db.execute(f"TRUNCATE {names} RESTART IDENTITY CASCADE")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def database() -> AsyncGenerator[None, None]:
    """Once per run: migrate, then open the pool (the app's lifespan does this when served)."""
    DatabaseForTests.check_is_test_database()
    DatabaseForTests.migrate()
    await db.connect()
    yield
    await db.disconnect()


@pytest_asyncio.fixture(autouse=True)
async def clean_database(database: None) -> None:
    """Before each test, so a test never sees rows left by another (or by a crashed run)."""
    await DatabaseForTests.reset()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Calls the app in memory: no server, no port, same middleware and error handlers."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
def auth(client: AsyncClient) -> AuthActions:
    return AuthActions(client)


@pytest.fixture
def orgs(client: AsyncClient, auth: AuthActions) -> OrgActions:
    return OrgActions(client, auth)


@pytest.fixture
def projects(client: AsyncClient) -> ProjectActions:
    return ProjectActions(client)


@pytest.fixture
def ingest(client: AsyncClient) -> IngestActions:
    return IngestActions(client)
