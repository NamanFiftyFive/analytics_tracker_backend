from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.core.roles import Role


# ── Requests ─────────────────────────────────────────────────────────────────

class AddMemberRequest(BaseModel):
    """If the email has no account yet, one is created with full_name and password
    (password is then required). Existing users are just added; full_name and password are ignored."""

    email: EmailStr = Field(examples=["teammate@example.com"])
    role: Role = Field(default=Role.VIEWER, examples=[Role.ANALYST])
    full_name: str | None = Field(default=None, max_length=120, examples=["Ravi Kumar"])
    password: str | None = Field(default=None, min_length=8, max_length=128, examples=["temporary123"])


class UpdateMemberRoleRequest(BaseModel):
    role: Role = Field(examples=[Role.ANALYST])


# ── Responses ────────────────────────────────────────────────────────────────

class OrganizationOut(BaseModel):
    id: UUID
    name: str
    slug: str
    plan: str
    is_active: bool
    created_at: datetime
    your_role: Role


class MemberOut(BaseModel):
    user_id: UUID
    email: EmailStr
    full_name: str | None
    role: Role
    joined_at: datetime


class CurrentMember(BaseModel):
    """The logged-in user as a member of the organization in the URL (set by RequireRole)."""

    organization_id: UUID
    user_id: UUID
    role: Role
    is_superadmin: bool = False  # True when a super admin is acting inside this organization
