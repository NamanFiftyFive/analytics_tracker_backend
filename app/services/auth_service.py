from uuid import UUID

import asyncpg

from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import PasswordService, TokenService
from app.db.database import Executor, db
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    LoginRequest,
    MembershipOut,
    MeResponse,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services.organization_service import OrganizationService


class AuthService:
    async def register(self, data: RegisterRequest) -> TokenResponse:
        """Create the user, their organization, and make them its admin, all or nothing."""
        async with db.transaction() as conn:
            users = UserRepository(conn)

            if await users.email_exists(data.email):
                raise ConflictError("An account with this email already exists")

            try:
                user = await users.create(
                    email=data.email,
                    password_hash=PasswordService.hash(data.password),
                    full_name=data.full_name,
                )
            except asyncpg.UniqueViolationError:
                # Same email registered by a concurrent request.
                raise ConflictError("An account with this email already exists") from None

            await OrganizationService.create_with_admin(conn, data.organization_name, user["id"])
            return await self._issue_tokens(conn, user["id"])

    async def login(self, data: LoginRequest) -> TokenResponse:
        users = UserRepository()
        user = await users.get_by_email_with_password(data.email)

        password_ok = PasswordService.verify(
            data.password, user["password_hash"] if user else None
        )
        if user is None or not password_ok:
            raise UnauthorizedError("Incorrect email or password")
        if not user["is_active"]:
            raise ForbiddenError("This account is disabled")

        async with db.transaction() as conn:
            await UserRepository(conn).touch_last_login(user["id"])
            return await self._issue_tokens(conn, user["id"])

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Swap a refresh token for a new pair. The old one stops working (rotation)."""
        token_hash = TokenService.hash_refresh_token(refresh_token)
        async with db.transaction() as conn:
            tokens = RefreshTokenRepository(conn)
            row = await tokens.get_active_for_update(token_hash)
            if row is None:
                raise UnauthorizedError("Refresh token is invalid or expired")

            user = await UserRepository(conn).get_by_id(row["user_id"])
            if user is None or not user["is_active"]:
                raise UnauthorizedError("Refresh token is invalid or expired")

            await tokens.revoke(row["id"])
            return await self._issue_tokens(conn, row["user_id"])

    async def logout(self, refresh_token: str) -> None:
        await RefreshTokenRepository().revoke_by_hash(
            TokenService.hash_refresh_token(refresh_token)
        )

    async def me(self, user_id: UUID) -> MeResponse:
        user = await UserRepository().get_by_id(user_id)
        if user is None:
            raise UnauthorizedError("User no longer exists")
        memberships = await OrganizationRepository().list_memberships(user_id)
        return MeResponse(
            user=UserOut(**dict(user)),
            organizations=[MembershipOut(**dict(m)) for m in memberships],
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    async def _issue_tokens(conn: Executor, user_id: UUID) -> TokenResponse:
        access_token, expires_in = TokenService.create_access_token(user_id)
        refresh_token, refresh_hash, refresh_expires_at = TokenService.new_refresh_token()
        await RefreshTokenRepository(conn).create(user_id, refresh_hash, refresh_expires_at)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )
