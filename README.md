# Backend: Analytics API

FastAPI + PostgreSQL with **raw SQL** (asyncpg, no ORM) and **dbmate** migrations.
Runs locally (Homebrew Postgres + venv) or fully in Docker; see "Docker" at the end.

> Every command in this file is run from the `backend/` folder, where `.env` lives.
>
> ```bash
> cd ~/Desktop/hackathon_2026/backend
> ```

---

## Project structure

```
backend/
├── .env                      # settings and secrets (git-ignored), see "Environment variables"
├── .env.example              # same keys with placeholder secrets: copy to .env on a new machine
├── requirements.txt          # Python packages
├── requirements-dev.txt      # + test tools (pytest, pytest-asyncio, httpx, pytest-cov); not in the Docker image
├── pytest.ini                # test settings, see "Tests"
├── schema.sql                # AUTO-GENERATED snapshot of the whole DB schema (don't edit)
├── Dockerfile                # API image (code + packages + migrations + dbmate), see "Docker"
├── .dockerignore             # keeps .env, .venv and docs out of the image
├── docker-compose.yml        # whole stack in Docker: db + migrate + api, see "Docker"
├── scripts/
│   ├── create_superadmin.py  # make a user the platform super admin (CLI only)
│   └── copy_local_db_to_docker.sh  # copy all data from local Postgres into the Docker one
├── tests/                    # pytest, against the separate hackathon_2026_test database
│   ├── conftest.py           # test DB setup (migrate, empty before each test), client fixture
│   ├── helpers.py            # AuthActions (register, login), OrgActions, ProjectActions
│   ├── unit/                 # pure functions: security, roles, response envelope (no HTTP)
│   └── api/                  # endpoints called in memory through the real app
├── migrations/               # schema changes as plain SQL, one file per table (dbmate)
│   ├── 20261017100000_create_types_and_helpers.sql
│   ├── 20261017100100_create_organizations.sql
│   ├── ...
│   └── 20261017101600_create_alert_history.sql
└── app/
    ├── main.py               # creates the FastAPI app, opens/closes the DB pool, registers routes
    ├── api/
    │   ├── deps.py           # get_current_user, RequireRole (org role), require_superadmin
    │   └── v1/
    │       ├── router.py     # collects all v1 routers under /api/v1
    │       └── endpoints/    # HTTP layer: one file per feature
    │           ├── health.py
    │           ├── auth.py
    │           ├── organizations.py
    │           ├── projects.py
    │           ├── api_keys.py
    │           ├── ingest.py  # POST /ingest/batch (SDKs, API-key auth)
    │           ├── insights.py  # GET .../insights/overview
    │           └── explorer.py  # GET .../events, event-definitions, persons
    │           └── admin.py   # super admin API (/admin/...)
    ├── services/             # business rules (what is allowed, what happens in which order)
    │   ├── auth_service.py
    │   ├── organization_service.py
    │   ├── user_service.py   # get_or_create user (shared)
    │   ├── project_service.py
    │   ├── api_key_service.py
    │   ├── ingest_service.py  # validate events, build persons/sessions/definitions
    │   ├── insights_service.py  # overview: time windows in project timezone, % change
    │   └── explorer_service.py  # event feed (cursor), event names, persons, timeline
    │   └── admin_service.py  # super admin operations
    ├── repositories/         # raw SQL queries, one class per table area
    │   ├── user_repository.py
    │   ├── organization_repository.py
    │   ├── refresh_token_repository.py
    │   ├── project_repository.py
    │   ├── api_key_repository.py
    │   ├── ingest_repository.py  # bulk upserts with unnest(), one statement per table
    │   ├── insights_repository.py  # aggregates over events / sessions
    │   ├── explorer_repository.py  # event feed, definitions, persons, sessions
    │   └── stats_repository.py   # platform totals for /admin/stats
    ├── schemas/              # Pydantic models: request validation and response shapes
    │   ├── auth.py
    │   ├── organization.py
    │   ├── project.py        # projects + API keys (timezone / origin validation)
    │   ├── ingest.py         # IngestBatch / IngestEvent / IngestResult
    │   ├── admin.py
    │   ├── pagination.py     # Page[T]: items, total, limit, offset
    │   └── client_response.py  # ClientResponse: {status, data} or {status, error}
    ├── core/
    │   ├── config.py         # Settings class: loads backend/.env
    │   ├── security.py       # PasswordService (argon2), TokenService (JWT), ApiKeyGenerator
    │   ├── roles.py          # Role enum: viewer < analyst < admin
    │   ├── exceptions.py     # error classes only: AppError, NotFoundError, ConflictError, ...
    │   ├── exception_handlers.py  # turns every error into a ClientResponse error body
    │   └── ingest_middleware.py   # CORS + sendBeacon + body limit for /ingest only
    └── db/
        └── database.py       # Database class: asyncpg pool + fetch/fetchrow/execute/transaction
```

