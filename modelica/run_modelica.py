"""
run_modelica.py -- run TubeStudy.Tube with OpenModelica (omc) for one truth-sim scenario.

  python run_modelica.py --seed 5 --leak ramp --size 0.1 --days 60 --out runs/s5_ramp
Writes drivers.txt, run.mos, result CSV into --out.  Needs `omc` on PATH (or --omc /path/to/omc).
"""
import argparse, os, subprocess, sys, shutil
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import truth_sim as ts, tube_reference as tr

VARS = 'Pg|pumpOnReal|nPumpsReal|Tsensor|Tamb|podsOut|leakTotal|Tgas'


def build_scn(seed, leak, size, days, split='test', **kw):
    lk = None if leak in (None, 'none') else dict(type=leak, size=size)
    return ts.make_scenario(seed, split, leak=lk, days=days, **kw)


def run_omc(scn, out, omc='omc', tol=1e-7):
    os.makedirs(out, exist_ok=True)
    d = tr.make_drivers(scn['settings'], scn['days'], scn['seed'], path=os.path.join(out, 'drivers.txt'))
    par = tr.modelica_params(scn)
    ov = ','.join('%s=%s' % (k, repr(float(v)) if k != 'L' else float(v)) for k, v in par.items())
    shutil.copy(os.path.join(HERE, 'TubeStudy.mo'), out)
    mos = f'''loadModel(Modelica); getErrorString();
loadFile("TubeStudy.mo"); getErrorString();
simulate(TubeStudy.Tube, startTime=0, stopTime={scn['days'] * 86400}, numberOfIntervals={scn['days'] * 144},
         tolerance={tol}, method="dassl", outputFormat="csv", fileNamePrefix="tube",
         variableFilter="{VARS}", simflags="-override={ov}");
getErrorString();
'''
    open(os.path.join(out, 'run.mos'), 'w').write(mos)
    r = subprocess.run([omc, 'run.mos'], cwd=out, capture_output=True, text=True, timeout=7200)
    open(os.path.join(out, 'omc.log'), 'w').write(r.stdout + '\n' + r.stderr)
    csv = os.path.join(out, 'tube_res.csv')
    if not os.path.exists(csv):
        raise RuntimeError('omc produced no result; see %s/omc.log\n%s' % (out, r.stdout[-1500:]))
    return csv, par


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=5); ap.add_argument('--leak', default='none')
    ap.add_argument('--size', type=float, default=0.1); ap.add_argument('--days', type=int, default=60)
    ap.add_argument('--out', default='runs/run'); ap.add_argument('--omc', default='omc')
    a = ap.parse_args()
    print(run_omc(build_scn(a.seed, a.leak, a.size, a.days), a.out, a.omc)[0])
