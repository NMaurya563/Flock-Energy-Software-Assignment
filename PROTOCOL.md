# Urja Meter Ops protocol

## Evidence and scope

Observed on 29 October 2026 using the supplied assignment login, normal read-only HTTP requests, and the JavaScript shipped to an ordinary browser. These are assistant observations, not a claim that the candidate personally performed the investigation. No REA tool was invoked: direct inspection of browser-delivered modules and live responses was sufficient. No scanning or mutation routes were used.

## Authentication

`GET /` redirects to `/login`. The login HTML contains a form with method POST and fields `email` and `password`. Send form-encoded `POST /login` with `Origin: https://urja-ops.flockenergy.tech`. Without Origin, a test submission was rejected as cross-site. With Origin, the observed response was JSON `{"type":"redirect","status":303,"location":"/meters"}` and a session cookie. The client also accepts an ordinary HTTP 303 with that cookie.

The cookie name is `__Secure-better-auth.session_token`; observed flags were Secure, HttpOnly, and Path=/. Cookie values, passwords, and signing secrets are never retained in these notes. An unauthenticated request to `/portal/meters/search` returned 401 with `{"error":"unauthorized","message":"A valid session is required."}`. Natural expiry duration was not measured. Renewal behavior is tested with a simulated 401; no claim is made that the live session was held until expiry.

## Browser architecture

The site identifies itself as SvelteKit. Initial `/meters` HTML showed 0 meters because the browser fills the table after mounting. It is therefore not evidence of an empty dataset. The page manifest exposes `/meters`, `/meters/[id]`, and `/transformers`.

Observed assets:

- `/_app/immutable/entry/app.03ZTmlg3.js`: page module manifest.
- `/_app/immutable/nodes/5.C4dYcCRt.js`: search request, 20-row pagination, meter fields.
- `/_app/immutable/nodes/6.l777LXKL.js`: geo/energy calls and two nameplate response shapes.
- `/_app/immutable/nodes/4.2Bgc2kUI.js`: transformer listing and signed export algorithm.

Asset hashes may change on deployment. They are investigation evidence, not runtime dependencies.

## Verified data routes

| Request | Observed response / behavior |
| --- | --- |
| `GET /portal/meters/search?q=&page=1` | `{data:[...],total:403,page:1,pageSize:20}` |
| `GET /portal/meters/search?q=J100000&page=1` | One matching meter |
| `GET /portal/dts?page=1` | Transformer rows; total 40; pageSize 20 |
| `GET /portal/keys` | `{data:{signingSecret:...}}`, session protected |
| `GET /portal/export?page=1` | Signed request; 403 complete meter rows and total 403 |
| `GET /portal/meters/J100000/geo` | String latitude and longitude inside data |
| `GET /portal/meters/J100000/energy` | 337 string-valued readings inside data |
| `GET /portal/meters/UNKNOWN/energy` | 404, `error:not_found`, `message:Meter not found` |
| `GET /meters/J100000/__data.json` | SvelteKit indexed/devalue data for details and hierarchy |

Search rows use `meterId`, `serialNo`, `make`, `phaseType`, `installStatus`, and `dtCode`. Transformer rows use `code`, `name`, `feederCode`, and `capacityKva`. Search is the portal's UI path, but the service uses bulk export for richer records and local filtering.

## Signed bulk export

The transformer page's "Export all meters" handler first fetches the signing secret, then computes:

```text
timestamp = decimal Unix seconds
query = page=1
canonical = GET + newline + /portal/export + newline + query + newline + timestamp
signature = lowercase hex HMAC-SHA256(secret UTF-8, canonical UTF-8)
```

Send the export GET with `x-timestamp` and `x-signature`. This exact sequence was replayed successfully. There is no trailing newline in the canonical message. No signing secret is hardcoded. Signature expiry tolerance and key rotation were not measured.

