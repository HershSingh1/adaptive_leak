# OpenModelica tube study (branch suggestion: `verify/openmodelica`, new files only)

| File | What it is |
|---|---|
| `TubeStudy.mo` | `TubeStudy.Tube`: 10 viscous-flow segments, gas-temperature lag, permeation + 2 outgassing sources + pods + vent humidity, hysteresis pump (97/103 Pa, gauge at far end), 4 leak types, leak position |
| `run_modelica.py` | Builds drivers.txt + run.mos, calls `omc`, returns the result CSV |
| `tube_reference.py` | Weather/pod drivers, scenario -> parameter mapping, Python mirror of the same ODEs |
| `modelica_adapter.py` | Gauge hardware (noise, drift, tempco, glitches) + pump-off windowing -> detector `view` |
| `run_on_modelica.py` | Runs detectors A-D with thresholds frozen from `results/fitted.pkl` |

## Run
    omc --version                                   # OpenModelica 1.22+ with MSL 4.x
    python modelica/run_on_modelica.py --source omc --days 60 --seeds 10
    python modelica/run_on_modelica.py --source ref --days 40 --seeds 3     # no omc needed

## Check the model before trusting it
1. Open `TubeStudy.mo` in OMEdit, check the model, fix any syntax the compiler flags (it was never compiled in the authoring sandbox).
2. Sealed tube: set Cperm=q300=gammaPod=secondFrac=0, Sgain=0, drive Tamb with a 5 K ramp -> rise must equal P*dT/T (gas law).
3. Compare `--source ref` and `--source omc` CSVs for one seed; Pg should agree to ~0.05 Pa.
4. Blind test: Melody picks leak type/size/start, runs `run_modelica.py`, sends only the CSV; detector must call it.

## Limits
- Equations are ours (same author as the detector), so this adds a different solver/structure (segments, flow, pump dynamics, thermal lag), not independent physics.
- Viscous-flow formula assumed valid at ~100 Pa for a >1 m tube; tube length 5 km, 10 segments are placeholders.
- Hold-test guardrail is inactive here (no hold data); gauge effects live in the adapter, not the model.
- Not a substitute for bench data.