### How the modules are connected

Each layer only calls the layer directly below it. Arrows point from the caller to what it uses.

```
  backend/.env ──▶ core/config.py ─────────── settings, read once at startup, used by every layer

  app/main.py      startup: db.connect()  ·  register_exception_handlers()  ·  mounts /api/v1
       │
       ▼
  api/v1/router.py                    collects every endpoint file under /api/v1
       │
       ▼
  ┌───────────────────────────────┐   validates input with  ┌────────────────────────────┐
  │ api/v1/endpoints/*.py         │────────────────────────▶│ schemas/*.py               │
  │ routes: HTTP in, HTTP out     │   wraps output in       │ schemas/client_response.py │
  └───────────────┬───────────────┘                         └────────────────────────────┘
                  │  Depends(...) ─────────────────────────▶ api/deps.py   reads the Bearer token
                  ▼
  ┌───────────────────────────────┐   hashing, JWT          ┌────────────────────────────┐
  │ services/*_service.py         │────────────────────────▶│ core/security.py           │
  │ business rules, transactions  │   raises errors from    │ core/exceptions.py         │
  └───────────────┬───────────────┘                         └────────────────────────────┘
                  │
                  ▼
  ┌───────────────────────────────┐
  │ repositories/*_repository.py  │   raw SQL with $1, $2 parameters
  └───────────────┬───────────────┘
                  ▼
  ┌───────────────────────────────┐
  │ db/database.py                │   Database class: asyncpg connection pool
  └───────────────┬───────────────┘
                  ▼
     PostgreSQL  hackathon_2026   ◀── tables created by migrations/*.sql  (dbmate up)
```

### How data flows through one request (login)

The request goes down the layers; the result comes back up and is wrapped once at the top.

```
  REQUEST                                                     RESPONSE
  POST /api/v1/auth/login                                     200 {"status": 200,
  {"email": "...", "password": "..."}                              "data": {"access_token": "...", ...}}
        │                                                                 ▲
        ▼                                                                 │
  endpoints/auth.py         validate body (LoginRequest)     ClientResponse.success(tokens)
        │                                                                 ▲
        ▼                                                                 │
  services/auth_service.py  check password, issue tokens     returns TokenResponse
        │                                                                 ▲
        ▼                                                                 │
  repositories/             SELECT ... FROM users            returns the row (Record)
  user_repository.py        WHERE lower(email) = lower($1)                ▲
        │                                                                 │
        ▼                                                                 │
  db/database.py ──▶ borrow pooled connection ──▶ PostgreSQL ──▶ row ─────┘
```

When something goes wrong in any layer, the error skips the rest of the path and goes to
`core/exception_handlers.py`, which sends `{"status": ..., "error": ...}`:

| Raised where | Error | Handler | Response |
|---|---|---|---|
| Endpoints, before your code runs | Bad or missing fields, invalid JSON | `validation_error_handler` | 422 |
| Services, `api/deps.py` | `AppError` subclasses | `app_error_handler` | 401, 403, 404, 409 … |
| FastAPI routing | Unknown URL, wrong method | `http_error_handler` | 404, 405 |
| Anywhere | Unexpected bug | `unexpected_error_handler` | 500 (details only in the server log) |

Example, wrong password: `auth_service` raises `UnauthorizedError` → `app_error_handler` →
`401 {"status": 401, "error": "Incorrect email or password"}`.

### Adding a new feature (e.g. projects)

1. `migrations/`: add the table change if one is needed (`dbmate new ...`)
2. `repositories/project_repository.py`: the SQL queries
3. `services/project_service.py`: the rules
4. `schemas/project.py`: request and response models
5. `api/v1/endpoints/projects.py`: the routes
6. `api/v1/router.py`: `api_router.include_router(projects.router)`

