# Backend: Analytics API (hackathon POC)

Multi-tenant product analytics SaaS (like Matomo): customer apps send usage events; orgs view dashboards and alerts.
Full docs: `README.md` (read only the section you need). Schema snapshot: `schema.sql` (auto-generated, don't edit).

## Stack and environment
- FastAPI + Python 3.14, **raw SQL via asyncpg** (no ORM, no SQLAlchemy/Alembic). Migrations: **dbmate**, plain `.sql`.
- **Local first**: Homebrew Postgres 14 on :5432, DB `hackathon_2026`, role `hackathon`.
- **Database**: Supabase (session pooler, settings in `.env`) for the hackathon; local Homebrew Postgres still works by switching `.env` back. Tests always use local Postgres.
- **Docker**: one container from `Dockerfile` (API + migrations + dbmate), no compose; DB stays outside. Old Docker volumes `analytics_pgdata14` / `hackathon_2026_pgdata` are unused; delete only if the user says so.
- `.env` lives in `backend/` (loaded by `app/core/config.py` via absolute path). `.env.example` has the same keys with placeholder secrets (keep in sync when adding settings).
- Run everything from `backend/` with the venv: `.venv/bin/python`, `.venv/bin/uvicorn app.main:app --reload`.
- nginx: user sets it up themselves from `~/Desktop/nginx_setup_guide.md`; don't configure it unless asked.

## Commands
- API: `.venv/bin/uvicorn app.main:app --reload` → http://localhost:8000/docs
- Migrations: `dbmate new <name>`, `dbmate up`, `dbmate rollback`, `dbmate status` (one table/change per file; never edit applied ones)
- Super admin: `.venv/bin/python -m scripts.create_superadmin <email> [--revoke]` (CLI only, no API)
- Docker: `docker build -t analytics-api .` + `docker run -d --name analytics_api --env-file .env -p 8000:8000 analytics-api` (README "Docker"). Migrations on Supabase: the user runs them themselves.
- Tests: `.venv/bin/pytest` (pytest + httpx in memory, DB `hackathon_2026_test`, truncated before each test; see README "Tests"). 197 tests, ~98% coverage, all green. Add tests with every feature.
- Type check: `npx --yes pyright --pythonpath .venv/bin/python app` (keep at 0 errors)
- Test on port **8001** (user's own server uses 8000); use `@demo-hack.io` test emails and delete them afterwards.

## Code layout (request flow, top to bottom)
`api/v1/endpoints/*.py` (HTTP only) → `services/*_service.py` (rules, `db.transaction()`) → `repositories/*_repository.py` (SQL with `$1` params) → `db/database.py` (`Database` class, asyncpg pool, `db` instance).
- Repositories are classes taking `conn: Executor = db` so the same SQL works inside a transaction.
- `schemas/` Pydantic models; `core/` config, security (argon2 + JWT), roles, exceptions, exception_handlers.

## Conventions (user preferences)
- **Guardrails** (`.claude/settings.json` + `.claude/hooks/guard.py`, changed by people only): blocked = editing/reading `.env` and keys, applied migrations, `schema.sql`, recursive force delete, force-push, `reset --hard`, `--no-verify`, destructive SQL / `dropdb`, `curl | sh`, `sudo`; asks a person = `git push`, `dbmate rollback`, deleting Docker volumes, new dependencies. After code edits, `pytest` must pass before finishing (Stop hook). If blocked, don't work around it: tell the user.
- **OOP**: classes for services, repositories, dependencies (e.g. `RequireRole`); avoid nested inner functions.
- **Response envelope** always: `ClientResponse.success(data, status)` → `{"status", "data"}`; errors raise `AppError` subclasses (`core/exceptions.py`) → `{"status", "error"}`. `status` = HTTP code.
- Explain *why* when making changes; the user is learning the stack. Do only the current step, then stop.
- Update `README.md` (structure tree, endpoints, diagrams) when adding features.

## Access model
- **Super admin** (`users.is_superadmin`, currently clashmini@gmail.com): `/admin/*`, full admin access in every org.
- **Orgs**: self-register via `POST /auth/register` or created via `POST /admin/organizations`. Can be suspended (`organizations.is_active`).
- **Org roles** viewer < analyst < admin (`core/roles.py`). Org routes use `Depends(RequireRole(Role.X))` on `/orgs/{org_id}/...`; non-members get 404.
- Org admins add/create member accounts via `POST /orgs/{org_id}/members`.
- Access token 15 min, refresh token 7 days (rotated, stored hashed). `get_current_user` reloads the user every request.

## Status
- Done: auth, orgs + members + roles, super admin API, response envelope, projects + API keys (`pk_live_…`, SHA-256 hashed, revoke not delete; `projects.allowed_origins`), Docker image (single container, DB outside), `POST /ingest/batch` (per-event validation, idempotent by event id, bulk `unnest` upserts into persons/events/sessions/event_definitions; `IngestCorsMiddleware` for browsers), 20 migrations.
- Flutter SDK done: `../event_tracker_analytics/` (FVM 3.47.0, Riverpod 3; see its README). Verified end-to-end against `/ingest/batch`.
- Test app: `../tracker_test_app/` sends to project "Tracker Test App" (org "One"). Ingest-path fix: SDK defers calls made during widget build.
- Mobile dashboard app: `../analytics_tracker/` (auth + bottom tabs done; see its CLAUDE.md).
- Search text goes through `repositories/search.py` `contains_pattern()` (escapes `%`/`_` for ILIKE).
- Insights + explorer APIs done (`/insights/overview`, `/events` with cursor, `/event-definitions`, `/persons`, `/persons/{id}`); days in project timezone.
- **Next**: alerts API → JS tracker `analytics.js` → insights queries, rollups, dashboards, alerts → Flutter admin app.
