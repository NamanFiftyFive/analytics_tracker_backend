"""Super admin API: manage every organization and user on the platform."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_admin_service, require_superadmin
from app.schemas.admin import (
    AdminOrganizationDetail,
    AdminOrganizationOut,
    AdminUserOut,
    CreateOrganizationRequest,
    PlatformStats,
    UpdateOrganizationRequest,
    UpdateUserRequest,
)
from app.schemas.auth import CurrentUser
from app.schemas.client_response import ClientResponse
from app.schemas.pagination import Page
from app.services.admin_service import AdminService

# Every route here requires a super admin.
router = APIRouter(prefix="/admin", tags=["super admin"], dependencies=[Depends(require_superadmin)])


@router.get("/stats", response_model=ClientResponse[PlatformStats])
async def platform_stats(service: AdminService = Depends(get_admin_service)):
    return ClientResponse.success(await service.stats())


# ── Organizations ────────────────────────────────────────────────────────────

@router.get("/organizations", response_model=ClientResponse[Page[AdminOrganizationOut]])
async def list_organizations(
    search: str | None = Query(default=None, max_length=100, description="Matches name or slug"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: AdminService = Depends(get_admin_service),
):
    return ClientResponse.success(await service.list_organizations(search, limit, offset))


@router.post(
    "/organizations",
    response_model=ClientResponse[AdminOrganizationDetail],
    status_code=status.HTTP_201_CREATED,
)
async def create_organization(
    data: CreateOrganizationRequest, service: AdminService = Depends(get_admin_service)
):
    """Create an organization for a customer with its first admin (existing or new account)."""
    return ClientResponse.success(await service.create_organization(data), status.HTTP_201_CREATED)


@router.get("/organizations/{org_id}", response_model=ClientResponse[AdminOrganizationDetail])
async def get_organization(org_id: UUID, service: AdminService = Depends(get_admin_service)):
    return ClientResponse.success(await service.get_organization(org_id))


@router.patch("/organizations/{org_id}", response_model=ClientResponse[AdminOrganizationDetail])
async def update_organization(
    org_id: UUID, data: UpdateOrganizationRequest, service: AdminService = Depends(get_admin_service)
):
    """Rename, change plan, or suspend (`is_active: false`) / reactivate an organization."""
    return ClientResponse.success(await service.update_organization(org_id, data))


# ── Users ────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=ClientResponse[Page[AdminUserOut]])
async def list_users(
    search: str | None = Query(default=None, max_length=100, description="Matches email or name"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: AdminService = Depends(get_admin_service),
):
    return ClientResponse.success(await service.list_users(search, limit, offset))


@router.patch("/users/{user_id}", response_model=ClientResponse[AdminUserOut])
async def update_user(
    user_id: UUID,
    data: UpdateUserRequest,
    admin: CurrentUser = Depends(require_superadmin),
    service: AdminService = Depends(get_admin_service),
):
    """Deactivate (`is_active: false`, also logs them out everywhere) or reactivate an account."""
    return ClientResponse.success(await service.update_user(admin.id, user_id, data))