---

## First-time setup

Needs Homebrew PostgreSQL running on port 5432 and dbmate.

```bash
# 1. tools
brew install dbmate

# 2. database role and database
psql -h localhost -d postgres -c "CREATE ROLE hackathon LOGIN PASSWORD '<password>'"
psql -h localhost -d postgres -c "CREATE DATABASE hackathon_2026 OWNER hackathon"

# 3. create backend/.env (see the table below)

# 4. Python environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 5. create the tables
dbmate up
```

VS Code: Command Palette → **Python: Select Interpreter** → `.venv/bin/python`.

---

## Environment variables (`backend/.env`)

Loaded by `app/core/config.py` (FastAPI) and by dbmate. Restart the API after changing it.

| Variable | Required | Example / notes |
|---|---|---|
| `POSTGRES_USER` | yes | `hackathon` |
| `POSTGRES_PASSWORD` | yes | your password |
| `POSTGRES_DB` | yes | `hackathon_2026` |
| `POSTGRES_HOST` | no | `localhost` (default) |
| `POSTGRES_PORT` | no | `5432` (default) |
| `DB_POOL_MIN_SIZE`, `DB_POOL_MAX_SIZE` | no | `2`, `20` (defaults) |
| `JWT_SECRET_KEY` | yes | generate: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `JWT_ALGORITHM` | no | `HS256` (default) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `15` (default) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | no | `7` (default) |
| `CORS_ORIGINS` | no | `'["http://localhost:3000","http://localhost:8080"]'` |
| `APP_NAME`, `ENVIRONMENT`, `DEBUG` | no | `"Analytics API"`, `local`, `true` |
| `DATABASE_URL` | for dbmate | `"postgres://hackathon:<password>@localhost:5432/hackathon_2026?sslmode=disable"` |
| `DBMATE_MIGRATIONS_DIR` | for dbmate | `"migrations"` |
| `DBMATE_SCHEMA_FILE` | for dbmate | `"schema.sql"` |

Check what the app actually loaded:

```bash
.venv/bin/python -c "from app.core.config import settings; print(settings.POSTGRES_DB, settings.POSTGRES_PORT, settings.DEBUG)"
```

---

## Run the API

```bash
.venv/bin/uvicorn app.main:app --reload            # http://localhost:8000
.venv/bin/uvicorn app.main:app --reload --port 8001  # another port
```

| URL | What |
|---|---|
| http://localhost:8000/docs | Interactive API docs (Swagger) |
| http://localhost:8000/api/v1/health | API is up |
| http://localhost:8000/api/v1/health/db | API can reach Postgres |

Stop with `Ctrl+C`. If port 8000 is stuck: `lsof -ti :8000 | xargs kill`.

---

## Response format

Every response uses one of two shapes; `status` always equals the HTTP status code.

```json
{"status": 200, "data": { ... }}
{"status": 409, "error": "An account with this email already exists"}
```

| Case | Example |
|---|---|
| Success | `{"status": 201, "data": {"access_token": "...", ...}}` |
| Success with nothing to return | `{"status": 200, "data": null}` |
| Business error (`AppError` subclasses) | `{"status": 401, "error": "Incorrect email or password"}` |
| Validation (bad / missing fields) | `{"status": 422, "error": "email: value is not a valid email address; password: Field required"}` |
| Invalid JSON body | `{"status": 422, "error": "Request body is not valid JSON"}` |
| Unknown URL / wrong method | `{"status": 404, "error": "Not Found"}`, `{"status": 405, "error": "Method Not Allowed"}` |
| Unexpected crash | `{"status": 500, "error": "Internal server error"}` (details only in the server log) |

Both shapes come from one class, `ClientResponse` (`app/schemas/client_response.py`), with fields
`status`, `data` and `error`; the unused one is left out of the JSON. In endpoints, return
`ClientResponse.success(...)` and raise `AppError` subclasses for errors:

