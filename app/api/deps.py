from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.roles import Role
from app.core.security import TokenService
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import CurrentUser
from app.schemas.organization import CurrentMember
from app.services.admin_service import AdminService
from app.services.api_key_service import ApiKeyService
from app.services.auth_service import AuthService
from app.services.explorer_service import ExplorerService
from app.services.ingest_service import IngestService
from app.services.insights_service import InsightsService
from app.services.organization_service import OrganizationService
from app.services.project_service import ProjectService

# Adds the "Authorize" button in /docs: paste the access_token from login there.
_bearer = HTTPBearer(auto_error=False)


# ── Services ─────────────────────────────────────────────────────────────────

def get_auth_service() -> AuthService:
    return AuthService()


def get_organization_service() -> OrganizationService:
    return OrganizationService()


def get_admin_service() -> AdminService:
    return AdminService()


def get_project_service() -> ProjectService:
    return ProjectService()


def get_api_key_service() -> ApiKeyService:
    return ApiKeyService()


def get_ingest_service() -> IngestService:
    return IngestService()


def get_insights_service() -> InsightsService:
    return InsightsService()


def get_explorer_service() -> ExplorerService:
    return ExplorerService()


# ── Who is calling ───────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """Reads `Authorization: Bearer <access_token>` and loads that user. Checked against the
    database on every request, so a deactivated account stops working immediately."""
    if credentials is None:
        raise UnauthorizedError("Not authenticated")
    user_id = TokenService.decode_access_token(credentials.credentials)
    if user_id is None:
        raise UnauthorizedError("Access token is invalid or expired")

    user = await UserRepository().get_by_id(user_id)
    if user is None:
        raise UnauthorizedError("User no longer exists")
    if not user["is_active"]:
        raise ForbiddenError("This account is disabled")
    return CurrentUser(id=user["id"], email=user["email"], is_superadmin=user["is_superadmin"])


async def require_superadmin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Platform owner only (users.is_superadmin)."""
    if not user.is_superadmin:
        raise ForbiddenError("Super admin access required")
    return user


class RequireRole:
    """Dependency for routes with {org_id} in the path. Lets the request through only if the
    logged-in user is a member of that organization with at least `minimum` role.
    Super admins always pass, acting as admin in every organization.

        member: CurrentMember = Depends(RequireRole(Role.ADMIN))
    """

    def __init__(self, minimum: Role) -> None:
        self.minimum = minimum

    async def __call__(
        self,
        org_id: UUID,
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentMember:
        access = await OrganizationRepository().get_access(org_id, user.id)

        if access is not None and user.is_superadmin:
            return CurrentMember(
                organization_id=org_id, user_id=user.id, role=Role.ADMIN, is_superadmin=True
            )
        if access is None or access["role"] is None:
            # Same answer whether the organization exists or not, so ids can't be probed.
            raise NotFoundError("Organization not found")
        if not access["is_active"]:
            raise ForbiddenError("This organization is suspended")

        member = CurrentMember(organization_id=org_id, user_id=user.id, role=Role(access["role"]))
        if not member.role.at_least(self.minimum):
            or_higher = "" if self.minimum == Role.ADMIN else " or higher"
            raise ForbiddenError(f"This action requires the {self.minimum} role{or_higher}")
        return member
