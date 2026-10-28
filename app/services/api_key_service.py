from uuid import UUID

from app.core.exceptions import NotFoundError
from app.core.security import ApiKeyGenerator
from app.db.database import Executor, db
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ApiKeyCreatedOut, ApiKeyOut


class ApiKeyService:
    @staticmethod
    async def create_key(conn: Executor, project_id: UUID, name: str) -> ApiKeyCreatedOut:
        """Generates a key, stores only its hash, and returns the full key this one time."""
        key, prefix, key_hash = ApiKeyGenerator.generate()
        row = await ApiKeyRepository(conn).create(project_id, name, prefix, key_hash)
        return ApiKeyCreatedOut(**dict(row), key=key)

    async def list_keys(self, organization_id: UUID, project_id: UUID) -> list[ApiKeyOut]:
        await self._ensure_project(organization_id, project_id)
        rows = await ApiKeyRepository().list_for_project(project_id)
        return [ApiKeyOut(**dict(row)) for row in rows]

    async def create(self, organization_id: UUID, project_id: UUID, name: str) -> ApiKeyCreatedOut:
        await self._ensure_project(organization_id, project_id)
        return await self.create_key(db, project_id, name)

    async def revoke(self, organization_id: UUID, project_id: UUID, key_id: UUID) -> ApiKeyOut:
        """The key stops working immediately; apps using it must switch to another key."""
        await self._ensure_project(organization_id, project_id)
        row = await ApiKeyRepository().revoke(project_id, key_id)
        if row is None:
            raise NotFoundError("API key not found")
        return ApiKeyOut(**dict(row))

    @staticmethod
    async def _ensure_project(organization_id: UUID, project_id: UUID) -> None:
        """The project must belong to the organization in the URL."""
        if not await ProjectRepository().exists(organization_id, project_id):
            raise NotFoundError("Project not found")