```python
from app.schemas.client_response import ClientResponse
from app.core.exceptions import NotFoundError

@router.get("/projects/{project_id}", response_model=ClientResponse[ProjectOut])
async def get_project(project_id: UUID):
    project = await ProjectRepository().get(project_id)
    if project is None:
        raise NotFoundError("Project not found")       # → {"status": 404, "error": "Project not found"}
    return ClientResponse.success(ProjectOut(**dict(project)))   # → {"status": 200, "data": {...}}

@router.post("/projects", response_model=ClientResponse[ProjectOut], status_code=201)
async def create_project(...):
    return ClientResponse.success(project, 201)         # status must match the route's status_code
```

Error classes in `app/core/exceptions.py`: `BadRequestError` (400), `UnauthorizedError` (401),
`ForbiddenError` (403), `NotFoundError` (404), `ConflictError` (409), `ServiceUnavailableError` (503).
To add one, subclass `AppError` and set `status_code`. Handlers for each error type are plain functions in
`app/core/exception_handlers.py`, listed in `EXCEPTION_HANDLERS`.

---

## API endpoints

All under `/api/v1`.

| Method | Path | Auth | What it does |
|---|---|---|---|
| GET | `/health` | no | Liveness check |
| GET | `/health/db` | no | Database check (returns Postgres version) |
| POST | `/auth/register` | no | Create user + organization; user becomes **admin**; returns tokens |
| POST | `/auth/login` | no | Email + password → access token (15 min) + refresh token (7 days) |
| POST | `/auth/refresh` | no | Refresh token → new token pair (old refresh token stops working) |
| POST | `/auth/logout` | no | Revoke a refresh token (`data` is `null`) |
| GET | `/auth/me` | Bearer | Current user + their organizations and roles |
| GET | `/orgs` | Bearer | Organizations the user belongs to, with their role in each |
| GET | `/orgs/{org_id}` | viewer+ | Organization details + `your_role` |
| GET | `/orgs/{org_id}/members` | viewer+ | Members with email, role and join date |
| POST | `/orgs/{org_id}/members` | admin | Add a user by email + role. If the email has no account, it is **created** with `full_name` and `password` (required then) |
| PATCH | `/orgs/{org_id}/members/{user_id}` | admin | Change a member's role: `{"role": "admin"}` |
| DELETE | `/orgs/{org_id}/members/{user_id}` | admin, or self | Remove a member; any member can remove themselves (leave) |

"viewer+" means viewer, analyst or admin. A user who is not a member of the organization gets
`404 Organization not found` (same as for an id that doesn't exist). An organization always keeps at
least one admin: demoting or removing the last admin returns `409`. Members of a **suspended**
organization get `403 This organization is suspended`.

Projects (one tracked app or website) and their API keys:

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/orgs/{org_id}/projects` | viewer+ | List projects (with `active_api_keys` count) |
| POST | `/orgs/{org_id}/projects` | admin | Create `{name, platform, timezone, allowed_origins}`; also creates a first key, returned once in `data.api_key.key` |
| GET | `/orgs/{org_id}/projects/{project_id}` | viewer+ | One project |
| PATCH | `/orgs/{org_id}/projects/{project_id}` | admin | Change name, platform, timezone, `allowed_origins` (replaces the list) |
| DELETE | `/orgs/{org_id}/projects/{project_id}` | admin | Delete the project **and all its data** (keys, events, sessions, stats, dashboards, alerts) |
| GET | `/orgs/{org_id}/projects/{project_id}/api-keys` | admin | List keys: name + visible prefix only |
| POST | `/orgs/{org_id}/projects/{project_id}/api-keys` | admin | New key `{name}`; full key returned **only once** in `data.key` |
| DELETE | `/orgs/{org_id}/projects/{project_id}/api-keys/{key_id}` | admin | Revoke: stops working immediately, stays listed |

- `platform`: `web`, `ios`, `android`, `flutter`, `other`. `timezone`: IANA name (`Asia/Kolkata`), used for daily charts.
- `allowed_origins`: websites allowed to send events, e.g. `https://cars.example.com` (normalized to lowercase,
  no trailing slash). Empty = any. Mobile apps aren't affected.
- Keys look like `pk_live_…`. Only a SHA-256 hash is stored, so a lost key can't be recovered: create a new one and
  revoke the old one. Keys are write-only (they will only be able to *send* events).

Event ingestion (called by SDKs inside customer apps and websites, **not** by logged-in users):

