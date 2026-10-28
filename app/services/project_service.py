from uuid import UUID

from app.core.exceptions import NotFoundError
from app.db.database import db
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import (
    CreateProjectRequest,
    ProjectCreatedOut,
    ProjectOut,
    UpdateProjectRequest,
)
from app.services.api_key_service import ApiKeyService


class ProjectService:
    async def list_projects(self, organization_id: UUID) -> list[ProjectOut]:
        rows = await ProjectRepository().list_for_organization(organization_id)
        return [ProjectOut(**dict(row)) for row in rows]

    async def get(self, organization_id: UUID, project_id: UUID) -> ProjectOut:
        row = await ProjectRepository().get(organization_id, project_id)
        if row is None:
            raise NotFoundError("Project not found")
        return ProjectOut(**dict(row))

    async def create(self, organization_id: UUID, data: CreateProjectRequest) -> ProjectCreatedOut:
        """Creates the project and its first API key together, so it's ready to receive events."""
        async with db.transaction() as conn:
            project_id = await ProjectRepository(conn).create(
                organization_id,
                name=data.name,
                platform=data.platform,
                timezone=data.timezone,
                allowed_origins=data.allowed_origins,
            )
            api_key = await ApiKeyService.create_key(conn, project_id, name="Default key")
            project = await ProjectRepository(conn).get(organization_id, project_id)

        assert project is not None
        return ProjectCreatedOut(project=ProjectOut(**dict(project)), api_key=api_key)

    async def update(
        self, organization_id: UUID, project_id: UUID, data: UpdateProjectRequest
    ) -> ProjectOut:
        found = await ProjectRepository().update(
            organization_id,
            project_id,
            name=data.name,
            platform=data.platform,
            timezone=data.timezone,
            allowed_origins=data.allowed_origins,
        )
        if not found:
            raise NotFoundError("Project not found")
        return await self.get(organization_id, project_id)

    async def delete(self, organization_id: UUID, project_id: UUID) -> None:
        """Deletes the project with all its keys, events, sessions, dashboards and alerts."""
        async with db.transaction() as conn:
            if not await ProjectRepository(conn).delete_with_data(organization_id, project_id):
                raise NotFoundError("Project not found")
