<!-- SPDX-License-Identifier: Apache-2.0 -->
# Task 18a report (steps 1-5, 7)

Status: DONE_WITH_CONCERNS. Commits: 8c017bf (ports + queues), e9b00a7 (rest).
Tests: 763 passed, 49 skipped (full suite; 218 in tests/backend/pipeline). ruff, mypy (52 files), lint-imports, contracts/gen.py --check: all clean.
Wheels: pyarrow 26.0.0 (Apache-2.0) and duckdb 1.5.6 (MIT) exist for cp314; pinned in extra [data]; recorded in docs/versions.md.
Docs: docs/pipeline.md (guarantees, layout, not verified).

Concerns
- Step 9 benchmark not run: no throughput claims.
- TDD: tests written before code for each module; I saw RED only as ImportError/collection failure (modules missing), not assertion failures; two mutation checks (store hidden-file logic, queue lease check) confirmed the tests catch regressions.
- COPY TO onto an already-listed parquet is not blocked by DuckDB (allowed_paths); defence is the constant SQL.
- Query site_id regex is stricter than the contract (any non-empty string).
- schema_version major not checked.
- Single writer per partition assumed (compaction).
- terms_url points to docs/pipeline.md (docs/terms/ is outside the allowed paths).

## Fix round 1

Commits: 1551683 + 822f730 (never lose admitted records), 59606a5 (offload + backoff), 3961d25 (single writer + lineage), c079a76 (CSV incremental, payload cap, clocks, confined queue, query cap).
Process: failing tests written and run red before each theme (test_integrity, test_resilience, test_maintenance, test_ingest_csv_incremental, test_hardening_round1).
Result: full tree pytest x3 = 896 / 896 / 897 passed, 49 skipped; ruff, mypy, lint-imports, gen.py --check clean.
Not fixed / limits: see docs/pipeline.md "Cosa NON e' verificato" (multi-process ingestion with a shared dedup not supported; flock unreliable on network FS; threads cannot be killed, cooperative flag only; persistent infra failure keeps messages queued rather than dead-lettering; *.corrupt files are not auto-deleted; CSV multi-line quoted cells unsupported; incremental CSV state is in memory only).

## Fix round 2

Commits: 8e286e3 (N1+N2), b117ad6 (N3), 6fd73df (N4), 6ff5ad7 (N5 + deterministic tests), 378f740 (docs).
Tests written first and run red per theme. Whole tree minus tests/backend/net (another agent's in-progress, uncollectable files) x3: 929 passed, 49 skipped each; backend ruff/mypy (70 files)/lint-imports/gen.py --check clean.
Not fixed: multi-process ingest writers on one PIPELINE_DIR; CSV state in memory (restart re-reads, raw gets file once more); Parquet files with valid footer but corrupt pages are not detected by the footer check; persistent infra failure is bounded by PIPELINE_MAX_INFRA_RETRIES (dead-letter infra_retry_exhausted).

## Fix round 3

Commits: 3d209c8 (quarantine confirmation), cb64530 (breaker, idempotent raw, cooperative cancel, tests), c123ef0 (docs).
Whole tree minus tests/backend/net x3: 942 passed, 49 skipped each; ruff, mypy backend, lint-imports, gen.py --check clean.
Not fixed: idempotency caches are per process (after restart a redelivery can duplicate raw; clean stays correct); footer-valid-but-page-corrupt files still only caught on a full read; breaker thresholds are per pipeline instance.

## Fix round 4

Commit c04a176. Whole tree minus tests/backend/net x3: 952 passed, 49 skipped each; ruff, mypy backend, lint-imports, gen.py --check clean.
Red evidence: test_round4.py first run failed at collection (missing module), not at assertion level.
Not fixed: caches and breaker state per process; canary proves the clean write path works, not that a given row is acceptable; a thread outliving PIPELINE_SHUTDOWN_WAIT_S can still write late (idempotent by key).