| Method | Path | Auth | What it does |
|---|---|---|---|
| POST | `/ingest/batch` | project API key: `X-API-Key` header, or `api_key` in the body (sendBeacon) | Receive 1–100 events → `202 {"accepted", "duplicates", "rejected": [{index, error}]}` |

```json
{
  "context": {"platform": "flutter", "os": "Android 14", "device_type": "mobile", "app_version": "2.3.1", "country": "IN"},
  "events": [
    {"id": "<uuid from the SDK>", "event": "test_drive_booked", "distinct_id": "anon-7f3a",
     "session_id": "<uuid>", "timestamp": "2026-10-20T10:16:30Z", "screen_name": "BookTestDrive",
     "properties": {"model": "Nexon EV"}}
  ]
}
```

- Event fields: `id`, `event`, `distinct_id`, `timestamp` required; optional `session_id`, `path`, `screen_name`,
  `referrer`, `utm_source`, `utm_medium`, `utm_campaign`, `properties` (≤ 16 KB). Unknown fields are ignored.
- **Each event is checked on its own**: bad ones come back in `rejected` with their index; the rest are stored.
- **Retries are safe**: an event `id` already stored is skipped and counted in `duplicates` (also within one batch).
- Timestamps without offset are UTC; more than 10 min in the future → server time; older than 31 days → rejected.
- `$identify` events: their `properties` are merged into the person's properties.
- One transaction per batch: `persons` (first/last seen), `events` (monthly partition), `sessions` (start, end,
  count, entry/exit page, utm, device), `event_definitions`; then `api_keys.last_used_at` (at most once a minute).
- Errors: `401` missing/invalid/revoked key, `403` suspended organization or website not in `allowed_origins`,
  `413` body over 1 MB, `422` batch shape (0 or > 100 events, bad `context`).
- Browsers: `core/ingest_middleware.py` allows any website to call `/ingest/*` (CORS, preflight), accepts
  `Content-Type: text/plain` (sendBeacon) and rejects bodies over 1 MB. Other routes keep the normal CORS rules.

Analytics (read-only, viewer+). Paths start with `/orgs/{org_id}/projects/{project_id}`:

| Method | Path | What it returns |
|---|---|---|
| GET | `.../insights/overview?range=today\|7d\|30d\|90d` | KPIs (active users, events, sessions, avg session) each with `previous` (same hours one period earlier: today at 10:00 vs yesterday 00:00–10:00) + `change_percent`, `events_per_day` (every day incl. zeros), `top_screens`, `top_events` (custom events only) |
| GET | `.../events?event=&person_id=&search=&cursor=&limit=50` | Newest events first; `next_cursor` loads older ones (keyset paging, stable while new events arrive). `search` matches user id, screen or property text |
| GET | `.../event-definitions` | Every event name seen, most recent first (filter chips) |
| GET | `.../persons?filter=all\|identified\|new&search=&limit=&offset=` | Users, most recently active first, with `event_count`, `last_os`, `total` and `counts` for each filter. `new` = first seen in 7 days |
| GET | `.../persons/{person_id}` | One user: traits, `stats` (sessions, events), 5 most recent sessions with up to 100 events each |

Days are counted in the **project's timezone** ("today" = the project's today). Each range is compared with the
period of the same length just before it; `change_percent` is null when that period had 0.
These read the raw `events` / `sessions` tables for now; the rollup tables can replace them later without API changes.

Super admin only (`403 Super admin access required` for everyone else):

| Method | Path | What it does |
|---|---|---|
| GET | `/admin/stats` | Platform totals: organizations, users, projects, events today |
| GET | `/admin/organizations?search=&limit=50&offset=0` | All organizations with member / project counts (paged) |
| POST | `/admin/organizations` | Create an organization + its first admin (existing account, or new with `admin_password`) |
| GET | `/admin/organizations/{org_id}` | Organization details + members |
| PATCH | `/admin/organizations/{org_id}` | Rename, change `plan` (free / pro / enterprise), suspend with `is_active: false` |
| GET | `/admin/users?search=&limit=50&offset=0` | All users with how many organizations each is in (paged) |
| PATCH | `/admin/users/{user_id}` | `is_active: false` disables the account and logs it out everywhere |

Paged lists return `{"items": [...], "total": 120, "limit": 50, "offset": 0}` inside `data`.

### Try auth in /docs

