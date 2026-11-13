"""
verify_clean.py -- 300 clean test runs (seeds 50000..50299), every detector, frozen thresholds.
No calibration code is called here. Output: results_verify/raw_clean.csv (one row per run x detector).

    python verify_clean.py
"""
import time
import pandas as pd
from multiprocessing import Pool
import verify_common as V
from truth_sim import make_scenario


def job(seed):
    scn = make_scenario(seed, 'test', days=V.CLEAN_DAYS)          # all six hidden effects on, unseen materials
    _, v = V.sim_view(scn)
    recs = []
    for nm, cfg in V.G['cfgs'].items():
        r = V.F.run_any(v, cfg, V.G['guess'])
        al = [(a, k) for a, k in r['alarms'] if a >= cfg['warm'] * 24.0]
        rec = dict(seed=seed, name=nm, days_eval=V.CLEAN_DAYS - cfg['warm'],
                   n_total=len(al), n_win=sum(1 for a, _ in al if V.WIN[0] <= a < V.WIN[1]),
                   alarms=V.alarm_str(al))
        for ch in ('cusum', 'frozen', 'verify'):
            rec['n_' + ch] = sum(1 for _, k in al if k == ch)
        recs.append(rec)
    return recs


def main():
    guess, cfgs = V.load_frozen()
    t0 = time.time()
    with Pool(V.WORKERS, initializer=V.init_worker, initargs=(guess, cfgs)) as pool:
        res = pool.map(job, V.CLEAN_SEEDS, chunksize=2)
    df = pd.DataFrame([r for rr in res for r in rr])
    df.to_csv(V.OUT + '/raw_clean.csv', index=False)
    print('clean runs done: %d runs x %d detectors in %.0fs' % (len(V.CLEAN_SEEDS), len(cfgs), time.time() - t0))


if __name__ == '__main__':
    main()
