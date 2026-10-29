# Project architecture and folder guide

This project adapts the reference repository's separation of routes, domain logic, and portal access to Python/FastAPI. It preserves the earlier MedSync preference for separate backend and frontend roots. The folder tree includes implemented capabilities; database packages will be added when a durable feature needs them.

## Layout

```text
Flock-Energy/
|-- backend/
|   |-- app/
|   |   |-- main.py                  # App creation, lifecycle, errors, logging, liveness
|   |   |-- api/
|   |   |   |-- router.py            # /api/v1 composition and shared error schemas
|   |   |   |-- dependencies.py      # Shared service injection and ID parameter type
|   |   |   `-- v1/
|   |   |       |-- meters.py        # Meter list and detail
|   |   |       |-- consumption.py   # Historical/current reading queries
|   |   |       |-- network.py       # Hierarchy and node lookup
|   |   |       |-- transformers.py  # Transformer directory and detail
|   |   |       `-- discovery.py     # Nearby search, overview, passive metadata
|   |   |-- clients/
|   |   |   `-- urja_client.py       # Cookies, login, signatures, retries, pagination
|   |   |-- core/
|   |   |   |-- config.py            # Validated environment settings
|   |   |   `-- exceptions.py        # Shared adapter/application errors
|   |   |-- domain/
|   |   |   |-- constants.py         # Hierarchy levels and explicit timezone assumption
|   |   |   |-- normalization.py     # Meter field normalization
|   |   |   |-- consumption.py       # Reading parsing and safe Decimal deltas
|   |   |   |-- network.py           # Ancestor-aware hierarchy construction
|   |   |   `-- discovery.py         # Haversine distance and fleet aggregation
|   |   |-- schemas/
|   |   |   |-- common.py            # Error response contracts
|   |   |   |-- meter.py             # Meter, coordinates, hierarchy entries, pagination
|   |   |   |-- consumption.py       # Reading and consumption responses
|   |   |   |-- network.py           # Network/node responses
|   |   |   |-- transformer.py       # Transformer responses
|   |   |   `-- discovery.py         # Nearby, fleet, and cache metadata responses
|   |   `-- services/
|   |       `-- meter_service.py     # Portal orchestration, validation, snapshot, queries
|   |-- scripts/                    # Explicit live smoke check and OpenAPI generator
|   |-- tests/
|   |   |-- conftest.py              # Shared synthetic/representative fixtures
|   |   |-- unit/                   # Client behavior and pure geography checks
|   |   `-- integration/            # API wiring/validation with mocked upstream
|   |-- .env.example
|   |-- requirements.txt
|   |-- requirements-dev.txt
|   |-- pyproject.toml
|   |-- Dockerfile
|   `-- README.md
|-- frontend/
|   `-- README.md                   # Optional dashboard scope; no UI runtime yet
|-- docs/
|   |-- decisions.md                # Choices, alternatives, consequences, revisit triggers
|   |-- architecture.md             # This guide
|   `-- investigation/EVIDENCE.md    # Sanitized observed protocol evidence
|-- README.md                       # Setup, public API, limitations, documentation links
|-- PROTOCOL.md                     # Actual upstream behavior and its uncertainties
|-- REFLECTION.md                   # Technical notes and candidate reflection prompts
|-- openapi.json                    # Generated public API contract
`-- docker-compose.yml
```

Package `__init__.py` files and local ignored environments/caches are omitted from this view. Credentials stay in ignored `backend/.env` or environment variables. Nothing under `.venv` is application source.

## Responsibilities and dependencies

- **API:** HTTP routing, query validation, dependency injection, and response contracts. A central router registers static discovery paths before meter-ID routes.
- **Services:** Coordinate portal reads, snapshot validation/freshness, and application-level lookup/filtering. Own mutable runtime state.
- **Domain:** Deterministic data transformations and calculations. May use response schemas and shared errors/constants, but does not import the API, service, or HTTP client.
- **Clients:** All upstream HTTP operations, authentication, session cookies, signing, pagination, and bounded recovery.
- **Schemas:** Explicit Pydantic shapes, grouped by resource. Do not perform I/O.
- **Core:** Shared settings and error types; keep this small instead of treating it as a miscellaneous folder.

Most requests follow API -> service -> portal client, then domain normalization -> schema response. Nearby/overview routes obtain a validated service snapshot and apply pure domain calculations. Configuration and response models are shared dependencies rather than extra runtime services.

## Relationship to the reference repository

| Reference TypeScript layout | Python adaptation |
| --- | --- |
| `src/index.ts`, `src/server.ts` | `backend/app/main.py` |
| `src/routes/` | `backend/app/api/v1/` plus central `api/router.py` |
| `src/portal/` | `backend/app/clients/` |
| `src/domain/normalize.ts` | Focused modules in `backend/app/domain/` |
| `src/domain/store.ts` | Snapshot and query orchestration in `backend/app/services/` |
| Zod schemas embedded in routes | Resource-specific Pydantic models in `backend/app/schemas/` |
| `src/config.ts` | `backend/app/core/config.py` |
| `tests/`, `scripts/`, `docs/decisions.md` | Equivalent Python test/script/documentation responsibilities |

This is a responsibility mapping, not a language-porting requirement. The dependency direction and smaller modules make the Python code easier to explain and test while retaining the local run command `uvicorn app.main:app`.

## Where new work belongs

1. A new public resource needs schemas and a focused route module; register it in `api/router.py`.
2. New upstream requests belong in the client and must be backed by protocol evidence.
3. Parsing/calculation changes belong in `domain/`; network or cache orchestration belongs in the service.
4. Put behavioral tests at the lowest useful layer, with API integration coverage for externally visible behavior.
5. Record consequential choices in [decisions.md](decisions.md), update [PROTOCOL.md](../PROTOCOL.md) when new upstream facts are verified, and regenerate `openapi.json` for contract changes.

Do not create empty repositories, models, database sessions, migrations, or utility packages just to fill the tree. Add them with the first implemented feature that needs them.
