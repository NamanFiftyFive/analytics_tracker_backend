from fastapi import APIRouter, Depends, status

from app.api.deps import get_auth_service, get_current_user
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.client_response import ClientResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=ClientResponse[TokenResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register(data: RegisterRequest, service: AuthService = Depends(get_auth_service)):
    """Create an account and its organization. The new user is the organization's admin."""
    return ClientResponse.success(await service.register(data), status.HTTP_201_CREATED)


@router.post("/login", response_model=ClientResponse[TokenResponse])
async def login(data: LoginRequest, service: AuthService = Depends(get_auth_service)):
    return ClientResponse.success(await service.login(data))


@router.post("/refresh", response_model=ClientResponse[TokenResponse])
async def refresh(data: RefreshRequest, service: AuthService = Depends(get_auth_service)):
    """Get a new access token. The refresh token sent is used up; store the new one."""
    return ClientResponse.success(await service.refresh(data.refresh_token))


@router.post("/logout", response_model=ClientResponse[None])
async def logout(data: RefreshRequest, service: AuthService = Depends(get_auth_service)):
    await service.logout(data.refresh_token)
    return ClientResponse.success(None)


@router.get("/me", response_model=ClientResponse[MeResponse])
async def me(
    user: CurrentUser = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    """The logged-in user (including is_superadmin) and their organizations."""
    return ClientResponse.success(await service.me(user.id))