The observed envelope contains `data` and `total`, but no page/pageSize metadata; all 403 rows arrived from page=1. The adapter requires count==total, rejects duplicate meter IDs, and reports incomplete export rather than silently presenting partial data. No unsupported page-count assumption is used.

Export records include the search fields plus `installType`, `build`, `hierarchy`, and `geo`. Hierarchy levels are `zone`, `circle`, `division`, `subdivision`, `substation`, `feeder`, and `dt`; each contains `name` and `code`. Geography uses `lat` and `lng`. `build` is not exposed as a public business field.

## Nameplate detail alternatives

SvelteKit detail JSON contains references into indexed arrays, so it is not a plain nested business response. The delivered detail module handles either `data:[{parameterName,parameterValue}]` or `classData` containing JSON with `installed_meter`. The two detail pages directly checked used the first shape. The second shape was seen in client code only. The service avoids dependence on that serializer by using the observed bulk export instead.

## Consumption and geography

Observed geo J100000: latitude `26.938961002479868`, longitude `75.83095696146852`, both strings on the geo route and numeric in export.

Observed energy rows use `timestamp`, `kwh`, `kvah`, and `voltR`, as strings. J100000's default response spans 23/06/2026 23:30 through 30/06/2026 23:30, with 337 readings at apparent half-hour intervals. First kWh is `48438.74`; the final is `48580.79`. These appear cumulative. No timezone offset is supplied. Asia/Kolkata is a documented service assumption, not proven by the protocol. Follow-up live checks verified calendar-date query support: `from=2026-06-01&to=2026-06-02` returned 96 rows spanning June 1 00:00 to June 2 23:30; `from=2026-06-25&to=2026-06-25` returned 48 rows spanning that day. The adapter now forwards paired bounds as local calendar dates and applies exact inclusive timestamp filtering afterward. One-sided bounds retain default-window filtering. A 93-local-day cap is a service policy, not a measured upstream limit.

## Hierarchy and reliability observations

The full dataset reconstructs into 240 ancestry-specific nodes and 91 warnings about reused codes across parents or conflicting names. Codes alone cannot safely identify globally unique nodes. Preserve full ancestry in IDs; expose warnings rather than arbitrarily correcting source data.

Live behavior was checked for successful login, Origin rejection, unauthenticated 401, meter search, missing meter 404, signed export, geo, and energy. Timeout handling, session expiry renewal, malformed payloads, and retry bounds are simulated in deterministic tests. No long-running expiry measurement, production load test, or full consumption sweep was performed.


## Adapter reliability updates

Transformer ingestion now follows the verified pagination envelope until its total is reached instead of assuming two pages. The observed instance still contains 40 transformers in two 20-row pages. Empty/short pages before completion, duplicate codes, changed totals or page sizes, invalid page metadata, and a maximum 1000-page traversal limit prevent incomplete or unbounded ingestion.

The Python client limits concurrent data requests to four, releasing the slot before session renewal. A deterministic four-request 401 storm test confirms completion and one shared renewal. Transient retry failures and the one permitted authentication replay use separate budgets.

The public consumption response additionally includes `consumption_kwh`, calculated using Decimal after chronological sorting. This derives a difference under the documented cumulative-register assumption; it is not a new upstream field. Invalid registers stay null, duplicates and decreases suppress deltas with warnings, and the first reading in the filtered slice has no delta. These fault behaviors are simulated offline; they are not claims of observed live resets.


## Derived discovery features

`/api/v1/meters/nearby` computes geographic distance from export coordinates. `/api/v1/overview` aggregates the validated export; neither assumes additional upstream routes. `/api/v1/meta` reports local cache state without probing the portal. Phase, installation type, hierarchy code, and ordering are local query features over the same validated snapshot.


The adapter renews sessions on an observed 401 or login redirect. A 403 is surfaced as an upstream access error rather than assumed to be an expired session; a malformed signature or denied resource is not repaired by repeating login. This distinction is covered by mocked responses. Missing numeric readings are null with explicit warnings, and malformed hierarchy containers fail validation rather than becoming silently empty objects.
