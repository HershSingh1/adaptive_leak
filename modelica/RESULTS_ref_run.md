# Reference-source run results

Command: `python modelica/run_on_modelica.py --source ref --days 40 --seeds 2`
Date: 2026-11-16. Branch: `verify/openmodelica`. Prerequisite: `python run_experiments.py --quick` (created `results/fitted.pkl`, ~230 s).

The `--source ref` run uses `tube_reference.py`, the Python reference of the tube model. It does not use OpenModelica.

## NULL RUNS (no leak)

| Detector | Runs | False alarms | Per 30 days |
|---|---|---|---|
| A: Night-only level model | 2 | 15 | 7.5 |
| B: Static physics, calibrated once | 2 | 8 | 4.0 |
| C: Adaptive, no guardrails | 2 | 5 | 2.5 |
| D: Adaptive, all guardrails | 2 | 7 | 3.5 |

## LEAK RUNS (2 runs per row)

| Leak | Size | Detector | Detected | Median delay (h) | False alarms |
|---|---|---|---|---|---|
| creep | 0.3 | A | 1.0 | 113.79 | 9 |
| creep | 0.3 | B | 1.0 | 108.37 | 4 |
| creep | 0.3 | C | 1.0 | 227.21 | 3 |
| creep | 0.3 | D | 1.0 | 66.37 | 3 |
| ramp | 0.1 | A | 1.0 | 42.21 | 9 |
| ramp | 0.1 | B | 1.0 | 52.37 | 4 |
| ramp | 0.1 | C | 0.5 | 20.53 | 3 |
| ramp | 0.1 | D | 1.0 | 16.37 | 4 |
| ramp | 0.3 | A | 1.0 | 16.87 | 8 |
| ramp | 0.3 | B | 1.0 | 17.04 | 4 |
| ramp | 0.3 | C | 1.0 | 13.96 | 4 |
| ramp | 0.3 | D | 1.0 | 13.96 | 4 |

## OpenModelica run

Not run. `omc --version` returned `command not found`, so OpenModelica is not installed on this machine. `TubeStudy.mo` has not been compiled or simulated, and there is no `omc.log`.

## Caveats

- Only 2 seeds and 40 days, so these counts are noisy. Detection rates are 0, 0.5 or 1.0 only.
- Detector D's false alarms on null runs (3.5 per 30 days) are not clearly better than C's (2.5), so this run does not show a false-alarm benefit from the guardrails.
- Running `run_experiments.py --quick` rewrote tracked files in `results/`. They were restored with `git checkout -- results` and not committed.
