<!-- SPDX-License-Identifier: Apache-2.0 -->
# Task 16 step 2 (HAL host + servo_ctrl_c) - report

Status: DONE. Commit 87e0469.

Tests: tests/backend/plugins: 94 passed, 47 skipped (plain + ubsan-trap builds pass; asan+ubsan skipped: libasan/libubsan missing). ruff, mypy, lint-imports clean. cppcheck 2.19.1 --enable=all: only unusedFunction on HAL API. Full suite: 14 failures all in tests/backend/api/test_estimators_sessions.py (other agent's untracked work), none in my paths.

Tolerances (in test file with rationale): noise-free steady error < 0.05 deg (obs 1e-5), settle < 0.5 s (obs 0.19), noisy steady error < 1 deg (obs 0.02-0.12, ~2 sigma of 0.55 deg noise), noisy overshoot < 2 deg (obs 0.49), saturation >= 90% steps at setpoint 200 (obs 289/300), anti-windup settle <= 0.6x naive (obs 1.43 vs 4.79 s) and overshoot < 0.5x (12 vs 76 deg).

Extensions to the requested protocol: optional inputs anti_windup, plant_rate_dps; extra output settle_time_s. Makefile: build-c now also runs build-servo.

Not verified: ESP32/Arduino build or run; ASan/UBSan runtime (absent; ubsan-trap used instead); behaviour of other gcc/libm versions; real servo/ADC timing.
