from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps import RequireRole, get_api_key_service
from app.core.roles import Role
from app.schemas.client_response import ClientResponse
from app.schemas.organization import CurrentMember
from app.schemas.project import ApiKeyCreatedOut, ApiKeyOut, CreateApiKeyRequest
from app.services.api_key_service import ApiKeyService

# API keys are secrets for sending data, so every route here is admin only.
router = APIRouter(prefix="/orgs/{org_id}/projects/{project_id}/api-keys", tags=["api keys"])


@router.get("", response_model=ClientResponse[list[ApiKeyOut]])
async def list_api_keys(
    project_id: UUID,
    member: CurrentMember = Depends(RequireRole(Role.ADMIN)),
    service: ApiKeyService = Depends(get_api_key_service),
):
    """Shows each key's name and visible prefix only; full keys are never shown again."""
    return ClientResponse.success(await service.list_keys(member.organization_id, project_id))


@router.post("", response_model=ClientResponse[ApiKeyCreatedOut], status_code=status.HTTP_201_CREATED)
async def create_api_key(
    project_id: UUID,
    data: CreateApiKeyRequest,
    member: CurrentMember = Depends(RequireRole(Role.ADMIN)),
    service: ApiKeyService = Depends(get_api_key_service),
):
    """New key for this project. `data.key` is shown only in this response; store it now."""
    key = await service.create(member.organization_id, project_id, data.name)
    return ClientResponse.success(key, status.HTTP_201_CREATED)


@router.delete("/{key_id}", response_model=ClientResponse[ApiKeyOut])
async def revoke_api_key(
    project_id: UUID,
    key_id: UUID,
    member: CurrentMember = Depends(RequireRole(Role.ADMIN)),
    service: ApiKeyService = Depends(get_api_key_service),
):
    """Revokes the key: it stops working immediately but stays listed for history."""
    return ClientResponse.success(await service.revoke(member.organization_id, project_id, key_id))
