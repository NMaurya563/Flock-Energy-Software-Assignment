# Flock Energy Meter API

A read-only FastAPI service over the Urja Meter Ops portal. It converts authenticated legacy responses into documented JSON for meter search, meter details, consumption readings, and network exploration.

## Quick start (Windows PowerShell)

Python 3.12+ is required. From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Fill PORTAL_USERNAME and PORTAL_PASSWORD in .env using the assignment's credentials.
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If `.env` already exists, keep it. The local workspace has credentials configured from the supplied assignment; `.env` is ignored and is not a distributable file. No credentials or signing secrets belong in source control.

Linux/macOS: use `python3 -m venv .venv` and `.venv/bin/python` in place of the Windows interpreter path. You do not need to activate the environment.

Open [Swagger UI](http://127.0.0.1:8000/docs), [ReDoc](http://127.0.0.1:8000/redoc), or [health](http://127.0.0.1:8000/health). The default server binds only to localhost. Authentication is lazy: health and docs work without portal credentials; data endpoints return a clear 503 until configured.

## API

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Process liveness, no upstream probe |
| GET | `/api/v1/meters` | Search meter ID/serial; make/status/transformer/phase/installation/hierarchy filters; sorting and pagination |
| GET | `/api/v1/meters/nearby` | Radius search ordered by distance, with pre-limit match count |
| GET | `/api/v1/overview` | Fleet counts by make/status/phase and data completeness |
| GET | `/api/v1/meta` | Passive cache state, age, TTL, and refresh status |
| GET | `/api/v1/meters/{meter_id}` | Normalized details, coordinates, hierarchy, data-quality warnings |
| GET | `/api/v1/meters/{meter_id}/consumption` | Cumulative readings and safe deltas; bounded historical retrieval with start/end |
| GET | `/api/v1/transformers` | Complete transformer directory using upstream pagination metadata |
| GET | `/api/v1/transformers/{transformer_code}` | Transformer details |
| GET | `/api/v1/network` | Flat hierarchy with explicit parents, meter counts, conflict warnings |
| GET | `/api/v1/network/node?node_id=...` | One hierarchy node, using its returned ID |

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/meters?q=J100000&page=1&page_size=20'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/meters/J100000'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/meters/J100000/consumption?start=2026-06-24T00:00:00Z&end=2026-06-25T00:00:00Z'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/network'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/meters/nearby?latitude=26.938&longitude=75.830&radius_km=2&limit=10'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/overview'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/meta'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/meters?phase=single&hierarchy_level=zone&hierarchy_code=Z-01&sort_by=make&order=asc'
```

Observed J100000 fields include serial `SE33962`, make `HPL`, phase `single`, status `Decommissioned`, and transformer `DT-001`. A normalized reading looks like:

```json
{"timestamp":"2026-06-23T23:30:00+05:30","kwh":"48438.74","kvah":"52313.84","voltage_r":"226"}
```

Decimal readings serialize as strings to retain decimal precision. Zero is preserved. Missing or invalid numeric values become null with warnings. Invalid timestamps are omitted with warnings. The timestamp timezone is an explicit assumption, not a verified upstream guarantee.

Dates must include an offset; URL-encode `+` as `%2B` in query strings, or use `Z`. Supply both `start` and `end` to fetch historical readings using the verified upstream `from`/`to` calendar-date parameters. UTC boundaries are converted to Asia/Kolkata dates before fetching, then exact inclusive timestamps are applied locally. Queries span at most 93 local calendar days. With neither bound, the default upstream window is returned; one bound retains local filtering of that default window. Data availability is determined by the portal. kWh/kVAh values appear cumulative; the original cumulative values remain available. `consumption_kwh` reports the Decimal difference between successive valid, chronologically sorted readings in the returned slice. The first row, missing registers, intervals touching duplicate timestamps, and register decreases produce null deltas rather than fabricated usage. A delta spans the actual time between its two readings, which may exceed a normal interval.

Errors use `{"error":{"code":"...","message":"..."}}`. Invalid parameters return 422, missing meters/nodes 404, malformed upstream responses 502, unavailable/authentication failures 503, and upstream timeouts 504.

## Structure and architecture

The layout preserves MedSync's separate application roots and adapts the reference repository's routes/domain/portal separation to FastAPI. See the [complete folder guide](docs/architecture.md) and [engineering decision log](docs/decisions.md).

```text
backend/
  app/
    main.py             Application lifecycle, errors, request logging
    api/                Central router, dependencies, routes grouped by resource
    clients/            Upstream authentication, signing, retries, pagination
    core/               Configuration and shared errors
    domain/             Pure normalization, reading, hierarchy, and discovery logic
    schemas/            Pydantic contracts grouped by resource
    services/           Snapshot freshness, upstream orchestration, application queries
  scripts/              OpenAPI export and explicit live API smoke check
  tests/
    unit/               Client behavior and pure calculation tests
    integration/        HTTP API tests with mocked upstream responses
frontend/               Optional dashboard scope note
docs/
  decisions.md          Decisions, alternatives, trade-offs, revisit conditions
  architecture.md       Folder responsibilities and dependency rules
  investigation/        Sanitized protocol evidence
PROTOCOL.md             Verified upstream protocol
REFLECTION.md           Technical notes and personal reflection prompts
openapi.json            Generated OpenAPI 3.x contract
```

Request flow: FastAPI router -> service -> HTTPX portal client -> Urja Meter Ops. The service reads the portal's existing signed bulk export, which already contains nameplate, geographic, and hierarchy fields. Consumption remains a per-meter request. There is no browser runtime dependency or HTML scraping in the service.

Four upstream data requests may run concurrently. A request releases its concurrency slot before any session renewal or retry, preventing recursive semaphore deadlocks. Authentication replay has a separate budget from transient failures. One HTTPX connection pool and session cookie jar live for the application lifetime and are closed on shutdown. A lock coalesces concurrent logins. An expired session triggers one renewal, with bounded replay. A 401 or login redirect can trigger session renewal; a 403 is reported as an upstream access error without repeating login. Only read requests receive transient retries; form login is not automatically retried. Retryable conditions are network/timeout failures and 429/502/503/504. Backoff is bounded; unexpected response bodies and errors are not logged.

## Configuration and freshness

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORTAL_URL` | Supplied portal URL | Upstream base URL |
| `PORTAL_USERNAME` | empty | Assignment login email |
| `PORTAL_PASSWORD` | empty | Secret, local environment only |
| `REQUEST_TIMEOUT` | 15 | Per-request HTTP timeout in seconds |
| `EXPORT_TTL_SECONDS` | 60 | Per-process export cache lifetime, 0 disables reuse |
| `UPSTREAM_ATTEMPTS` | 3 | Maximum transient attempts, with one additional auth replay budget |

The export cache is a small, in-memory snapshot with a lock to prevent duplicate fetches. `fetched_at` exposes retrieval time. Expired snapshots are refreshed; stale data is never silently served after refresh failure. Consumption is fetched fresh. Each worker has its own cache; there is no background synchronization. Refresh fetches the whole export, so a very large dataset or many workers would need a shared index and a streaming or paginated ingestion design.

## PostgreSQL decision

Direct reads plus a short-lived cache satisfy the core task. PostgreSQL, SQLAlchemy models, and Alembic migrations are intentionally deferred: no durable table is necessary for the verified workflows. Database and migration packages will be created with the first justified persistent feature; unused scaffolding has been removed. A future index should upsert observed meter IDs and record retrieval time, while retaining the portal as the source of truth. There are no database setup requirements for this version.

## Test and verify

Run from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m ruff format --check app tests scripts
.\.venv\Scripts\python.exe -m scripts.export_openapi
# Explicitly opts into read-only live portal traffic:
.\.venv\Scripts\python.exe -m scripts.smoke
```

The offline suite contains 75 passing tests, including four simultaneous expired requests, changing/incomplete transformer pages, incomplete exports, and invalid/reset register values. The normal test suite uses mocked upstream responses and requires neither credentials, network access, nor a database. Tests cover signatures, concurrent login, session renewal, retries, timeouts, malformed responses, normalization, exact filter behavior, pagination, timestamps, and hierarchy conflicts.

A live check on 29 October 2026 verified 403 meters, 40 transformers across all upstream pages, 337 readings for J100000, and 240 hierarchy nodes with 91 conflict warnings. Counts are observations of that instance, not invariants. See [investigation evidence](docs/investigation/EVIDENCE.md).

## Docker

```powershell
docker compose up --build
```

First configure `backend/.env`. Docker exposes port 8000 on localhost. The image build and all 11 API paths have been verified in a temporary Docker container, as well as in the local Python environment.

## Decisions, assumptions, and limitations

The numbered [decision log](docs/decisions.md) records the chosen approach, alternatives, trade-offs, and conditions for revisiting each architecture choice.

- The signed bulk route is a normal feature of the portal's transformer page. It avoids per-meter detail scraping and preserves fields that search omits.
- The observed export returns all 403 rows for `page=1` without pagination metadata. The service checks row count against `total` and fails clearly if the portal starts returning partial exports.
- Hierarchy codes are not globally unique in clean parent relationships. IDs include full ancestry, preventing silent merges; warnings expose reused codes under different parents and conflicting labels.
- Portal timestamps omit timezone. Asia/Kolkata is assumed based on the Jaipur utility context. Historical `from`/`to` support was verified with June 1-2 and June 25 queries; the public API caps requests at 93 local days.
- Search is local case-insensitive ID/serial matching; make/status/transformer filters use exact values. Sorting defaults to meter ID ascending. `sort_by` supports meter_id/make/status and `order` supports asc/desc; meter ID breaks ties. Hierarchy filters require both hierarchy_level and hierarchy_code and match exact observed codes.
- No JWT, user accounts, mutations, Redis, background workers, or frontend dashboard are required for the core task. The API is intended for trusted local use. Add access controls before exposing it outside that context.
- The adapter depends on an undocumented protocol and on the bulk signing secret route. Credentials and signing secrets remain runtime-only. Changes to those routes require adapter updates.
- Retry-After scheduling, shared multi-worker cache, production metrics, persistent query indexing, and large-export streaming are improvements for a larger deployment.
- Personal reflection must be completed by the candidate from their own experience. Technical investigation and code here were assistant-assisted; do not represent them as independently completed work.

[Engineering decisions](docs/decisions.md) · [Folder guide](docs/architecture.md) · [Verified protocol](PROTOCOL.md) · [OpenAPI contract](openapi.json) · [Reflection](REFLECTION.md)


## Repository review fixes

The referenced TypeScript/Fastify repository was reviewed for behavior; this implementation remains Python 3.12+, FastAPI, Pydantic v2, HTTPX, and pytest. No Node application was added. Transformer pagination follows observed `total`, `page`, and `pageSize`; duplicate codes, missing pages, changed totals or page sizes, and malformed records fail with 502. Export ingestion validates completeness and unique, nonblank meter IDs before replacing the current cache. Consumption normalization never treats invalid data as zero or invents a negative consumption interval after register reset.


## Discovery and freshness

Nearby search uses Haversine distance on valid export coordinates. It sorts by unrounded distance and meter ID, limits results to 100, and reports the full matching count before the limit. Missing or invalid coordinates are excluded and counted; legitimate (0, 0) coordinates remain valid. This is an O(N) scan suited to the observed small dataset.

The overview returns meter counts by observed status, make, and phase, distinct nonempty transformer codes, coordinate coverage, meters with normalization warnings, and incomplete hierarchy counts. It reports source-data completeness, not electrical fault detection. Missing grouping values use `Unknown`.

`/api/v1/meta` is passive and requires no upstream connection. Its state is `not_loaded`, `fresh`, or `expired`, with snapshot age, TTL, and refresh-in-progress. An expired cache is not silently served by data endpoints: the next data query refreshes it or returns the upstream error. All discovery responses that use a snapshot include `fetched_at`.

The smoke script exercises all public API routes plus representative validation and error paths against live portal data. To check an already-running instance instead of an in-process app, run `python -m scripts.smoke --base-url http://127.0.0.1:8001` from backend. Both the local server and the Docker container passed this live smoke check.
#   F l o c k - E n e r g y - S o f t w a r e - A s s i g n m e n t  
 