from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps import RequireRole, get_project_service
from app.core.roles import Role
from app.schemas.client_response import ClientResponse
from app.schemas.organization import CurrentMember
from app.schemas.project import (
    CreateProjectRequest,
    ProjectCreatedOut,
    ProjectOut,
    UpdateProjectRequest,
)
from app.services.project_service import ProjectService

router = APIRouter(prefix="/orgs/{org_id}/projects", tags=["projects"])


@router.get("", response_model=ClientResponse[list[ProjectOut]])
async def list_projects(
    member: CurrentMember = Depends(RequireRole(Role.VIEWER)),
    service: ProjectService = Depends(get_project_service),
):
    return ClientResponse.success(await service.list_projects(member.organization_id))


@router.post("", response_model=ClientResponse[ProjectCreatedOut], status_code=status.HTTP_201_CREATED)
async def create_project(
    data: CreateProjectRequest,
    member: CurrentMember = Depends(RequireRole(Role.ADMIN)),
    service: ProjectService = Depends(get_project_service),
):
    """Admin only. Also creates the first API key: `data.api_key.key` is shown only in this response."""
    project = await service.create(member.organization_id, data)
    return ClientResponse.success(project, status.HTTP_201_CREATED)


@router.get("/{project_id}", response_model=ClientResponse[ProjectOut])
async def get_project(
    project_id: UUID,
    member: CurrentMember = Depends(RequireRole(Role.VIEWER)),
    service: ProjectService = Depends(get_project_service),
):
    return ClientResponse.success(await service.get(member.organization_id, project_id))


@router.patch("/{project_id}", response_model=ClientResponse[ProjectOut])
async def update_project(
    project_id: UUID,
    data: UpdateProjectRequest,
    member: CurrentMember = Depends(RequireRole(Role.ADMIN)),
    service: ProjectService = Depends(get_project_service),
):
    """Admin only. Change name, platform, timezone or allowed website origins."""
    return ClientResponse.success(await service.update(member.organization_id, project_id, data))


@router.delete("/{project_id}", response_model=ClientResponse[None])
async def delete_project(
    project_id: UUID,
    member: CurrentMember = Depends(RequireRole(Role.ADMIN)),
    service: ProjectService = Depends(get_project_service),
):
    """Admin only. Permanently deletes the project with its API keys, events, sessions,
    dashboards and alerts."""
    await service.delete(member.organization_id, project_id)
    return ClientResponse.success(None)
