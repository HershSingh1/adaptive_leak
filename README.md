# Adaptive leak detection: synthetic-data simulation

A simulated hyperloop-style glass tube at about 100 Pa, a detector whose model of "normal" keeps re-learning,
and a test bench that checks whether that re-learning helps or lets leaks hide.

## What it does, in plain words
1. **Truth world (`truth_sim.py`).** Simulates a tube with an on/off pump (97-103 Pa). While the pump is off, pressure rises.
   That rise rate (Pa/h) is the signal. It includes the physics the detector models (gas law, outgassing, seal permeation,
   gauge drift, pod traffic) **plus six effects the detector has never seen**: second outgassing source, sunlight and thermal lag,
   vent humidity, seal aging, gauge glitches, wind and rain cooling.
2. **Scenario generator.** Every run draws a random tube (diameter, glass, seals, indoor/outdoor, climate, traffic),
   random true parameters, and optionally a mid-run change (moved outdoors, weather front, seal swap, vent) or a leak
   (sudden, ramp, intermittent, or creeping over 21 days).
3. **Starting-guess model (`model.py`).** Learns "tube settings -> starting parameter values" from 240 synthetic training tubes.
4. **Online model.** A Kalman filter re-tunes four scale factors every observation window, shape parameters are re-fitted every 14 days,
   and CUSUM watches the leftover. Five guardrails: pause learning when the CUSUM score climbs, learn slowly, physical bounds,
   frozen reference copy, periodic 24 h hold test.
5. **Experiments (`run_experiments.py`).** Thresholds are tuned on a separate tune split (about 1 false alarm per 30 days).
   Everything is then scored on a test split with new materials and all six hidden effects.
   The detector only sees pressure rise, temperatures, pod counts, settings, and operator announcements. Never true parameters or leak labels.

## Run it
    pip install numpy scipy scikit-learn pandas matplotlib tabulate
    python run_experiments.py --quick   # about 2 min smoke test
    python run_experiments.py           # about 7 min on 2 cores
    python analyze.py                   # tables -> results/summary.md, figures -> results/*.png

## Detectors compared
A night-only level model (Melody-style, calibrated per tube) | B static physics equation, calibrated once | C adaptive with no guardrails |
D adaptive with all five guardrails | D with each guardrail removed, and D with cold or datasheet-only starts.

## What this can and cannot show
Can show: how the method behaves, which guardrails matter, sensitivity to each hidden effect.
Cannot show: false-alarm rate or smallest detectable leak on a real tube, or that the outgassing and permeation terms describe real glass.
The detector's equation shares its structure with the truth world (same scaling laws), so real bench data is still needed before real-tube claims.
Simulator B (different functional forms, same author) is a partial guard against that; Melody's `leak_sim.py` is the better second simulator.
