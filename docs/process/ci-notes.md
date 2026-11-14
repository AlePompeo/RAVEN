<!-- SPDX-License-Identifier: Apache-2.0 -->
# Note sulla CI

Workflow: `.github/workflows/ci.yml` (push, pull_request, workflow_dispatch; `ubuntu-latest`).

## Cosa gira dove

| Job | Cosa fa | Dipendenze installate |
|---|---|---|
| `backend` | `make build-c`, `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, `pytest`, `contracts/gen.py --check`, allowlist licenze, SBOM CycloneDX | `pip install -c constraints/base.txt -e ".[dev,ml,fusion,data]"`; Node serve a `json2ts` |
| `frontend` | `npm run check`, `npm test` (vitest), `npm run build`, `npm run check:bundle` | `npm ci` |
| `e2e` | `make build-c`, build del frontend (`/` e `/app/`), Playwright + axe su Chromium | venv `.venv` con le sole dipendenze di base (il server e2e parte da `.venv/bin/python`) |

## Scelte

- **Extra opzionali.** La CI installa `ml`, `fusion`, `data` (ruote leggere) cosi' mypy e pytest
  eseguono il codice dei plugin numpy/onnx/duckdb/imufusion. Non installa `torch`, `gymnasium`,
  `stable-baselines3` (la ruota PyPI di torch e' di GB). Per loro `pyproject.toml` ha override mypy
  (`ignore_missing_imports`; nei due moduli che sottoclassano tipi torch/gymnasium anche
  `disallow_subclassing_any=false` e `warn_unused_ignores=false`). Il codice passa mypy sia con sia senza
  torch (verificato in due venv). I test che richiedono torch/gymnasium si saltano (`importorskip`).
- **Senza extra.** Con il solo `.[dev]` pytest non fallisce: i test numpy/sklearn/imufusion usano
  `importorskip`, `tests/backend/pipeline/conftest.py` salta i test pyarrow/duckdb in raccolta,
  `test_real_plugins_dir` tollera i plugin con extra mancanti. mypy invece richiede gli extra installati
  (o i relativi stub): non e' supportato senza.
- **Vincoli.** `-c constraints/base.txt` rende la CI riproducibile (stessi pin del Dockerfile). Senza,
  una nuova versione di una dipendenza MPL-2.0 (es. certifi) fa fallire il controllo licenze, che
  accetta revisioni solo per versione esatta (`scripts/license_reviewed.txt`).
- **Binari C.** `fspl` e `servo_ctrl` non sono versionati (`bin/` e' ignorato): `make build-c` va eseguito
  nei job `backend` e `e2e`. Senza, `fspl-c` non compare in `/sims` e i test e2e che lo scelgono vanno in timeout.
- **Test frontend ermetici.** `frontend/src/test-setup.ts` (vitest `setupFiles`) fissa
  `navigator.hardwareConcurrency`, `deviceMemory`, `connection`, `devicePixelRatio`. Senza, il livello di
  qualita' (`viewports/quality.ts`) dipendeva dalla macchina: un runner CI da 2 core dava il livello `lo`
  (DPR massimo 1,5, nessuna parallasse) e due test di `canvas2dViewport` fallivano.
- **Node 22** (come il Dockerfile). Verificato da clone pulito con Node 22.23: frontend check/test/build/bundle e 308 test e2e passano. `engines` resta `>=20.18`.

## Riprodurre in locale

Venv pulito: `python3 -m venv v && v/bin/pip install -c constraints/base.txt -e ".[dev,ml,fusion,data]"`,
poi `make build-c` e i comandi del job. E2E: `E2E_PORT=8010 make e2e` (richiede `make venv`).
