<!-- SPDX-License-Identifier: Apache-2.0 -->
# Task 12 report

Status: DONE (with concerns). Commit: 9a41c50 feat(frontend): chat, sims, legal pages and consent module.

Tests: vitest 8 files / 53 tests pass (includes others' files); svelte-check 0 errors (2 a11y warnings in pages/viewer/Viewer.svelte, not mine); npm run build OK.

Delivered: shell/consent.ts (+test, ConsentSettings.svelte), pages chat (sse.ts, api.ts, Chat.svelte), sims (api.ts, Sims.svelte), privacy, cookies, licenses (api.ts), public/licenses.json = [] placeholder.

Concerns:
- Nothing was run in a browser: Svelte components (Chat, Sims, Licenses, legal pages, ConsentSettings) are only compiled/type-checked; only pure TS modules are unit-tested.
- /api/plugins exposes no input schema, so the sims form uses user-editable name/value rows of numeric inputs (default row "x"), not a schema-generated form.
- "Local stub" provider = hardcoded LOCAL_PROVIDERS = ['echo-llm'] in chat/api.ts; any other provider shows the external-service notice.
- licenses.json format assumed: array of {name, version, license}; Task 13 CI must produce it. Absent/non-JSON/empty -> friendly empty state.
- Existing nav shows Privacy/Cookie/Licenze entries (order 90-92) via navLabel.
- frontend/package.json and package-lock.json show modifications in the worktree from the other agent; not touched or committed by me.

## Fix round 1
All 8 findings addressed in one commit (see git log, "fix(frontend): chat/sims a11y, consent hardening and SSE parser limits").
Tests: vitest 13 files / 99 tests pass (jsdom component tests via @testing-library/svelte). svelte-check: 0 errors in my files; 3 errors remain in pages/telemetry/telemetry.test.ts (other agent: missing node types). Build OK.
Notes: sims name "__proto__" rejected, "toString"/"constructor" accepted (own props). Licenses distinguishes ok/empty/absent(404)/error. loadScript: https or same-origin only, optional allowedHosts and integrity, CSP must allow hosts (documented in cookies page). Component tests run in jsdom only; still no real browser/screen-reader run.

## Fix round 2
Revoke now fails safe: session-level revoke (no new scripts, script tags removed) even if persistence fails, returns false; UI shows stored state and an explicit "revoca NON salvata, consenso potrebbe essere ancora attivo" status. SSE: empty chunk no longer resets CRLF state. vitest 13 files / 102 tests pass; svelte-check 0 errors; build OK. jsdom only, no real browser.

## Fix round 3
Explicit message when a grant fails while stored consent is still true (states exact session isGranted result). Note: that branch is not reachable via the checkbox (it shows checked, so a click is a revoke); covered at module level plus a two-failed-revokes component test. vitest 14 files / 115 tests; svelte-check 0 errors; build OK.