1. **POST /auth/register** → copy `data.access_token` from the response
2. Click **Authorize** (top right) → paste the token → Authorize
3. **GET /auth/me**

### Try auth with curl

```bash
curl -s -X POST localhost:8000/api/v1/auth/register -H "Content-Type: application/json" \
  -d '{"email":"me@example.com","password":"supersecret1","full_name":"Me","organization_name":"My Org"}'

curl -s -X POST localhost:8000/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"email":"me@example.com","password":"supersecret1"}'

curl -s localhost:8000/api/v1/auth/me -H "Authorization: Bearer <access_token>"
```

---

## Roles and permissions

There are two levels:

```
Super admin (platform owner)       users.is_superadmin = true; created only with scripts/create_superadmin.py
   │  manages every organization and user via /admin/..., and acts as admin inside any organization
   ▼
Organizations (customers)          self-register with POST /auth/register, or created by the super admin
   └── members: admin / analyst / viewer   added by the org's admin with POST /orgs/{org_id}/members
```

| Who is created | How |
|---|---|
| Super admin | `.venv/bin/python -m scripts.create_superadmin you@example.com` (`--revoke` to remove) |
| Organization + its first admin | `POST /auth/register` (public) or `POST /admin/organizations` (super admin) |
| Members of an organization | `POST /orgs/{org_id}/members` by that organization's admin |

Organization roles are per organization (`organization_members.role`) and ranked **viewer < analyst < admin**;
a higher role can do everything a lower one can. `app/core/roles.py` defines them.

| Role | Can do |
|---|---|
| viewer | Read the organization, its members (and later: dashboards, alert history) |
| analyst | Everything a viewer can (later: create dashboards, widgets and alert rules) |
| admin | Everything, plus manage members and roles (later: projects and API keys) |

Protect a route that has `{org_id}` in its path with `RequireRole` from `app/api/deps.py`:

```python
from app.api.deps import RequireRole
from app.core.roles import Role
from app.schemas.organization import CurrentMember

@router.post("/orgs/{org_id}/projects")
async def create_project(member: CurrentMember = Depends(RequireRole(Role.ADMIN))):
    # Only reached if the logged-in user is an admin of org_id.
    # member.organization_id, member.user_id and member.role are available here.
    ...
```

`RequireRole` returns `401` without a valid token, `404` if the user is not a member of the
organization, `403` if their role is too low or the organization is suspended. Super admins always
pass (as `admin`, with `member.is_superadmin = True`). For platform-wide routes use
`Depends(require_superadmin)`.

Every authenticated request reloads the user from the database (`get_current_user`), so a
deactivated account stops working immediately, even with an unexpired access token.

---

## Database access (raw SQL)

`app/db/database.py` defines the `Database` class; the app uses one shared instance, `db`.
Parameters always use `$1, $2` placeholders (never f-strings with user input).

```python
from app.db.database import db

row  = await db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)       # one row or None
rows = await db.fetch("SELECT * FROM projects WHERE organization_id = $1", org_id)  # list
val  = await db.fetchval("SELECT count(*) FROM users")                       # single value
await db.execute("UPDATE users SET last_login_at = now() WHERE id = $1", user_id)
await db.executemany("INSERT INTO t (a, b) VALUES ($1, $2)", [(1, 2), (3, 4)])
await db.copy_records("events", records, columns=[...])                     # fast bulk insert

async with db.transaction() as conn:   # several writes: all succeed or all are undone
    await conn.execute(...)
    await conn.execute(...)
```

Repositories take either `db` or a transaction connection:

```python
UserRepository()            # each query on its own pooled connection
UserRepository(conn)        # inside `async with db.transaction() as conn:`
```

---

## Migrations (dbmate)

Schema changes are plain `.sql` files in `migrations/`, applied in timestamp order.
Each file has two sections:

```sql
-- migrate:up
ALTER TABLE users ADD COLUMN avatar_url text;

-- migrate:down
ALTER TABLE users DROP COLUMN avatar_url;
```

| Command | What it does |
|---|---|
| `dbmate status` | List migrations: `[X]` applied, `[ ]` pending |
| `dbmate new add_avatar_to_users` | Create a new empty migration file with a timestamp |
| `dbmate up` | Apply all pending migrations |
| `dbmate rollback` | Undo the most recent migration (runs its `migrate:down`) |
| `dbmate dump` | Rewrite `schema.sql` from the current database |

