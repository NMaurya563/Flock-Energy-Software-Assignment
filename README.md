# Flock Energy Meter API

A read-only FastAPI service over the Urja Meter Ops portal. It converts authenticated legacy responses into a documented API for meter discovery, meter details, consumption readings, transformer lookup, and network exploration.

The upstream portal is an undocumented application with separate search, transformer, signed-export, geography, and energy flows. This service hides those details behind validated Pydantic contracts, a normalized in-memory meter index, bounded retries, session renewal, and consistent JSON errors.

---

## 1. What This Is and How It Is Structured

```text
┌─────────────────────────────────────────────────────────────┐
│                    Urja Meter Ops Portal                    │
│  • Form authentication with a session cookie                 │
│  • Meter search and transformer pagination                    │
│  • HMAC-signed bulk meter export                             │
│  • Per-meter geography and consumption readings               │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ Authenticated HTTP requests
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 UrjaClient (`app/clients/`)                  │
│  • Shared HTTPX client and session cookie jar                 │
│  • Login coalescing and bounded authentication replay         │
│  • Four-request concurrency limit                             │
│  • Timeout and transient retry handling                       │
│  • Signed export and complete pagination validation           │
└─────────────────────────────────────────────────────────────┘
             │                                      │
             │ Snapshot / discovery                 │ Live consumption
             ▼                                      ▼
┌───────────────────────────────────┐   ┌───────────────────────────────┐
│ MeterService (`app/services/`)    │   │ Reading normalization           │
│ • In-memory export snapshot       │   │ • Decimal-safe numeric values   │
│ • TTL and refresh coordination    │   │ • Explicit Asia/Kolkata         │
│ • Search, filters, and pagination │   │   timestamp assumption          │
│ • Nearby and overview queries     │   │ • Chronological cumulative      │
│ • Hierarchy reconstruction        │   │   deltas with reset protection   │
└───────────────────────────────────┘   └───────────────────────────────┘
             │                                      │
             └──────────────────┬───────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI REST API                          │
│  /health       /docs       /redoc       /openapi.json         │
│  /api/v1/meters            /api/v1/meters/{meter_id}          │
│  /api/v1/meters/nearby     /api/v1/meters/{id}/consumption    │
│  /api/v1/transformers      /api/v1/network                   │
│  /api/v1/overview          /api/v1/meta                       │
└─────────────────────────────────────────────────────────────┘
```

The request flow is:

```text
FastAPI route → MeterService → UrjaClient → Urja Meter Ops
```

Pure normalization and calculation logic stays in `backend/app/domain/`; API contracts stay in `backend/app/schemas/`. The service has no browser-runtime dependency and does not scrape HTML.

---

## 2. Quick Start

### Prerequisites

- Python 3.12+
- A valid assignment login for the Urja Meter Ops portal
- Docker Desktop, if using the container workflow

### Installation and setup on Windows PowerShell

From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Fill `PORTAL_USERNAME` and `PORTAL_PASSWORD` in `backend/.env`. The file is ignored by Git; credentials and signing secrets must never be committed.

Start the development server:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

