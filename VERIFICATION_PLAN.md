# Verification plan (written before any verification run)

Branch `verify/stats-hardening`. Purpose: re-test the detectors with more clean runs, honest confidence
intervals, a slow-leak sweep, and a non-adaptive baseline. `truth_sim.py`, `model.py`, `run_experiments.py`
and `analyze.py` are **not modified**; everything is in new files.

## 1. Frozen-split protocol

| Split | Seeds | Used for |
|---|---|---|
| train | 10000 .. 10239 (240 tubes, split `train`) | starting-guess model (same as `run_experiments.py`) |
| tune  | 20000 .. 20079 (80 tubes, split `tune`) | thresholds, learning rate, pause level |
| **verify-clean (test)** | **50000 .. 50299** (300 tubes, split `test`, 60 d) | clean false-alarm runs |
| **verify-sweep (test)** | **51000 .. 51029** (30 tubes, split `test`, 180 d), reused for every growth rate | slow-leak sweep and leak-free twins |

- The verify seeds are disjoint from every seed used by `run_experiments.py` (10000-10239, 20000-22xxx, 30000-36xxx),
  so none of these scenarios has been looked at before.
- Order of work: (a) `verify_fit.py` fits on train/tune only and writes `results_verify/thresholds.json`
  (all thresholds, `rho`, `pause`, plus the SHA-256 of `results/fitted.pkl`). This file is **committed before any
  test run**. (b) The test scripts load the fitted object, refuse to run if its hash differs from `thresholds.json`,
  and never call any calibration function.
- After test results exist: **no threshold, learning rate, pause level, guardrail setting, seed list or metric
  definition is changed.** If a bug in the harness forces a rerun, the bug and the rerun are logged in section 7;
  the fitted thresholds stay as committed.
- All randomness is seeded: scenario seeds above; bootstrap seed 12345; any model-internal RNG is checked and
  recorded in `results_verify/seeds.json`.

## 2. Detectors

The 11 detectors in `model.CONFIGS` (A, B, C, D, D- no pause, D- fast learning, D- no bounds, D- no frozen copy,
D- no hold test, D cold start, D datasheet-only start), plus two new non-adaptive baselines in `fixed_cusum.py`:

- **F0, fixed-threshold CUSUM, a priori h.** z = (rise - mean) / sd, with mean and sd taken once from the first
  10 days. No temperature or traffic model, no re-learning, no recalibration. CUSUM reference k = 0.5,
  **h = 5.0 chosen before any run** (textbook value, not tuned).
- **F1, same statistic, h tuned once on the tune split** to 1 false alarm per 30 days with the same `pick()` rule
  as the other detectors. Fixed afterwards.

Alarms before day 10 (warm-up) are ignored for every detector, as in the existing pipeline.

## 3. Metrics

### M1. False alarms per 30 days (clean runs)
300 clean test runs, 60 days each, all six hidden effects on (as in `E0`). Per detector:
1. **Window fraction with Wilson interval.** Evaluation window = days 10-40 (exactly 30 days). For each run,
   indicator "at least one alarm in the window". Report the fraction with a 95% **Wilson** interval.
2. **Rate per 30 days.** Pooled alarms over days 10-60 divided by pooled days times 30, with an exact (Garwood)
   Poisson 95% interval and a run-level bootstrap 95% interval (alarms cluster inside runs, so the bootstrap is the
   more honest one). Also reported per alarm channel (`cusum`, `frozen`, `verify`).

### M2. Detection delay vs leak growth rate (slow-leak sweep)
Creeping leak, final size 0.10 Pa/h, start day 20, 180-day runs, linear growth over `creep_days` in
{2, 7, 14, 28, 56, 112}, i.e. growth rate 0.050, 0.0143, 0.0071, 0.0036, 0.0018, 0.0009 Pa/h per day.
The same 30 tube seeds are used at every growth rate (paired). For each detector and growth rate:
- detected share (Wilson 95%), delay from leak start to first alarm (median among detected, bootstrap 95%),
- **leak level at first alarm** (Pa/h), which is how large the leak was when it was caught.
- **Chance baseline:** each seed also runs once without a leak (twin). The share of twins with an alarm after day 20
  (and before the same horizon) tells how many "detections" are false alarms by luck.

### M3. Share of slow leaks missed
Missed = no alarm within `creep_days + 30` days of leak start (the leak has had 30 days at full size).
Reported as a share per detector and growth rate with a Wilson 95% interval. A leak detected only by an alarm that a
twin would also have raised is still counted as detected in the table, and the twin chance share is printed next
to it so the reader can discount it.

## 4. Pass criteria (fixed now)

These are reporting rubrics. A detector that fails is reported as failing.

- **P1 clean false alarms.** PASS if the Wilson upper bound of the window fraction is <= 0.80
  (about 1.6 alarms per 30 days if alarms were Poisson). MARGINAL if the point estimate is <= 0.63 (the value a
  budget of exactly 1 per 30 days would give) but the upper bound exceeds 0.80. FAIL if the point estimate exceeds 0.63.
  The tuning target was 1 per 30 days, so a detector whose test rate is well above that has not held its calibration
  on new tubes.
- **P2 slow-leak detection.** At a growth rate, PASS if missed share <= 0.20 **and** the Wilson lower bound of the
  detected share exceeds the Wilson upper bound of the twin chance share. Otherwise FAIL.
- **P3 baseline comparison.** D beats a baseline at a growth rate if the paired bootstrap 95% interval of
  (detected share of D minus detected share of baseline) excludes 0, and D's P1 is not worse than the baseline's.
  If the interval includes 0 the result is reported as "no difference shown".
- **P4 guardrail does nothing.** Each guardrail ablation is compared to D, paired by seed. A guardrail is called
  **inert** if the paired 95% bootstrap intervals for (clean window fraction) and (detected share at every growth
  rate) all include 0. It is called **harmful** if removing it improves both metrics with intervals excluding 0.
  Also reported: how many clean runs have an identical alarm list with and without the guardrail, and the number of
  alarms each channel (`frozen`, `verify`) contributes.

## 5. Outputs

`results_verify/` (CSV raw per-run records, `thresholds.json`, `seeds.json`, `verify_summary.md`).
`results/` from the original pipeline is not overwritten.

## 6. Known limits (stated up front)

- The detector equations share structure with the truth simulator, so this checks statistical honesty and sample
  size, not real-tube performance.
- The tune split is the only place thresholds see data. Test tubes use unseen materials and all hidden effects,
  so some drift between tune and test false-alarm rates is expected and is part of what is being measured.
- 300 runs gives a Wilson interval about +/- 0.05 on a fraction near 0.5. The slow-leak sweep has only 30 tubes per
  rate, so intervals there are wide (about +/- 0.15). Conclusions about differences smaller than that are not supported.

## 7. Deviations log

- 2026-11-13, before test runs: first attempt to run `verify_fit.py` with `python -I` failed on import (isolated mode hides
  neighbouring modules); rerun without `-I`. No data or thresholds involved.
- 2026-11-13, **after results were seen**: `verify_report.py` gained a section "Post-hoc: detection above the leak-free twin".
  Reason: twin alarm shares were high (leak-free runs alarm often over 30-160 day windows), so the plan's P2/P3 "detected"
  share is inflated by false alarms. The section is descriptive only. **No criterion, threshold, seed or earlier verdict was changed.**
  The P3 "D better" verdicts as printed follow the plan's rule and should be read together with this section.
