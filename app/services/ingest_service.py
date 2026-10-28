from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import ValidationError

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import ApiKeyGenerator
from app.db.database import db
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.ingest_repository import (
    DefinitionRow,
    EventRow,
    IngestRepository,
    PersonRow,
    SessionRow,
)
from app.schemas.ingest import IngestBatch, IngestEvent, IngestResult, RejectedEvent

IDENTIFY_EVENT = "$identify"           # its properties are stored on the person
FUTURE_TOLERANCE = timedelta(minutes=10)  # device clocks a bit ahead are fine
MAX_EVENT_AGE = timedelta(days=31)        # SDK offline queues shouldn't hold events longer


class IngestService:
    async def ingest(self, batch: IngestBatch, header_key: str | None, origin: str | None) -> IngestResult:
        target = await self._resolve_target(header_key or batch.api_key, origin)
        events, rejected = self._validate_events(batch.events)

        accepted = 0
        if events:
            async with db.transaction() as conn:
                accepted = await self._store(IngestRepository(conn), target["project_id"], batch, events)

        await ApiKeyRepository().touch_last_used(target["key_id"])
        return IngestResult(accepted=accepted, duplicates=len(events) - accepted, rejected=rejected)

    # ── Checks ───────────────────────────────────────────────────────────────

    @staticmethod
    async def _resolve_target(api_key: str | None, origin: str | None) -> asyncpg.Record:
        """Which project the key sends to, after checking the key, the organization and the
        website origin (browsers only; apps send no Origin header)."""
        if not api_key:
            raise UnauthorizedError("API key required: send it in the X-API-Key header")
        target = await ApiKeyRepository().get_ingest_target(ApiKeyGenerator.hash(api_key))
        if target is None:
            raise UnauthorizedError("Invalid or revoked API key")
        if not target["organization_active"]:
            raise ForbiddenError("This organization is suspended")

        allowed = target["allowed_origins"]
        if origin and allowed and origin.strip().lower().rstrip("/") not in allowed:
            raise ForbiddenError("This website is not allowed to send events for this project")
        return target

    @staticmethod
    def _validate_events(raw_events: list[dict[str, Any]]) -> tuple[list[IngestEvent], list[RejectedEvent]]:
        """Each event on its own: bad ones are reported back, good ones are still stored."""
        now = datetime.now(UTC)
        valid: list[IngestEvent] = []
        rejected: list[RejectedEvent] = []

        for index, raw in enumerate(raw_events):
            try:
                event = IngestEvent.model_validate(raw)
            except ValidationError as exc:
                message = "; ".join(
                    f"{'.'.join(str(p) for p in err['loc']) or 'event'}: {err['msg']}" for err in exc.errors()
                )
                rejected.append(RejectedEvent(index=index, error=message))
                continue

            if event.timestamp < now - MAX_EVENT_AGE:
                rejected.append(RejectedEvent(index=index, error="timestamp: older than 31 days"))
                continue
            if event.timestamp > now + FUTURE_TOLERANCE:
                # Phone clock is wrong; keep the event but use the time we received it.
                event.timestamp = now
            valid.append(event)

        return valid, rejected

    # ── Storage ──────────────────────────────────────────────────────────────

    async def _store(
        self, repo: IngestRepository, project_id: UUID, batch: IngestBatch, events: list[IngestEvent]
    ) -> int:
        """Order matters: persons first (events need person_id), then events (to learn which
        ones are new), then sessions and definitions from the NEW events only, so a retried
        batch doesn't count anything twice. Returns how many events were new."""
        unique: dict[UUID, IngestEvent] = {}
        for event in events:
            unique.setdefault(event.id, event)  # same id twice in one batch: keep the first
        events = list(unique.values())

        person_ids = await repo.upsert_persons(project_id, self._persons(events))

        rows = [self._event_row(e, person_ids.get(e.distinct_id)) for e in events]
        inserted_ids = await repo.insert_events(project_id, batch.context, rows)
        new_events = [e for e in events if e.id in inserted_ids]

        if new_events:
            sessions = self._sessions(new_events, person_ids)
            if sessions:
                await repo.upsert_sessions(project_id, batch.context, sessions)
            await repo.upsert_definitions(project_id, self._definitions(new_events))
        return len(new_events)

    @staticmethod
    def _event_row(event: IngestEvent, person_id: UUID | None) -> EventRow:
        properties = dict(event.properties)
        for key in ("referrer", "utm_source", "utm_medium", "utm_campaign"):
            value = getattr(event, key)
            if value:
                properties[f"${key}"] = value
        return EventRow(
            id=event.id,
            event_name=event.event,
            distinct_id=event.distinct_id,
            session_id=event.session_id,
            occurred_at=event.timestamp,
            path=event.path,
            screen_name=event.screen_name,
            properties=properties,
            person_id=person_id,
        )

    @staticmethod
    def _persons(events: list[IngestEvent]) -> list[PersonRow]:
        """One row per distinct_id: earliest and latest time seen, plus $identify traits."""
        persons: dict[str, PersonRow] = {}
        for event in sorted(events, key=lambda e: e.timestamp):
            person = persons.setdefault(
                event.distinct_id, PersonRow(event.distinct_id, event.timestamp, event.timestamp)
            )
            person.last_seen_at = event.timestamp
            if event.event == IDENTIFY_EVENT:
                person.properties.update(event.properties)
        return list(persons.values())

    @staticmethod
    def _sessions(events: list[IngestEvent], person_ids: dict[str, UUID]) -> list[SessionRow]:
        """One row per session_id: time range, event count, first and last page/screen."""
        grouped: dict[UUID, list[IngestEvent]] = {}
        for event in events:
            if event.session_id is not None:
                grouped.setdefault(event.session_id, []).append(event)

        sessions = []
        for session_id, items in grouped.items():
            items.sort(key=lambda e: e.timestamp)
            first, last = items[0], items[-1]
            sessions.append(
                SessionRow(
                    id=session_id,
                    person_id=person_ids.get(last.distinct_id),
                    started_at=first.timestamp,
                    ended_at=last.timestamp,
                    event_count=len(items),
                    entry_path=first.path or first.screen_name,
                    exit_path=last.path or last.screen_name,
                    referrer=first.referrer,
                    utm_source=first.utm_source,
                    utm_medium=first.utm_medium,
                    utm_campaign=first.utm_campaign,
                )
            )
        return sessions

    @staticmethod
    def _definitions(events: list[IngestEvent]) -> list[DefinitionRow]:
        definitions: dict[str, DefinitionRow] = {}
        for event in events:
            current = definitions.get(event.event)
            if current is None:
                definitions[event.event] = DefinitionRow(event.event, event.timestamp, event.timestamp)
            else:
                current.first_seen_at = min(current.first_seen_at, event.timestamp)
                current.last_seen_at = max(current.last_seen_at, event.timestamp)
        return list(definitions.values())
