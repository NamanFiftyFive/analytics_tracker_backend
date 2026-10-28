from fastapi import APIRouter, Depends, Header, status

from app.api.deps import get_ingest_service
from app.schemas.client_response import ClientResponse
from app.schemas.ingest import IngestBatch, IngestResult
from app.services.ingest_service import IngestService

# Called by SDKs inside customer apps and websites, not by logged-in users: authenticated with
# the project's API key. Browser support (CORS, sendBeacon) is in core/ingest_middleware.py.
router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post(
    "/batch",
    response_model=ClientResponse[IngestResult],
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_batch(
    batch: IngestBatch,
    x_api_key: str | None = Header(default=None, alias="X-API-Key", description="Project API key (pk_live_…)"),
    origin: str | None = Header(default=None, include_in_schema=False),
    service: IngestService = Depends(get_ingest_service),
):
    """Receive up to 100 events. Each event is checked on its own: invalid ones are listed in
    `rejected` and the rest are still stored. Re-sending an event with the same `id` is safe
    (counted in `duplicates`, stored once)."""
    result = await service.ingest(batch, x_api_key, origin)
    return ClientResponse.success(result, status.HTTP_202_ACCEPTED)
