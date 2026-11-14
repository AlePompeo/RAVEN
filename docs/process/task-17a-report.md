<!-- SPDX-License-Identifier: Apache-2.0 -->
# Task 17a report (steps 1-4)

Status: DONE_WITH_CONCERNS. Commits: 54017b7 (steps 1-3), 3644984 (step 4 + docs).
Tests: 485 passed, 49 skipped (full suite); ruff check, mypy strict, lint-imports (2 contracts), contracts/gen.py --check all clean.

Delivered: ports Predictor/Trainer/ModelRegistry, kinds model/trainer/environment, core forbidden-ML contract
(include_external_packages = True added to .importlinter), FileModelRegistry (ONNX, sha256, atomic, regex ids,
human-gated promote, rollback), predictor_baseline + trainer_baseline, TrainerRunner + worker + /api/train,
/api/jobs/{id}, /api/jobs/{id}/cancel, docs/ml.md, docs/versions.md, extra [ml] in pyproject.

Concerns: see final message.

## Fix round 1 (commit 893112d)
All 7 important findings and the minor items fixed; details in docs/ml.md "Indurimento".
Full suite without tests/backend/pipeline (other agent's in-flight work): 533 passed, 49 skipped, 3 consecutive runs, no flakiness.
ruff/mypy/lint-imports/gen.py clean for my files; remaining ruff/mypy errors are in backend/pipeline (not mine).
Residual: killpg after leader exit has a theoretical pid-reuse window; stat-fingerprint cache misses a rewrite that preserves inode/size/mtime/ctime.

## Fix round 2
See final message of round 2: killpg only for live leader, getppid check in boot, card-then-stack promote with retrying readers, promoted_snapshot (single verified read), plugin registry cache and error mapping, docs on anonymous flood. 542 passed, 49 skipped x2 (pipeline excluded).
