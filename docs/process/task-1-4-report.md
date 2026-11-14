<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tasks 1-4 report
Status: DONE_WITH_CONCERNS
- Task 1 scaffold (4f7cf55), Task 2 ports/errors (2f1d64d), Task 3 manifest/registry (0680bec), Task 4 subprocess adapter (see git log).
- All dev deps installed on Python 3.14.7 (versions in docs/versions.md).
- Tests: 19 passed; ruff clean; lint-imports 1 kept; mypy strict clean (9 files).
- fspl-c: bin/fspl via `make build-c`, manifest entry `exec:bin/fspl`; the test fixture compiles to a pytest tmp dir.
Concerns / deviations:
- .importlinter uses multi-line list syntax (single-line form broke on import-linter 2.15).
- ruff BLE001 needed a noqa in Registry.discover (intentional broad except).
- Task 2/3 implementation files were written before observing the failing run (Task 1 and 4 failures were observed).
- setuptools packages.find, egg-info/caches added to .gitignore; REUSE.toml minimal.

## Fix round 1
Hardened manifest (timeout_s finite >0, non-empty str fields, utf-8), Registry duplicate rejection, ExecSimulation (input validation, kill+await in finally incl. cancellation, 64 KiB stdout bound, empty/duplicate output keys). New tests in test_hardening.py and test_subprocess_hardening.py. 47 passed; ruff, mypy, lint-imports clean.
