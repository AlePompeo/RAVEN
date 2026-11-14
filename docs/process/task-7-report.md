<!-- SPDX-License-Identifier: Apache-2.0 -->
# Task 7 report
Status: DONE. API (app/security/routes), build_app in bootstrap, TelemetryHub + SSE + CSV replay.
Tests: tests/backend/api (test_api.py, test_telemetry_hub.py). Real bug found by test: 422 with NaN input crashed serialization -> custom RequestValidationError handler.
Notes: rate limit per peer IP (X-Forwarded-For ignored), /health exempt, ENV/CORS_ORIGINS/RATE_LIMIT_PER_MIN/TELEMETRY_CSV read at build time.

## Fix round 1
LRU rate-limit eviction, opt-in TRUSTED_PROXY=1 (otherwise limit is global behind a proxy), OPTIONS not counted; SSE cap TELEMETRY_MAX_SUBSCRIBERS -> 503; env parsing via env_positive_int -> SystemExit with clear message from build_app; /api/plugins errors only dir name + class name; BodySizeLimitMiddleware (MAX_BODY_BYTES, 413, Content-Length + streaming; replaces app's 400 when body read is aborted); input keys 1..64 chars; invalid TELEMETRY_CSV logged and skipped; CSV loop sleeps per pass; no module-level `app` (Makefile dev uses `uvicorn --factory backend.bootstrap:build_app`). Tests: tests/backend/api/test_hardening.py.

## Fix round 2
SSE cap atomic: hub.subscribe() raises TooManySubscribers (check+subscribe synchronous), handler subscribes before StreamingResponse -> 503; generator only unsubscribes in finally (plus idempotent BackgroundTask safety net). Tests: hub-level and endpoint-level concurrent connects (7 vs cap 3 -> exactly 3x200, 4x503).

## Fix round 3
SSE slot reclaimed regardless of response lifecycle: _LeasedStreamingResponse.__call__ try/finally unsubscribes (replaces BackgroundTask). Test simulates send() raising OSError before the generator starts (red first: count stayed 1). Hub concurrency test made genuinely interleaved (sleep(0) before/after subscribe).

## CSV replay contract fix
csv_replay now maps columns to contracts/telemetry.schema.json (strings for t_utc/site_id/schema_version, floats, nested sun_/earth_ az_deg/el_deg), synthesises t_utc (UTC Z) / site_id (TELEMETRY_SITE_ID, default demo) / schema_version, validates with backend.contracts_models.Telemetry (no new runtime dep), drops invalid rows with log + hub.invalid_rows. Shared fixture: contracts/examples/telemetry.sample.json. Tests: tests/backend/api/test_csv_replay.py (red first: 13 failed).
