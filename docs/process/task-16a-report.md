<!-- SPDX-License-Identifier: Apache-2.0 -->
# Task 16a (steps 1 and 3) report

Status: DONE with concerns. Commit 7edb3ef.

- Ports FirmwareSim (async load/step/reset) and Estimator (sync predict/update) in backend/core/ports.py; KINDS += firmware, estimator; bootstrap python: entries work for them, exec: rejected for these kinds.
- imufusion 1.3.3 verified: cp314 manylinux wheel exists, installs and runs on Python 3.14.7, MIT (metadata + LICENSE.md in wheel and sdist). Extra [fusion] = imufusion==1.3.3 + numpy. Notes in docs/versions.md. No fallback filter needed.
- Plugin backend/plugins/estimator_imu (ImuEstimator, kind estimator, Apache-2.0). Gotcha found: Fusion ignores the gyro for the first ~3 s unless skip_startup() is called.
- Tests: 208 passed, 2 skipped; ruff check, mypy strict, lint-imports, gen.py --check all clean.

Concerns
1. state_estimate (state[], covariance[][]) does not match Estimator output (name->value map, no covariance; Fusion yields none). Schema left unchanged; no covariance fabricated. Hence the API endpoint POST /api/estimators/{id}/update was skipped.
2. numpy installed into the shared .venv trips scripts/license_check.py (rc=1, "da rivedere"). Needs `pip:numpy@2.5.4  # ...` in scripts/license_reviewed.txt (outside my allowed paths).
3. Existing `ruff format --check` failures in files not mine (test_smoke, test_manifest_registry, license_check.py, docs md).
4. sdist build not verified in isolation (build deps need network); wheel path is verified.

## Fix: state_estimate matches Estimator output

- Schema: state is name->number map (minProperties 1), state_order optional unique names, covariance optional; semver, date-time, additionalProperties false kept. Squareness/size of covariance cannot be expressed in JSON Schema (documented in the schema description). Python/TS regenerated (gen.py --check clean).
- Tests: positive/negative schema tests and Pydantic model, ImuEstimator output wrapped in a message validates (no covariance). Duplicate state_order is enforced only by the schema, not the generated Pydantic model.
- Endpoint POST /api/estimators/{id}/update added (backend/api/routes.py): body {measurement, dt_s?}; ValueError->422, unknown id or wrong kind->404, 502 on creation failure; one instance per id per app, serialized by a threading.Lock (sync handler in threadpool; an asyncio.Lock would bind to the per-request loops of TestClient). Tests incl. 32 concurrent calls.
- Suite: 240 passed, 2 skipped; ruff/mypy/lint-imports/gen --check clean. scripts/ untouched.

## Fix round 1

- dt atomic: update(measurement, dt_s=None) validates measurement and dt first, applies dt only on success; a 422 with dt_s leaves filter and step unchanged. Estimator Protocol now has update(..., dt_s) and reset(); reset() also clears the step.
- Sessions: optional session (^[A-Za-z0-9_-]{1,64}$, default "default"); instances keyed (id, session), LRU cap ESTIMATOR_MAX_SESSIONS (default 64); POST /api/estimators/{id}/reset.
- Errors: new core InvalidMeasurement(ValueError); only it gives 422 with message; any other exception (incl. foreign ValueError) is logged and returns a generic 502.
- Locks: per-session lock, short guard only for the session dict, registry.create outside locks (first instance wins on a race). Tests: slow session and slow create do not block another session.
- 404 can mean plugin not registered (missing [fusion] extra); noted in manifest.toml.
- Suite: 350 passed, 49 skipped (tree includes other agents files); ruff, mypy, lint-imports, gen --check clean.

## Fix round 2

- In-flight sessions are never evicted: each request takes a lease (users += 1 under the guard) before waiting on the session lock and releases it in finally. Eviction picks the oldest session with users == 0; if the cap is reached and all are in use, 503 "troppe sessioni attive". Tests (threading events, no sleeps): in-flight session survives cap+N new sessions and its state continues (same instance); 503 when all in flight; lease released after 422.
- ImuEstimator commits dt only after a successful AHRS update (test with a fake ahrs raising RuntimeError).
- Suite: 354 passed, 49 skipped; ruff, mypy, lint-imports, gen --check clean.
