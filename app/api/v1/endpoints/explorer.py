from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import RequireRole, get_explorer_service
from app.core.roles import Role
from app.schemas.client_response import ClientResponse
from app.schemas.explorer import EventDefinitionOut, EventPage, PersonDetail, PersonFilter, PersonPage
from app.schemas.organization import CurrentMember
from app.services.explorer_service import ExplorerService

events_router = APIRouter(prefix="/orgs/{org_id}/projects/{project_id}", tags=["events"])
persons_router = APIRouter(prefix="/orgs/{org_id}/projects/{project_id}/persons", tags=["users"])


@events_router.get("/events", response_model=ClientResponse[EventPage])
async def list_events(
    project_id: UUID,
    event: str | None = Query(default=None, max_length=200, description="Only this event name"),
    person_id: UUID | None = Query(default=None, description="Only this user's events"),
    search: str | None = Query(default=None, max_length=100, description="User id, screen or property text"),
    cursor: str | None = Query(default=None, description="`next_cursor` from the previous page"),
    limit: int = Query(default=50, ge=1, le=100),
    member: CurrentMember = Depends(RequireRole(Role.VIEWER)),
    service: ExplorerService = Depends(get_explorer_service),
):
    """Newest events first. Load older ones with `cursor`."""
    page = await service.events(
        member.organization_id,
        project_id,
        event_name=event,
        person_id=person_id,
        search=search,
        cursor=cursor,
        limit=limit,
    )
    return ClientResponse.success(page)


@events_router.get("/event-definitions", response_model=ClientResponse[list[EventDefinitionOut]])
async def list_event_definitions(
    project_id: UUID,
    member: CurrentMember = Depends(RequireRole(Role.VIEWER)),
    service: ExplorerService = Depends(get_explorer_service),
):
    """Every event name seen in the project, most recently seen first."""
    return ClientResponse.success(await service.definitions(member.organization_id, project_id))


@persons_router.get("", response_model=ClientResponse[PersonPage])
async def list_persons(
    project_id: UUID,
    filter: PersonFilter = Query(default="all", description="all, identified, or new (first seen in 7 days)"),
    search: str | None = Query(default=None, max_length=100, description="User id or trait text"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    member: CurrentMember = Depends(RequireRole(Role.VIEWER)),
    service: ExplorerService = Depends(get_explorer_service),
):
    """The app's end users, most recently active first, with counts for each filter."""
    page = await service.persons(
        member.organization_id, project_id, person_filter=filter, search=search, limit=limit, offset=offset
    )
    return ClientResponse.success(page)


@persons_router.get("/{person_id}", response_model=ClientResponse[PersonDetail])
async def get_person(
    project_id: UUID,
    person_id: UUID,
    member: CurrentMember = Depends(RequireRole(Role.VIEWER)),
    service: ExplorerService = Depends(get_explorer_service),
):
    """One user: traits, totals and their 5 most recent sessions with events."""
    return ClientResponse.success(await service.person_detail(member.organization_id, project_id, person_id))
