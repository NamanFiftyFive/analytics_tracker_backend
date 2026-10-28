from uuid import UUID

from app.core.exceptions import BadRequestError, NotFoundError
from app.db.database import db
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.stats_repository import StatsRepository
from app.repositories.user_repository import UserRepository
from app.schemas.admin import (
    AdminOrganizationDetail,
    AdminOrganizationOut,
    AdminUserOut,
    CreateOrganizationRequest,
    PlatformStats,
    UpdateOrganizationRequest,
    UpdateUserRequest,
)
from app.schemas.organization import MemberOut
from app.schemas.pagination import Page
from app.services.organization_service import OrganizationService
from app.services.user_service import UserService


class AdminService:
    """Everything the super admin can do across the whole platform."""

    async def stats(self) -> PlatformStats:
        return PlatformStats(**dict(await StatsRepository().platform_totals()))

    # ── Organizations ────────────────────────────────────────────────────────

    async def list_organizations(
        self, search: str | None, limit: int, offset: int
    ) -> Page[AdminOrganizationOut]:
        orgs = OrganizationRepository()
        rows = await orgs.search(search, limit, offset)
        return Page(
            items=[AdminOrganizationOut(**dict(row)) for row in rows],
            total=await orgs.count(search),
            limit=limit,
            offset=offset,
        )

    async def get_organization(self, organization_id: UUID) -> AdminOrganizationDetail:
        orgs = OrganizationRepository()
        org = await orgs.get_with_counts(organization_id)
        if org is None:
            raise NotFoundError("Organization not found")
        members = await orgs.list_members(organization_id)
        return AdminOrganizationDetail(
            organization=AdminOrganizationOut(**dict(org)),
            members=[MemberOut(**dict(m)) for m in members],
        )

    async def create_organization(self, data: CreateOrganizationRequest) -> AdminOrganizationDetail:
        """Organization + its first admin (existing account, or a new one) in one transaction."""
        async with db.transaction() as conn:
            admin, _ = await UserService.get_or_create(
                conn, data.admin_email, data.admin_full_name, data.admin_password
            )
            org = await OrganizationService.create_with_admin(
                conn, data.organization_name, admin["id"], plan=data.plan
            )
        return await self.get_organization(org["id"])

    async def update_organization(
        self, organization_id: UUID, data: UpdateOrganizationRequest
    ) -> AdminOrganizationDetail:
        updated = await OrganizationRepository().update(
            organization_id, name=data.name, plan=data.plan, is_active=data.is_active
        )
        if updated is None:
            raise NotFoundError("Organization not found")
        return await self.get_organization(organization_id)

    # ── Users ────────────────────────────────────────────────────────────────

    async def list_users(self, search: str | None, limit: int, offset: int) -> Page[AdminUserOut]:
        users = UserRepository()
        rows = await users.search(search, limit, offset)
        return Page(
            items=[AdminUserOut(**dict(row)) for row in rows],
            total=await users.count(search),
            limit=limit,
            offset=offset,
        )

    async def update_user(
        self, acting_user_id: UUID, user_id: UUID, data: UpdateUserRequest
    ) -> AdminUserOut:
        if user_id == acting_user_id and not data.is_active:
            raise BadRequestError("You can't deactivate your own account")

        async with db.transaction() as conn:
            user = await UserRepository(conn).set_active(user_id, data.is_active)
            if user is None:
                raise NotFoundError("User not found")
            if not data.is_active:
                await RefreshTokenRepository(conn).revoke_all_for_user(user_id)

        row = await UserRepository().get_with_org_count(user_id)
        assert row is not None
        return AdminUserOut(**dict(row))
