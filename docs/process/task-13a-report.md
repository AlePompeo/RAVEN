<!-- SPDX-License-Identifier: Apache-2.0 -->
# Task 13a report (infrastruttura)

Status: DONE_WITH_CONCERNS. Test: 167 passed, 2 skipped; ruff, mypy, lint-imports, gen.py --check OK.

Verificato: docker build (OK, ~46s), container non root (uid 10001), HEALTHCHECK healthy, /health con header,
/ serve il frontend, /licenses.json generato (three, uplot), /api/plugins elenca 4 plugin.
NON verificato: docker compose (plugin compose assente: "unknown command: docker compose"), valkey in esecuzione
(solo manifest dell'immagine valkey/valkey:8.1.4-alpine verificato; licenza BSD-3-Clause da COPYING del ramo 8.1),
esecuzione della sim fspl-c dentro il container, CI GitHub (mai eseguita; i comandi sono provati localmente),
cyclonedx-py provato solo localmente, make dev.

Concerns: (1) una riga + import in backend/api/app.py (non bootstrap/routes) per mount_static; no-op senza STATIC_DIR.
(2) MPL-2.0 flaggati da license_check: certifi, fqdn, pathspec, passati con --reviewed (revisione manuale: file-level, non modificati).
(3) Il bootstrap usa sempre MemoryCache: il profilo valkey non e' usato dall'app.
(4) gen.py --check in CI richiede npm ci prima (json2ts).

## Fix round 1

Commit: see git log (fix(infra): SPA fallback, ...). Tests: 176 passed, 2 skipped; ruff, mypy, lint-imports OK.
Done: SPA fallback + Cache-Control in backend/api/static.py (tests: traversal, symlink, HEAD, POST, /api 404 JSON); license --reviewed-file with eco:name@version, never overrides forbidden, whitespace normalised; CI concurrency, timeouts, prod-only SBOM, SHA-pinning note; compose bind 127.0.0.1 + valkey requirepass note; Dockerfile node:22 (frontend check/test/build/bundle passed in node:22 container); docker build + run OK (/chat 200 no-cache, /api/nope 404 JSON).
Not verified: CI on GitHub; docker compose; CSP in a real browser (13b); reviewed.txt versions drift when CI installs newer pip packages (CI will fail until reviewed); CI still uses Node 20.
