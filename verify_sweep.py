"""
verify_sweep.py -- slow-leak sweep with frozen thresholds. 30 tubes (seeds 51000..51029), 180 days, creeping
leak of final size 0.10 Pa/h starting day 20, growth over creep_days in {2,7,14,28,56,112}; plus one leak-free
twin per tube (chance baseline). Output: results_verify/raw_sweep.csv with every alarm time per run x detector.

    python verify_sweep.py
"""
import time
import pandas as pd
from multiprocessing import Pool
import verify_common as V
from truth_sim import make_scenario


def job(args):
    seed, cd = args                                  # cd = None -> leak-free twin
    leak = None if cd is None else dict(type='creep', size=V.LEAK_SIZE, creep_days=float(cd), start_day=V.LEAK_START_DAY)
    scn = make_scenario(seed, 'test', days=V.SWEEP_DAYS, leak=leak)
    _, v = V.sim_view(scn)
    recs = []
    for nm, cfg in V.G['cfgs'].items():
        r = V.F.run_any(v, cfg, V.G['guess'])
        al = [(a, k) for a, k in r['alarms'] if a >= cfg['warm'] * 24.0]
        recs.append(dict(seed=seed, creep_days=-1 if cd is None else cd, name=nm, n_total=len(al), alarms=V.alarm_str(al)))
    return recs


def main():
    guess, cfgs = V.load_frozen()
    t0 = time.time()
    jobs = [(s, cd) for s in V.SWEEP_SEEDS for cd in [None] + V.CREEP_DAYS]
    with Pool(V.WORKERS, initializer=V.init_worker, initargs=(guess, cfgs)) as pool:
        res = pool.map(job, jobs, chunksize=1)
    pd.DataFrame([r for rr in res for r in rr]).to_csv(V.OUT + '/raw_sweep.csv', index=False)
    print('sweep done: %d runs x %d detectors in %.0fs' % (len(jobs), len(cfgs), time.time() - t0))


if __name__ == '__main__':
    main()
