"""Request and response models for the super admin API (/admin/...)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.organization import MemberOut

Plan = Literal["free", "pro", "enterprise"]


# ── Requests ─────────────────────────────────────────────────────────────────

class CreateOrganizationRequest(BaseModel):
    """Create an organization for a customer. If admin_email has no account yet, one is created
    with admin_full_name and admin_password (password is then required)."""

    organization_name: str = Field(min_length=2, max_length=120, examples=["Acme Corp"])
    plan: Plan = "free"
    admin_email: EmailStr = Field(examples=["owner@acme.com"])
    admin_full_name: str | None = Field(default=None, max_length=120, examples=["Acme Owner"])
    admin_password: str | None = Field(default=None, min_length=8, max_length=128, examples=["temporary123"])


class UpdateOrganizationRequest(BaseModel):
    """Only the fields you send are changed."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    plan: Plan | None = None
    is_active: bool | None = Field(default=None, description="false suspends the organization")


class UpdateUserRequest(BaseModel):
    is_active: bool = Field(description="false disables the account and logs the user out everywhere")


# ── Responses ────────────────────────────────────────────────────────────────

class PlatformStats(BaseModel):
    organizations: int
    active_organizations: int
    users: int
    active_users: int
    projects: int
    events_today: int


class AdminOrganizationOut(BaseModel):
    id: UUID
    name: str
    slug: str
    plan: str
    is_active: bool
    created_at: datetime
    member_count: int
    project_count: int


class AdminOrganizationDetail(BaseModel):
    organization: AdminOrganizationOut
    members: list[MemberOut]


class AdminUserOut(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_superadmin: bool
    last_login_at: datetime | None
    created_at: datetime
    organization_count: int
