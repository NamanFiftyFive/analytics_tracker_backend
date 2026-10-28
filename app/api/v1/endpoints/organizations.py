from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps import RequireRole, get_current_user, get_organization_service
from app.core.roles import Role
from app.schemas.auth import CurrentUser, MembershipOut
from app.schemas.client_response import ClientResponse
from app.schemas.organization import (
    AddMemberRequest,
    CurrentMember,
    MemberOut,
    OrganizationOut,
    UpdateMemberRoleRequest,
)
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.get("", response_model=ClientResponse[list[MembershipOut]])
async def list_my_organizations(
    user: CurrentUser = Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
):
    """Organizations the logged-in user belongs to, with their role in each.
    (Super admins see every organization under /admin/organizations.)"""
    return ClientResponse.success(await service.list_for_user(user.id))


@router.get("/{org_id}", response_model=ClientResponse[OrganizationOut])
async def get_organization(
    member: CurrentMember = Depends(RequireRole(Role.VIEWER)),
    service: OrganizationService = Depends(get_organization_service),
):
    return ClientResponse.success(await service.get(member))


@router.get("/{org_id}/members", response_model=ClientResponse[list[MemberOut]])
async def list_members(
    member: CurrentMember = Depends(RequireRole(Role.VIEWER)),
    service: OrganizationService = Depends(get_organization_service),
):
    return ClientResponse.success(await service.list_members(member.organization_id))


@router.post(
    "/{org_id}/members",
    response_model=ClientResponse[MemberOut],
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    data: AddMemberRequest,
    member: CurrentMember = Depends(RequireRole(Role.ADMIN)),
    service: OrganizationService = Depends(get_organization_service),
):
    """Admin only. Adds a user by email. If the email has no account yet, it is created with
    full_name and password (required in that case); give the person that password to log in."""
    new_member = await service.add_member(member.organization_id, data)
    return ClientResponse.success(new_member, status.HTTP_201_CREATED)


@router.patch("/{org_id}/members/{user_id}", response_model=ClientResponse[MemberOut])
async def change_member_role(
    user_id: UUID,
    data: UpdateMemberRoleRequest,
    member: CurrentMember = Depends(RequireRole(Role.ADMIN)),
    service: OrganizationService = Depends(get_organization_service),
):
    """Admin only. The last admin can't be demoted."""
    return ClientResponse.success(
        await service.change_role(member.organization_id, user_id, data.role)
    )


@router.delete("/{org_id}/members/{user_id}", response_model=ClientResponse[None])
async def remove_member(
    user_id: UUID,
    member: CurrentMember = Depends(RequireRole(Role.VIEWER)),
    service: OrganizationService = Depends(get_organization_service),
):
    """Admins can remove anyone; others can only remove themselves. The last admin can't leave."""
    await service.remove_member(member, user_id)
    return ClientResponse.success(None)
