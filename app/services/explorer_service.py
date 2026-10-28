import base64
import binascii
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.exceptions import BadRequestError, NotFoundError
from app.repositories.explorer_repository import ExplorerRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.explorer import (
    EventDefinitionOut,
    EventOut,
    EventPage,
    PersonCounts,
    PersonDetail,
    PersonFilter,
    PersonOut,
    PersonPage,
    PersonStats,
    SessionWithEvents,
)

NEW_USER_DAYS = 7


class EventCursor:
    """Opaque page marker for the event feed: the (time, id) of the last event shown,
    base64-encoded so clients treat it as a token."""

    @staticmethod
    def encode(occurred_at: datetime, event_id: UUID) -> str:
        return base64.urlsafe_b64encode(f"{occurred_at.isoformat()}|{event_id}".encode()).decode()

    @staticmethod
    def decode(cursor: str) -> tuple[datetime, UUID]:
        try:
            occurred_at, event_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
            return datetime.fromisoformat(occurred_at), UUID(event_id)
        except (ValueError, binascii.Error, UnicodeDecodeError):
            raise BadRequestError("Invalid cursor") from None


class ExplorerService:
    async def events(
        self,
        organization_id: UUID,
        project_id: UUID,
        *,
        event_name: str | None,
        person_id: UUID | None,
        search: str | None,
        cursor: str | None,
        limit: int,
    ) -> EventPage:
        await self._ensure_project(organization_id, project_id)
        rows = await ExplorerRepository().list_events(
            project_id,
            event_name=event_name or None,
            person_id=person_id,
            search=(search or "").strip() or None,
            before=EventCursor.decode(cursor) if cursor else None,
            limit=limit + 1,  # one extra tells us whether there is a next page
        )
        items = [EventOut(**dict(row)) for row in rows[:limit]]
        has_more = len(rows) > limit
        next_cursor = EventCursor.encode(items[-1].occurred_at, items[-1].id) if has_more else None
        return EventPage(items=items, next_cursor=next_cursor)

    async def definitions(self, organization_id: UUID, project_id: UUID) -> list[EventDefinitionOut]:
        await self._ensure_project(organization_id, project_id)
        rows = await ExplorerRepository().list_definitions(project_id)
        return [EventDefinitionOut(**dict(row)) for row in rows]

    async def persons(
        self,
        organization_id: UUID,
        project_id: UUID,
        *,
        person_filter: PersonFilter,
        search: str | None,
        limit: int,
        offset: int,
    ) -> PersonPage:
        await self._ensure_project(organization_id, project_id)
        repo = ExplorerRepository()
        new_since = datetime.now(UTC) - timedelta(days=NEW_USER_DAYS)
        rows = await repo.list_persons(
            project_id,
            person_filter=person_filter,
            search=(search or "").strip() or None,
            new_since=new_since,
            limit=limit,
            offset=offset,
        )
        counts = await repo.person_counts(project_id, new_since)
        return PersonPage(
            items=[PersonOut(**{k: v for k, v in dict(row).items() if k != "total"}) for row in rows],
            total=rows[0]["total"] if rows else 0,
            limit=limit,
            offset=offset,
            counts=PersonCounts(**dict(counts)),
        )

    async def person_detail(self, organization_id: UUID, project_id: UUID, person_id: UUID) -> PersonDetail:
        await self._ensure_project(organization_id, project_id)
        repo = ExplorerRepository()
        person = await repo.get_person(project_id, person_id)
        if person is None:
            raise NotFoundError("User not found")

        sessions = await repo.recent_sessions(person_id)
        events = await repo.events_for_sessions(project_id, [s["id"] for s in sessions]) if sessions else []
        by_session: dict[UUID, list[EventOut]] = {}
        for row in events:
            by_session.setdefault(row["session_id"], []).append(EventOut(**dict(row)))

        return PersonDetail(
            person=PersonOut(**dict(person)),
            stats=PersonStats(sessions=await repo.person_session_count(person_id), events=person["event_count"]),
            sessions=[SessionWithEvents(**dict(s), events=by_session.get(s["id"], [])) for s in sessions],
        )

    @staticmethod
    async def _ensure_project(organization_id: UUID, project_id: UUID) -> None:
        if not await ProjectRepository().exists(organization_id, project_id):
            raise NotFoundError("Project not found")
