from fastapi import APIRouter

from app.api.v1.endpoints import admin, api_keys, auth, explorer, health, ingest, insights, organizations, projects
from app.schemas.client_response import ClientResponse

# Documents the error shape in /docs (replaces FastAPI's default 422 schema).
api_router = APIRouter(
    responses={422: {"model": ClientResponse[None], "description": "Validation error"}},
)
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(projects.router)
api_router.include_router(api_keys.router)
api_router.include_router(ingest.router)
api_router.include_router(insights.router)
api_router.include_router(explorer.events_router)
api_router.include_router(explorer.persons_router)
api_router.include_router(admin.router)
