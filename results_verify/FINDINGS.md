# Findings (hand-written summary of `verify_summary.md`; numbers come from that file)

Thresholds were frozen from train/tune seeds before any test run (commit "Freeze thresholds ..."). 300 clean test runs,
30-tube slow-leak sweep, all seeds fixed.

1. **Calibration did not carry over to new tubes for the adaptive detectors.** Target was 1 false alarm per 30 days.
   On 300 clean test runs: A 0.74, B 0.23, F0 0.56, F1 0.65 (at or under target); **D 1.69 [1.58, 1.81]**, C 3.03,
   D-ablations 1.6 to 2.3. Under the plan's loose P1 rule (Wilson upper bound of "any alarm in 30 days" <= 0.80) all but C pass, so P1 "PASS" for D
   means "not terrible", not "on target".
2. **Slow-leak detection by D is mostly not distinguishable from chance at the slowest rates.** Leak-free twins of the same tubes
   raise an alarm inside the window 53% to 93% of the time for D. Above the twin, D's gain is 0.47 [0.30, 0.63] at the fastest
   leak and 0.07 [0.00, 0.17] at the slowest (0.0009 Pa/h/day). Plan criterion P2 passes for D only at the three fastest rates.
3. **Against the non-adaptive baselines, D shows no difference once chance is removed.** Plan criterion P3 prints "D better" at every
   rate, but only because D detects more in leak-free twins too. Above the twin, D minus F0/F1 has intervals that include 0 at every rate.
   F0/F1 miss about half of the leaks in every cell; D and B alarm more often.
   B (static physics) had the largest above-twin detection at slow rates (0.47 [0.30, 0.63] at 0.0009), with the fewest clean false alarms (0.23 per 30 d),
   but its tuned threshold h = 54.5 sits at the top of the search grid (55).
4. **Guardrails.** No guardrail met the plan's INERT rule. Removing pause, slow learning, bounds, frozen copy or hold test each raised clean
   false alarms (+0.05 to +0.25 in window fraction, intervals exclude 0) with no detection gain at any rate. Caveat: each ablation was
   calibrated separately, so thresholds differ across rows.
   Within that, **the frozen-copy channel is effectively broken as calibrated**: for D and five other detectors its threshold `h_d` landed on the
   grid ceiling (100), i.e. no tested value met its false-alarm budget, and it still raised 16 alarms on the 300 clean runs of D.
5. **Limits.** 30 tubes per sweep cell; intervals are about +/-0.15. Detector and simulator share equations.
