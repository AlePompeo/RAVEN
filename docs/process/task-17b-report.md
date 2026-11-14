<!-- SPDX-License-Identifier: Apache-2.0 -->
# Task 17b (steps 5-6) report

Status: DONE. Commits: 20e5491 (RL, extras, docs), 25eee1c (DL predictor_nn). The Environment port
was already in HEAD (swept into the pipeline agent's ports.py commit); ports.py is unchanged by me now.

Tests: full suite excl. pipeline, run twice: 597 passed, 49 skipped (not mine) each; ruff, mypy
(backend: 64 files), lint-imports (2 kept), gen.py --check all clean.

Feasibility (Py 3.14.7, Linux x86_64): gymnasium 1.4.0 (MIT) and SB3 2.9.0 (MIT) install; torch
2.14.1+cpu cp314 wheel exists on the CPU index (196 MB wheel, ~770 MB installed); PyPI default is
CUDA. onnxscript 0.7.2 (MIT) needed for the dynamo ONNX exporter.

Measured: ARS gain vs best baseline 0.28-0.36 (threshold 0.15), ~1.3 s; PPO 8k steps -2.96 vs P
-3.35 vs zero -37.6 (smoke only); NN skill 0.83 (threshold 0.25), ONNX vs torch 4e-6 (tolerance 1e-4).

Not verified: see docs/ml.md "Sim-to-real e cosa NON e' verificato".

## Fix round 1

Commit: see git log (fix(ml): tuned PD baseline...). Gate now: tuned P/PD grid baseline, 300 paired episodes, paired bootstrap CI (2000, seed fixed), thresholds on gain_ci_low and gain_ci_low_perturbed (+-20% tau/rate), fresh eval seed block per candidate, NN input-domain rejection (min*0.9..max*1.1), FIXED_TEST_SEED rejected in NN.
Finding: tuned PD (kp 45, kd -2) is near-optimal; ARS matches it (gain ~ -0.003), so the example candidate is NOT promotable (0.15 unreachable with linear policy; MLP and v|v| feature attempts also ~0).
Not fixed: predictor_baseline/trainer_baseline seed/domain checks (outside allowed paths); no final independent test set against winners curse.
Tests: 609 passed, 49 skipped x2; ruff/lint-imports/gen.py clean; mypy clean on my files (backend/pipeline/service.py has 2 errors from another agent).

## Fix round 2

Optional ServoPlant nonlinearities (deadband_deg, stiction_dps, backlash_deg; default off), profile servo_realistic (1.0 / 5.0 / 1.0, chosen before comparison, illustrative) used by trainer-rl; perturbation incl. these +-20%; profile recorded in card. predictor_baseline/trainer_baseline: FIXED_TEST_SEED rejected, input-domain check (min*0.9, max*1.1, fail-closed).
Honest RL result: ARS gain_ci_low about -0.003..-0.005 (servo_realistic, seeds 0-2); sensitivity low/high also <= 0 (high: down to -0.024). PPO 200k steps: gain -0.0014 vs tuned PD. Candidates remain unpromotable; gate unchanged.
Tests: 627 passed, 49 skipped (x2); ruff, mypy (65 files), lint-imports, gen.py clean.
