<!-- SPDX-License-Identifier: Apache-2.0 -->
# Task 11 report

Status: DONE_WITH_CONCERNS. Commit 99de35d `feat(frontend): charts and lazy viewport port`.

Tests: vitest 10 files / 70 tests pass; svelte-check 0 errors 0 warnings; build OK; check-bundle OK (51006 B raw vs threshold 64000 B; negative test with three in the initial path fails as expected).

Deps (exact, MIT, no engines declared, npm audit 0): three 0.186.1, uplot 1.6.32, @types/three 0.186.0 (dev). Recorded in docs/versions.md together with the bundle measurement.

Not run in a browser: the real WebGL render, uPlot rendering, ResizeObserver, matchMedia reduced-motion, keyboard/screen-reader behaviour, and a real EventSource against the backend were NOT exercised. Only jsdom (WebGL fallback path via mocked getContext) and a fake EventSource were tested.

## Fix round 1
parseSample now validates the real contract (semver schema_version, required t_utc/site_id/power_w, optional link_margin_db/sun/earth, finite numbers); contract test reads contracts/examples/telemetry.sample.json. check-bundle uses the Vite manifest (build script now `vite build --manifest`) plus index.html script/preload/absolute URLs; negative-tested (html preload of three, manifest import of three). Backoff jitter (injectable random); stop() no longer sets state; status text constant across retries. Telemetry chart: role=group + aria-describedby caption. Viewer: reactive reduced-motion with cleanup, non-live description, debounced polite announcer on user actions. Added @types/node 20.19.43 (MIT, audit 0). Results: vitest 13 files / 99 tests, svelte-check 0/0, build OK, check-bundle OK (51014 B).

## Fix round 2
parseSample now mirrors the schema strictly (additionalProperties false at top level and sun/earth, site_id minLength 1, schema pattern, RFC 3339 date-time with timezone and range checks); schema-driven Vitest negative cases read contracts/telemetry.schema.json. check-bundle logic moved to scripts/bundleCheck.mjs (pure analyzeBundle/htmlScripts, both quote styles and unquoted attributes) with committed Vitest tests (clean pass, static three import, absolute-URL modulepreload, single-quoted attrs, budget, missing chunk, code-marker). threeViewport already listened to matchMedia change (it re-read `reduced` each frame); this is now proven by a test with fake matchMedia/rAF/renderer via exported createThreeViewport (stop/restart on change, no loop if reduced at mount, dispose removes listener and cancels frame). Results: vitest 15 files / 118 tests, svelte-check 0/0, build OK, check-bundle OK (51014 B). Still not run in a browser.
