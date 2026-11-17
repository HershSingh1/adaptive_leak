"""
run_on_modelica.py -- run the SAME detectors (thresholds frozen from results/fitted.pkl) on tube runs.

  python modelica/run_on_modelica.py --source ref --days 40          # Python mirror (works anywhere)
  python modelica/run_on_modelica.py --source omc --days 60          # real OpenModelica runs
  python modelica/run_on_modelica.py --source csv --csvdir DIR       # results you already ran with omc
Nothing is re-tuned on Modelica data.
"""
import argparse, os, pickle, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import model as M, tube_reference as tr, modelica_adapter as ad, run_modelica as rm

NAMES = ['A  Night-only level model', 'B  Static physics, calibrated once', 'C  Adaptive, no guardrails',
         'D  Adaptive, all guardrails']


def get_result(scn, source, out, omc):
    if source == 'ref':
        d = tr.make_drivers(scn['settings'], scn['days'], scn['seed'])
        par = tr.modelica_params(scn); os.makedirs(out, exist_ok=True)
        csv = tr.reference_run(par, d, scn['days'] * 86400, os.path.join(out, 'ref.csv'))
    else:
        csv, par = rm.run_omc(scn, out, omc)
    return ad.read_csv(csv), par


def job(args):
    seed, leak, size, days, source, outroot, omc = args
    scn = rm.build_scn(seed, leak, size, days)
    res, par = get_result(scn, source, os.path.join(outroot, f's{seed}_{leak}_{size}'), omc)
    view = ad.to_view(res, scn, par['tau0'], seed)
    guess, cfgs = pickle.load(open(os.path.join(ROOT, 'results', 'fitted.pkl'), 'rb'))
    rows = []
    for nm in NAMES:
        r = M.run(view, cfgs[nm], guess)
        al = r['alarms']; tw = cfgs[nm]['warm'] * 24.0
        rec = dict(seed=seed, leak=leak, size=size, det=nm, windows=len(view['obs']['t']))
        if leak == 'none':
            n = len([1 for a, _ in al if a >= tw]); rec.update(false_alarms=n, fa_per_30d=n / max(days - cfgs[nm]['warm'], 1) * 30)
        else:
            t_l = scn['leak']['start_day'] * 24
            pre = [a for a, _ in al if tw <= a < t_l]; post = [a for a, _ in al if a >= t_l]
            rec.update(false_alarms=len(pre), detected=bool(post), delay_h=(post[0] - t_l) if post else np.nan)
        rows.append(rec)
    return rows


if __name__ == '__main__':
    from multiprocessing import Pool
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default='ref', choices=['ref', 'omc']); ap.add_argument('--days', type=int, default=40)
    ap.add_argument('--seeds', type=int, default=3); ap.add_argument('--omc', default='omc')
    ap.add_argument('--out', default=os.path.join(HERE, 'runs'))
    a = ap.parse_args()
    cases = [(s, 'none', 0.0) for s in range(1, a.seeds + 1)]
    cases += [(s, lk, sz) for s in range(1, a.seeds + 1) for lk, sz in [('ramp', 0.3), ('creep', 0.3), ('ramp', 0.1)]]
    jobs = [(s, lk, sz, a.days, a.source, a.out, a.omc) for s, lk, sz in cases]
    with Pool(2) as p:
        rows = [r for rr in p.map(job, jobs) for r in rr]
    df = pd.DataFrame(rows); df.to_csv(os.path.join(HERE, 'modelica_results_%s.csv' % a.source), index=False)
    null = df[df.leak == 'none'].groupby('det').agg(runs=('seed', 'nunique'), false_alarms=('false_alarms', 'sum'), fa_per_30d=('fa_per_30d', 'mean'))
    lk = df[df.leak != 'none'].groupby(['leak', 'size', 'det']).agg(runs=('seed', 'count'), detected=('detected', 'mean'), median_delay_h=('delay_h', 'median'), false_alarms=('false_alarms', 'sum'))
    print('\nNULL RUNS (no leak)\n', null.round(2).to_string(), '\n\nLEAK RUNS\n', lk.round(2).to_string())