Rules:
- Never edit a migration that has already been applied; add a new one.
- A file you create by hand must be named `YYYYMMDDHHMMSS_name.sql` with a timestamp later than the last file.
- Only structure changes (`CREATE` / `ALTER` / `DROP`) go in `migrations/`. One-off data scripts run with
  `psql -f` or the pgAdmin Query Tool, and live outside this folder.
- `schema.sql` is regenerated after every `up` / `rollback`; don't edit it.

### Tables

| Area | Tables |
|---|---|
| Tenancy & auth | `organizations`, `users`, `organization_members`, `refresh_tokens`, `projects`, `api_keys` |
| Tracking | `persons`, `sessions`, `events` (monthly partitions + `events_default`), `event_definitions` |
| Rollups | `event_daily_stats`, `project_daily_stats` |
| Dashboards & alerts | `dashboards`, `widgets`, `alert_rules`, `alert_history` |

Database functions (defined in migrations, live inside Postgres):
- `set_updated_at()`: trigger that keeps `updated_at` current on `dashboards` and `widgets`
- `create_events_partition(date)`: creates a month's events table, e.g. `SELECT create_events_partition('2027-01-01');`

---

## PostgreSQL

### pgAdmin 4

| Field | Value |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Maintenance database | `hackathon_2026` |
| Username | `hackathon` |
| Password | `POSTGRES_PASSWORD` from `.env` |

Tables: `hackathon_2026` → Schemas → public → Tables. Functions: → Functions.

### psql

```bash
psql -h localhost -U hackathon -d hackathon_2026          # interactive shell (\dt lists tables, \q quits)
psql -h localhost -U hackathon -d hackathon_2026 -c "SELECT count(*) FROM users"
psql -h localhost -U hackathon -d hackathon_2026 -f path/to/script.sql
```

### Homebrew Postgres service

```bash
brew services list                      # is postgresql@14 running?
brew services start postgresql@14
brew services restart postgresql@14
```

---

## Packages

```bash
.venv/bin/pip install -r requirements.txt     # after requirements.txt changes
.venv/bin/pip install <package>               # then add it to requirements.txt
.venv/bin/pip list                            # what's installed
```

| Package | Used for |
|---|---|
| `fastapi`, `uvicorn[standard]` | Web framework and server |
| `pydantic-settings` | Loading `.env` into `Settings` |
| `asyncpg` | PostgreSQL driver and connection pool |
| `pyjwt` | Access tokens |
| `argon2-cffi` | Password hashing |
| `email-validator` | Email validation in request models |
| `pytest`, `pytest-asyncio`, `httpx`, `pytest-cov` | Tests only (`requirements-dev.txt`) |