- [Swagger UI](http://127.0.0.1:8000/docs)
- [ReDoc](http://127.0.0.1:8000/redoc)
- [OpenAPI JSON](http://127.0.0.1:8000/openapi.json)
- [Health check](http://127.0.0.1:8000/health)

Authentication is lazy. Health and documentation work without portal credentials. Data endpoints return a clear `503` until credentials are configured.

Linux/macOS users can replace the Windows interpreter path with `.venv/bin/python`.

### Docker

Configure `backend/.env`, then run from the repository root:

```powershell
docker compose up --build
```

The API is exposed at `http://127.0.0.1:8000`.

---

## 3. API Surface

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Process liveness; does not contact the portal |
| GET | `/api/v1/meters` | Search, filter, sort, and paginate the meter snapshot |
| GET | `/api/v1/meters/nearby` | Find meters within a radius, ordered by distance |
| GET | `/api/v1/overview` | Fleet counts and source-data completeness |
| GET | `/api/v1/meta` | Snapshot state, age, TTL, and refresh status |
| GET | `/api/v1/meters/{meter_id}` | Normalized meter details and quality warnings |
| GET | `/api/v1/meters/{meter_id}/consumption` | Cumulative readings and safe consumption deltas |
| GET | `/api/v1/transformers` | Complete transformer directory |
| GET | `/api/v1/transformers/{transformer_code}` | Transformer details |
| GET | `/api/v1/network` | Flat hierarchy with parent links and warnings |
| GET | `/api/v1/network/node?node_id=...` | One hierarchy node by its returned ID |

All errors use the same envelope:

```json
{
  "error": {
    "code": "not_found",
    "message": "Meter not found."
  }
}
```

Validation errors return `422`, missing resources return `404`, malformed upstream data returns `502`, unavailable or authentication failures return `503`, and upstream timeouts return `504`.

---

## 4. Sample Requests

The following examples use PowerShell:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/meters?q=J100000&page=1&page_size=20'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/meters/J100000'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/meters/nearby?latitude=26.938&longitude=75.830&radius_km=2&limit=10'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/transformers'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/network'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/overview'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/meta'
```

Consumption requests require dates with an offset. In a query string, encode `+` as `%2B`, or use `Z`:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/meters/J100000/consumption?start=2026-06-24T00:00:00Z&end=2026-06-25T00:00:00Z'
```

A normalized reading preserves decimal values as strings:

```json
{
  "timestamp": "2026-06-23T23:30:00+05:30",
  "kwh": "48438.74",
  "kvah": "52313.84",
  "voltage_r": "226",
  "consumption_kwh": null
}
```

The portal appears to expose cumulative registers. `consumption_kwh` is calculated only between valid, chronologically ordered readings. The first reading, missing registers, duplicate timestamps, and register decreases produce a null delta rather than fabricated usage.

---

## 5. Configuration and Freshness

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORTAL_URL` | Assignment portal URL | Upstream base URL |
| `PORTAL_USERNAME` | Empty | Portal login email |
| `PORTAL_PASSWORD` | Empty | Portal password; local environment only |
| `REQUEST_TIMEOUT` | `15` | Per-request timeout in seconds |
| `EXPORT_TTL_SECONDS` | `60` | In-memory export cache lifetime; `0` disables reuse |
| `UPSTREAM_ATTEMPTS` | `3` | Maximum transient attempts plus one auth replay budget |

The export is held as a small in-memory snapshot. A lock prevents duplicate refreshes, and `/api/v1/meta` reports whether it is `not_loaded`, `fresh`, or `expired`. Stale data is not silently served after a failed refresh. Consumption is fetched fresh for each request.

Each worker owns its own cache; there is no background synchronization or database requirement. PostgreSQL, SQLAlchemy, and Alembic are intentionally deferred because the verified workflows do not require durable storage.

---

## 6. Reliability and Data Rules

- Upstream requests share one HTTPX connection pool and session cookie jar for the application lifetime.
- Concurrent logins are coalesced, and an expired session receives one bounded renewal/replay.
- Four data requests may run concurrently. The request slot is released before session renewal to avoid semaphore deadlocks.
- Only read requests receive transient retries. Retryable conditions include network/timeouts and `429`, `502`, `503`, and `504`.
- Transformer ingestion follows upstream pagination metadata and rejects incomplete, duplicated, malformed, or inconsistent pages.
- Export ingestion requires the returned row count to match `total` and rejects duplicate or blank meter IDs.
- Nearby search uses Haversine distance on valid coordinates and reports the full match count before limiting results.
- Hierarchy IDs include ancestry because observed hierarchy codes are not globally unique.
- Missing or invalid numeric values become `null` with warnings; zero remains a valid value.
- Portal timestamps do not include a timezone. The API documents Asia/Kolkata as an assumption based on the Jaipur utility context.
- Historical consumption requests are capped at 93 local calendar days and require paired `start`/`end` bounds for upstream retrieval.

See the [verified protocol](PROTOCOL.md) for observed upstream behavior and limitations.

---

## 7. Project Structure

```text
backend/
  app/
    main.py             Application lifecycle, errors, and request logging
    api/                Router, dependencies, and versioned endpoints
    clients/            Upstream authentication, signing, retries, and pagination
    core/               Configuration and shared exceptions
    domain/             Pure normalization, readings, hierarchy, and discovery logic
    schemas/            Pydantic response and request contracts
    services/           Snapshot freshness and application orchestration
  scripts/              OpenAPI export and explicit live smoke check
  tests/
    unit/               Client, geography, and pure calculation tests
    integration/        HTTP API tests with mocked upstream responses
frontend/               Optional dashboard scope note
docs/
  architecture.md       Folder responsibilities and dependency rules
  decisions.md          Engineering decisions and trade-offs
  investigation/        Sanitized protocol evidence
PROTOCOL.md              Verified upstream protocol
REFLECTION.md            Technical notes and reflection prompts
openapi.json             Generated OpenAPI 3.1 contract
```

Read the [folder guide](docs/architecture.md) for dependency boundaries and the [decision log](docs/decisions.md) for alternatives and trade-offs.

---

## 8. Test and Verify

Run from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m ruff format --check app tests scripts
.\.venv\Scripts\python.exe -m scripts.export_openapi
```

The test suite uses mocked upstream traffic and does not require credentials, network access, or a database. The live smoke script is intentionally separate because it contacts the portal:

```powershell
.\.venv\Scripts\python.exe -m scripts.smoke
```

To check an already-running server:

```powershell
.\.venv\Scripts\python.exe -m scripts.smoke --base-url http://127.0.0.1:8000
```

---

## 9. Documentation and Scope

- [Backend README](backend/README.md)
- [Architecture guide](docs/architecture.md)
- [Engineering decisions](docs/decisions.md)
- [Verified protocol](PROTOCOL.md)
- [Investigation evidence](docs/investigation/EVIDENCE.md)
- [OpenAPI contract](openapi.json)
- [Reflection prompts](REFLECTION.md)

The core submission is backend-focused. There are no user accounts, mutations, JWTs, Redis, background workers, persistent query indexing, or dashboard requirements in the current scope. Add access controls before exposing the service beyond a trusted local environment.

The upstream adapter depends on undocumented portal behavior, including the signed bulk export route. Credentials and signing secrets remain runtime-only, and protocol changes may require corresponding client updates.
