import re
from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

Platform = Literal["web", "ios", "android", "flutter", "other"]

# scheme://host[:port], e.g. https://cars.example.com or http://localhost:3000
_ORIGIN_PATTERN = re.compile(r"^https?://[a-z0-9.-]+(:\d{1,5})?$")


def _check_timezone(value: str | None) -> str | None:
    if value is None:
        return value
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown timezone '{value}', use an IANA name like 'Asia/Kolkata'") from None
    return value


def _normalize_origins(values: list[str] | None) -> list[str] | None:
    """'https://Cars.Example.com/' -> 'https://cars.example.com'; duplicates removed."""
    if values is None:
        return values
    cleaned: list[str] = []
    for value in values:
        origin = value.strip().lower().rstrip("/")
        if not _ORIGIN_PATTERN.match(origin):
            raise ValueError(f"'{value}' is not an origin; use scheme://host[:port], e.g. https://example.com")
        if origin not in cleaned:
            cleaned.append(origin)
    return cleaned


# ── Requests ─────────────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120, examples=["Car App"])
    platform: Platform = Field(examples=["flutter"])
    timezone: str = Field(default="UTC", examples=["Asia/Kolkata"], description="Used for daily charts")
    allowed_origins: list[str] = Field(
        default_factory=list,
        max_length=20,
        examples=[["https://cars.example.com"]],
        description="Websites allowed to send events. Empty = any. Ignored for mobile apps.",
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str | None:
        return _check_timezone(value)

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, value: list[str]) -> list[str] | None:
        return _normalize_origins(value)


class UpdateProjectRequest(BaseModel):
    """Only the fields you send are changed. allowed_origins replaces the whole list."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    platform: Platform | None = None
    timezone: str | None = None
    allowed_origins: list[str] | None = Field(default=None, max_length=20)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        return _check_timezone(value)

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_origins(value)


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80, examples=["Android release"])


# ── Responses ────────────────────────────────────────────────────────────────

class ProjectOut(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    platform: Platform
    timezone: str
    allowed_origins: list[str]
    created_at: datetime
    active_api_keys: int


class ApiKeyOut(BaseModel):
    """A key as listed later: only the visible prefix, never the full key."""

    id: UUID
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreatedOut(ApiKeyOut):
    """Returned once, right after creation. Store `key` now; it can't be shown again."""

    key: str


class ProjectCreatedOut(BaseModel):
    project: ProjectOut
    api_key: ApiKeyCreatedOut
