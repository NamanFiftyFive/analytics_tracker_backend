from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import RequireRole, get_insights_service
from app.core.roles import Role
from app.schemas.client_response import ClientResponse
from app.schemas.insights import OverviewOut, OverviewRange
from app.schemas.organization import CurrentMember
from app.services.insights_service import InsightsService

router = APIRouter(prefix="/orgs/{org_id}/projects/{project_id}/insights", tags=["insights"])


@router.get("/overview", response_model=ClientResponse[OverviewOut])
async def overview(
    project_id: UUID,
    range: OverviewRange = Query(default="7d", description="today, 7d, 30d or 90d (days in the project timezone)"),
    member: CurrentMember = Depends(RequireRole(Role.VIEWER)),
    service: InsightsService = Depends(get_insights_service),
):
    """KPIs with the change vs the previous period, events per day, top screens and top events."""
    return ClientResponse.success(await service.overview(member.organization_id, project_id, range))