---

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt   # once
.venv/bin/pytest                                # everything (~2 s)
.venv/bin/pytest tests/api/test_auth.py         # one file
.venv/bin/pytest -k refresh                     # tests whose name contains "refresh"
.venv/bin/pytest --cov=app --cov-report=term-missing   # which lines no test runs (~98% covered)
```

Each bug found by these tests now has a test that guards the fix (Oct 2026): retried events from a fast
device clock stored twice (`test_ingest.py`), `range=today` compared with the wrong hours (`test_insights.py`),
`%` / `_` acting as wildcards in searches (`test_explorer.py`, `test_admin.py`, `tests/unit/test_search.py`).

- **Separate database.** Tests use `hackathon_2026_test`, never `hackathon_2026`. `tests/conftest.py`
  sets `POSTGRES_DB` before the app loads, and refuses to run if the name doesn't end in `_test`.
- **Always the current schema.** Each run starts with `dbmate up` on the test database, using the same migrations.
- **Each test starts empty.** Every table is truncated before each test, so tests don't depend on each other.
- **No server needed.** `httpx` calls the app in memory (`ASGITransport`), with the real middleware and
  error handlers; nothing listens on 8000 or 8001.
- Create the test database once on a new machine (the `hackathon` role can't create databases):
  `createdb -h localhost -O hackathon hackathon_2026_test`

| Folder | What it tests |
|---|---|
| `tests/unit/` | `PasswordService`, `TokenService`, `ApiKeyGenerator`, `Role.at_least`, `ClientResponse` |
| `tests/api/` | `/health`, `/auth/*` (register, login, me, refresh rotation, logout, disabled accounts) |
| `tests/api/test_organizations.py` | `/orgs/*`: role checks per route, 404 for non-members, suspended orgs, super admin, add/change/remove members, last-admin rule |
| `tests/api/test_projects.py` | projects + API keys: first key works, only hashes stored, validation, admin-only changes, other orgs' projects unreachable, delete removes data, revoked keys stop at once |
| `tests/api/test_ingest.py` | `/ingest/batch`: storing with device context, persons/sessions/definitions, retries and duplicates, per-event rejection, time limits, API key + origin checks, browser CORS / sendBeacon / 1 MB limit |
| `tests/api/test_insights.py` | overview KPIs, previous period, days in the project timezone, top screens/events (fixed "now", rows written directly) |
| `tests/api/test_explorer.py` | event feed (filters, search, cursor paging), event names, users list (filters, counts, paging), user detail |
| `tests/api/test_admin.py` | `/admin/*`: super admin only, stats, organizations (create, suspend, plan), users (deactivate logs out everywhere) |
| `tests/api/test_errors.py` | invalid JSON, deleted user's token, database down (503), unexpected bug (500 without details) |

---

## Type checking

Same checker as VS Code's Pylance:

```bash
npx --yes pyright --pythonpath .venv/bin/python app
```

---

## Docker

The whole stack runs from `backend/docker-compose.yml`, so run the commands from `backend/` like everything else.
It reads the same `.env`; compose only overrides what differs inside Docker (database host).

```
docker compose up
   │
   ├─ db        postgres:14-alpine, host port 5433 ──▶ volume "analytics_pgdata14" (the data)
   │              │ healthy
   ├─ migrate   analytics-api image, runs `dbmate up`, then exits
   │              │ finished OK
   └─ api       analytics-api image, uvicorn on host port 8000
```

| What | Where it lives | Survives rebuild / `down`? |
|---|---|---|
| Code, packages, migrations | the `analytics-api` image (built from `backend/Dockerfile`) | rebuilt with `--build` |
| Database files | the `analytics_pgdata14` volume | ✅ yes; only `down -v` or `docker volume rm` deletes it |
| Secrets (`.env`) | your machine only; never in the image | — |

```bash
cd ~/Desktop/hackathon_2026/backend

docker compose up -d --build          # build + start db, migrations, api  → http://localhost:8000/docs
docker compose ps -a                  # status (migrate shows "exited (0)" = migrations done)
docker compose logs -f api            # follow API logs
docker compose down                   # stop and remove containers (data is kept)

docker compose exec api python -m scripts.create_superadmin you@example.com   # super admin in Docker
docker compose exec db psql -U hackathon -d hackathon_2026                    # SQL shell in Docker
```

Stop your local uvicorn first: both use port 8000. The Docker database is on **5433**
(pgAdmin: `localhost:5433`), so it never touches the Homebrew one on 5432.

**Just the API image, with your local Postgres** (no compose, no database container):

```bash
docker build -t analytics-api .
docker run -d --name analytics_api --env-file .env \
  -e POSTGRES_HOST=host.docker.internal -p 8000:8000 analytics-api
docker logs -f analytics_api          # logs
docker rm -f analytics_api            # stop and remove
```

`host.docker.internal` is how a container reaches your Mac (`localhost` inside it means the container
itself). `docker run --env-file` passes values exactly as written, quotes included, so keep `.env`
values unquoted.

**New migration:** create it locally as usual (`dbmate new ...`, `dbmate up`, which also updates
`schema.sql`), then `docker compose up -d --build`; the migrate service applies it in Docker.

**Copy your local data into Docker** (once, into an empty Docker database):

```bash
scripts/copy_local_db_to_docker.sh
```

It copies data only (the tables come from the migrations), refuses to run if the Docker database
already has users, and prints row counts for both sides.

**Sharing:** the image has no data and no secrets. Someone else needs the `backend/` folder (or the
image plus `docker-compose.yml`), creates `.env` from `.env.example` with their own
password and `JWT_SECRET_KEY`, and runs `docker compose up -d --build`. They start with an empty
database. The image is built for this Mac's chip (arm64); servers usually need amd64
(`docker buildx build --platform linux/amd64,linux/arm64 ...` when publishing).
