# Next steps

1. **Install OpenModelica** (https://openmodelica.org/download) and confirm `omc --version` works in the shell.
2. **Run the omc source:** `python modelica/run_on_modelica.py --source omc --days 20 --seeds 1`.
   - If it fails, read `omc.log` in the run folder (`modelica/runs/...`) and send the first compile error lines.
   - Do not edit `TubeStudy.mo` until the error has been reviewed.
3. **Compare omc against ref.** Once omc runs, repeat with `--days 40 --seeds 2` and check that the NULL and LEAK tables match `RESULTS_ref_run.md`. A mismatch means `TubeStudy.mo` and `tube_reference.py` disagree.
4. **Increase statistical power.** Use more seeds (for example 10 or more) and a longer horizon. With 2 seeds, detection rates are only 0, 0.5 or 1.0 and the false-alarm counts are noisy.
5. **Investigate detector C vs D on null runs.** D (all guardrails) had more null false alarms than C (7 vs 5). Check whether this holds with more seeds.
6. **Open a PR** from `verify/openmodelica` to `main` after steps 2-3 pass. Nothing has been merged.
7. **Housekeeping:** `run_experiments.py --quick` modifies tracked files in `results/`. Restore them before committing, or decide whether those files should stay tracked.
