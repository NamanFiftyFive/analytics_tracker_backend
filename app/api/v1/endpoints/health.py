from fastapi import APIRouter

from app.core.exceptions import ServiceUnavailableError
from app.db.database import db
from app.schemas.client_response import ClientResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ClientResponse[dict])
async def health():
    return ClientResponse.success({"api": "ok"})


@router.get("/health/db", response_model=ClientResponse[dict])
async def health_db():
    try:
        version = await db.fetchval("SELECT version()")
    except Exception as exc:
        raise ServiceUnavailableError(f"Database unavailable: {exc}") from exc
    return ClientResponse.success({"database": "ok", "version": version})
