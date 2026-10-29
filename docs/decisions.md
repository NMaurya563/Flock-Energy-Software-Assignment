# Engineering decisions and trade-offs

Status: accepted for the current implementation. Recorded: 29 October 2026.

This log describes the choices actually implemented in this Python project. It adapts the decision-log approach of the [reference repository](https://github.com/log1-codes/Flock-Energy-Software-Assignment/blob/master/docs/decisions.md), while using our own verified protocol evidence and selected stack. It does not assert that all reference-repository claims were independently verified.

For each meaningful future architecture change, add or update a numbered record with its context, chosen approach, alternatives, consequences, and reason to revisit it. Mark replaced decisions as superseded and link the replacement. Keep runtime observations in [PROTOCOL.md](../PROTOCOL.md) and personal experience in [REFLECTION.md](../REFLECTION.md).

## D-001 — Python stack and a modular monolith

- **Context:** The requested stack is Python 3.12+, FastAPI, Pydantic v2, and HTTPX. The assignment is small enough to run as one local service.
- **Decision:** Use one FastAPI application, with resource routes, explicit response schemas, pure domain functions, an application service, and an upstream client. Preserve `backend/` and `frontend/` at the root to follow the original MedSync preference.
- **Alternatives:** Port the TypeScript/Fastify reference wholesale; put everything in one module; create separate services for each domain.
- **Consequences:** The project stays within the chosen stack and each layer has a clear owner. There is some module navigation overhead, but no distributed deployment or messaging infrastructure.
- **Revisit when:** There are independently deployed capabilities or materially different scaling requirements. See the [folder guide](architecture.md).

## D-002 — Isolate observed legacy transport behind one client

- **Context:** The portal is undocumented. Browser-delivered JavaScript exposes ordinary search, detail, transformer, and export behavior.
- **Decision:** Keep HTTP, cookie handling, signing, timeouts, and upstream errors in `app/clients/urja_client.py`. Use the verified signed export for meter metadata, geography, and hierarchy, plus separate energy and transformer requests.
- **Alternatives:** Scrape HTML or decode SvelteKit page-state arrays on every request; call detail routes once per meter.
- **Consequences:** A small adapter contains protocol changes and avoids browser automation at runtime. The application depends on the current export behavior; it rejects incomplete results instead of silently dropping records.
- **Revisit when:** The portal exposes a supported API or changes its export/authentication contract. Evidence: [protocol](../PROTOCOL.md), [investigation](investigation/EVIDENCE.md).

## D-003 — Lazy configuration-dependent authentication

- **Context:** Health and documentation should remain accessible without portal credentials. The verified form login needs an Origin header and sets a secure session cookie.
- **Decision:** Validate configuration types with pydantic-settings; read credentials from environment or ignored `backend/.env`. Authenticate lazily using `POST /login`, retain cookies in HTTPX, and serialize login attempts with an async lock and session-generation check.
- **Alternatives:** Authenticate and download data at boot; hardcode a cookie; assume an unmeasured expiry and refresh on a fixed timer.
- **Consequences:** Missing credentials return 503 on data requests while docs and liveness remain available. The first data call incurs authentication latency. A 401 or login redirect receives at most one renewal per request; a 403 access/signature rejection is surfaced as an upstream error instead of retrying login. Secrets are not persisted in code or logs.
- **Revisit when:** Real measurements establish session lifetime, rotation behavior, or a need for multiple upstream accounts. No fixed one-hour expiry is assumed by this implementation.

## D-004 — Bounded concurrency and separate retry budgets

- **Context:** A session renewal must not recursively wait for a concurrency slot held by its own request. Transient failures should not cause unbounded upstream traffic.
- **Decision:** Permit four concurrent data requests. Release the slot before renewal, backoff, or replay. Use a default 15-second HTTP timeout, three configured transient attempts, and one separate authentication replay. Retry network/timeouts and 429/502/503/504 with bounded backoff.
- **Alternatives:** Unrestricted parallelism, recursive retries while holding a semaphore, retries for every status, or no retries.
- **Consequences:** Request volume is bounded and the four-simultaneous-401 case completes in regression tests. There is additional latency during retryable failures. Login POSTs are not automatically retried, and Retry-After scheduling is deferred.
- **Revisit when:** Operational measurements justify different limits or a circuit breaker.

## D-005 — Short-lived memory snapshot, explicit freshness

- **Context:** The observed export has 403 meters, which fits comfortably in process memory. Most discovery requests can reuse the same snapshot.
- **Decision:** Cache a validated export for 60 seconds by default, with one refresh lock per process. Replace the snapshot only after successful validation. Expose `fetched_at` and passive `/api/v1/meta` state. Expired data requests refresh or fail; they do not silently serve stale data. Readings and transformer-directory requests remain live.
- **Alternatives:** Fetch the export on every request; background stale-while-revalidate; Redis; a persistent database index.
- **Consequences:** Low operational complexity and explicit freshness, with possible failures during an upstream outage once the cache expires. Workers have independent caches, and refresh still downloads the entire export. This deliberately differs from the reference repository's stale-while-revalidate design.
- **Revisit when:** Availability requirements explicitly permit stale results, workers multiply, or dataset size makes a shared persistent index worthwhile.

## D-006 — Validate completeness and follow pagination metadata

- **Context:** The export currently supplies the complete dataset in `page=1`; transformer pages include total, page, and pageSize metadata.
- **Decision:** Require export row count to equal total and reject duplicate or blank meter IDs. Traverse transformer pages using returned metadata, rejecting duplicate codes, changed totals or page sizes, wrong pages, and missing rows; cap traversal at 1000 pages.
- **Alternatives:** Hardcode two transformer pages; accept whatever records arrive; infer unsupported export pagination.
- **Consequences:** Incomplete data becomes a clear 502 error rather than a misleading success. A source that changes while transformer pages are being read may require a subsequent retry by the consumer.
- **Revisit when:** The portal adds snapshot IDs, cursors, or explicit bulk-export pagination.

## D-007 — Preserve hierarchy ambiguity

- **Context:** Hierarchy codes repeat under different ancestors, and some names or codes are inconsistent or missing.
- **Decision:** Identify nodes by the full observed ancestor path, expose conflict warnings, and retain source values. Keep the transformer directory separately accessible rather than silently treating it as authority over meter-embedded hierarchy fields.
- **Alternatives:** Globally merge equal codes; automatically repair missing relationships; overwrite conflicting names from the transformer directory.
- **Consequences:** Consumers can see uncertainty instead of receiving guessed topology. Missing tiers remain a limitation, and repeated codes can appear in several branches. The result describes observed relationships, not independently verified physical wiring.
- **Revisit when:** A documented authoritative mapping or utility-approved repair rule is available.

## D-008 — Decimal readings and conservative consumption deltas

- **Context:** Energy readings arrive as strings and appear cumulative. Bad values, repeated timestamps, and register decreases can distort derived consumption.
- **Decision:** Parse finite numeric values with Decimal, retain zero, return null for invalid values, and surface parsing warnings. Sort timestamps before calculating differences. Suppress deltas for the first returned row, missing adjacent registers, any interval touching a duplicate timestamp, and decreases.
- **Alternatives:** Convert failed parsing to zero; use binary floating-point for energy; blindly subtract response-order rows; treat decreases as negative consumption.
- **Consequences:** Decimal values serialize as strings and consumers must parse them accordingly. Each accepted delta spans its actual pair of timestamps; no fixed interval or complete-coverage guarantee is inferred. Register-reset usage is unknown, not estimated.
- **Revisit when:** The utility documents meter reset/rollover rules or supplies interval energy directly.

## D-009 — Historical retrieval with explicit date semantics

- **Context:** Live queries verified `from`/`to` local calendar dates. Raw timestamps contain no timezone offset.
- **Decision:** Require timezone-aware public start/end timestamps. With both bounds, convert them to assumed Asia/Kolkata dates, fetch that upstream window, and apply exact inclusive boundaries locally. Limit paired queries to 93 local calendar days. A single bound preserves filtering of the default upstream window.
- **Alternatives:** Only filter the default seven-day response; silently interpret naive timestamps as UTC; allow unlimited historical requests.
- **Consequences:** Historical windows now work, including UTC boundaries crossing a local date. Asia/Kolkata remains a stated assumption; 93 days is a service policy, not a claimed upstream restriction. Availability remains controlled by the portal.
- **Revisit when:** The source confirms timezone or establishes a different retention or pagination contract.

## D-010 — Derived discovery without extra infrastructure

- **Context:** Verified exports already include useful coordinates, statuses, manufacturers, and hierarchy fields.
- **Decision:** Use in-memory Haversine radius search, exact attribute/hierarchy filters, deterministic sorting, and fleet/data-completeness summaries. Keep the calculations in `app/domain/`; use validated snapshots for input.
- **Alternatives:** PostGIS, an R-tree, a search service, or per-meter portal calls for discovery queries.
- **Consequences:** No additional infrastructure is needed at the observed scale. Nearby queries scan O(N) records and sort matches. Invalid/missing locations are excluded and counted; valid (0, 0) is retained. Counts describe source data and are not inferred fault alarms.
- **Revisit when:** Measured latency or dataset size requires an index.

## D-011 — Explicit API contracts and structured errors

- **Context:** Consumers need a stable contract despite upstream inconsistency.
- **Decision:** Group response schemas by resource, generate OpenAPI from FastAPI, and use `{"error":{"code":"...","message":"..."}}` for handled errors. Distinguish validation 422, not-found 404, method-not-allowed 405, malformed upstream 502, unavailable/authentication 503, and timeout 504.
- **Alternatives:** Pass upstream bodies directly to clients; hand-maintain a second OpenAPI specification; return success for partial/malformed data.
- **Consequences:** Public errors do not expose raw upstream bodies. Schema edits require regenerating root `openapi.json`; structural refactors can be checked against the previous contract.
- **Revisit when:** Versioned compatibility requirements or a client SDK warrant a formal deprecation policy.

## D-012 — Keep optional deployment and persistence work scoped

- **Context:** The assignment prioritizes a usable API over infrastructure, and no current feature needs durable storage.
- **Decision:** Defer PostgreSQL/SQLAlchemy/Alembic, downstream accounts, a dashboard, Redis, and background jobs. Keep a frontend scope note, but create database/migration packages only when a persistent feature is implemented. Provide local Python setup and a small Docker configuration.
- **Alternatives:** Add empty ORM layers, speculative schemas, migrations with no consumers, or a mandatory database to run the API.
- **Consequences:** Setup is small and the folder tree reflects implemented responsibilities. The service is intended for trusted local use; broader deployment needs access controls and operational design. The Docker image builds successfully, and a temporary container passed live smoke checks across all 11 API paths.
- **Revisit when:** A concrete persistence, UI, multi-user access, or deployment requirement is accepted. PostgreSQL remains the chosen persistence option if justified.

## D-013 — Offline regression tests and opt-in live verification

- **Context:** CI and local tests must be repeatable without portal credentials or availability.
- **Decision:** Keep HTTPX/mock-client and pure calculation checks in `tests/unit/`; put in-process HTTP API integration checks in `tests/integration/`, with the upstream mocked. Use a separate explicit `scripts.smoke` command for live verification. Pin direct runtime/development dependencies.
- **Alternatives:** Make every test hit the portal; only test happy-path helpers; report unit success as proof of live compatibility.
- **Consequences:** The 75-test offline suite is deterministic and live checks exercise all 11 documented paths separately. Simulated expiry, resets, malformed payloads, and retry behavior are labeled as tests rather than live observations. A Starlette/httpx test-client deprecation warning remains non-failing.
- **Revisit when:** A stable staging portal, supported contract, or production deployment enables additional automated integration coverage.
