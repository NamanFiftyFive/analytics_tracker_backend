from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.core.roles import Role


# ── Requests ─────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=120)
    organization_name: str = Field(min_length=2, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Responses ────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_superadmin: bool
    last_login_at: datetime | None
    created_at: datetime


class MembershipOut(BaseModel):
    id: UUID
    name: str
    slug: str
    plan: str
    is_active: bool
    role: Role


class MeResponse(BaseModel):
    user: UserOut
    organizations: list[MembershipOut]


class CurrentUser(BaseModel):
    """The logged-in user, loaded from the database on every authenticated request."""

    id: UUID
    email: EmailStr
    is_superadmin: bool
