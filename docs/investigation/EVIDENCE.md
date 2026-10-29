# Investigation evidence

Date: 29 October 2026 (Asia/Kolkata).

Evidence was obtained through direct HTTP requests using assignment credentials and static inspection of the browser's publicly delivered JavaScript. No credentials or live session values are retained. The candidate should reproduce these flows in Chrome DevTools and understand the implementation before submission.

1. GET root -> /login. HTML form fields: email/password. POST without Origin was rejected. Same-origin form POST set a secure HttpOnly session cookie and returned a serialized redirect to /meters.
2. Authenticated /meters HTML initially contained an empty table. Its page JS performs `/portal/meters/search?q=...&page=...` on mount.
3. Search page 1 returned 20 rows, total 403. Search for J100000 returned its single matching row.
4. Transformer page JS exposed `/portal/keys` and signed `/portal/export?page=1`. A normal signed export returned 403 records with total 403.
5. `/portal/dts?page=1` returned 20 rows with total 40.
6. J100000 geo returned coordinate strings; energy returned 337 rows. Missing meter energy returned 404. An unauthenticated search returned 401.
7. The implementation's explicit live smoke check verified 403 normalized meters, J100000 detail and 337 readings, 240 hierarchy nodes, and 91 hierarchy warnings.

To reproduce manually: open DevTools Network, enable Preserve log, sign in, inspect Fetch/XHR while opening meters, a meter detail, and transformers; click Export all meters. Review request methods, query strings, response fields, and error statuses. Do not share raw cookies, passwords, signing keys, or unsanitized HAR files. See ../../PROTOCOL.md for exact verified protocol details.

Automated test fixtures combine a representative observed meter/reading with clearly synthetic mutations for fault cases. Test-generated keys and sessions are not real portal secrets.

Follow-up verification: the Python adapter dynamically retrieved all 40 transformer records. Reliability regressions are covered by 43 offline tests, including concurrent expiry and malformed/partial ingestion.

Historical-window verification: J100000 queried with from=2026-06-01,to=2026-06-02 returned 96 rows (01/06/2026 00:00 through 02/06/2026 23:30). Querying June 25 alone returned 48 rows. These were normal authenticated GET requests; no timezone guarantee was present in the payload.
