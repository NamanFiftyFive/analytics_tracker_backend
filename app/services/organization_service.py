import re
import secrets
from uuid import UUID

import asyncpg

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.roles import Role
from app.db.database import Executor, db
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.auth import MembershipOut
from app.schemas.organization import AddMemberRequest, CurrentMember, MemberOut, OrganizationOut
from app.services.user_service import UserService


class OrganizationService:
    @staticmethod
    async def create_with_admin(
        conn: Executor, name: str, admin_user_id: UUID, plan: str = "free"
    ) -> asyncpg.Record:
        """New organization with the given user as its admin. Used by registration and by the
        super admin. Call inside a transaction."""
        orgs = OrganizationRepository(conn)
        org = await orgs.create(name=name, slug=await OrganizationService._unique_slug(orgs, name), plan=plan)
        await orgs.add_member(org["id"], admin_user_id, role=Role.ADMIN)
        return org

    async def list_for_user(self, user_id: UUID) -> list[MembershipOut]:
        rows = await OrganizationRepository().list_memberships(user_id)
        return [MembershipOut(**dict(row)) for row in rows]

    async def get(self, member: CurrentMember) -> OrganizationOut:
        org = await OrganizationRepository().get_by_id(member.organization_id)
        if org is None:
            raise NotFoundError("Organization not found")
        return OrganizationOut(**dict(org), your_role=member.role)

    async def list_members(self, organization_id: UUID) -> list[MemberOut]:
        rows = await OrganizationRepository().list_members(organization_id)
        return [MemberOut(**dict(row)) for row in rows]

    async def add_member(self, organization_id: UUID, data: AddMemberRequest) -> MemberOut:
        """Add a user to the organization, creating their account first if the email is new."""
        async with db.transaction() as conn:
            user, _ = await UserService.get_or_create(conn, data.email, data.full_name, data.password)
            orgs = OrganizationRepository(conn)
            if await orgs.get_member(organization_id, user["id"]) is not None:
                raise ConflictError("This user is already a member of the organization")
            try:
                await orgs.add_member(organization_id, user["id"], data.role)
            except asyncpg.UniqueViolationError:
                # Added by a concurrent request between the check and the insert.
                raise ConflictError("This user is already a member of the organization") from None
            row = await orgs.get_member(organization_id, user["id"])

        assert row is not None
        return MemberOut(**dict(row))

    async def change_role(self, organization_id: UUID, user_id: UUID, role: Role) -> MemberOut:
        async with db.transaction() as conn:
            orgs = OrganizationRepository(conn)
            member = await orgs.get_member(organization_id, user_id, for_update=True)
            if member is None:
                raise NotFoundError("Member not found")

            if member["role"] == Role.ADMIN and role != Role.ADMIN:
                await self._ensure_not_last_admin(orgs, organization_id, user_id)

            await orgs.update_member_role(organization_id, user_id, role)
            row = await orgs.get_member(organization_id, user_id)

        assert row is not None
        return MemberOut(**dict(row))

    async def remove_member(self, actor: CurrentMember, user_id: UUID) -> None:
        """Admins can remove anyone; other members can only remove themselves (leave)."""
        if actor.user_id != user_id and actor.role != Role.ADMIN:
            raise ForbiddenError("Only admins can remove other members")

        async with db.transaction() as conn:
            orgs = OrganizationRepository(conn)
            member = await orgs.get_member(actor.organization_id, user_id, for_update=True)
            if member is None:
                raise NotFoundError("Member not found")

            if member["role"] == Role.ADMIN:
                await self._ensure_not_last_admin(orgs, actor.organization_id, user_id)

            await orgs.remove_member(actor.organization_id, user_id)

    @staticmethod
    async def _unique_slug(orgs: OrganizationRepository, name: str) -> str:
        """'Acme Inc.' -> 'acme-inc', or 'acme-inc-3f9a' if that is taken."""
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "org"
        slug = base
        while await orgs.slug_exists(slug):
            slug = f"{base}-{secrets.token_hex(2)}"
        return slug

    @staticmethod
    async def _ensure_not_last_admin(
        orgs: OrganizationRepository, organization_id: UUID, user_id: UUID
    ) -> None:
        admin_ids = await orgs.lock_admin_ids(organization_id)
        if admin_ids == [user_id]:
            raise ConflictError("An organization must keep at least one admin")
