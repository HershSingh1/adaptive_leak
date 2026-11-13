"""
verify_fit.py -- stage 1 of the frozen protocol. Fits everything on TRAIN and TUNE seeds only:
starting-guess model, learning rate / pause level (same grid and rule as run_experiments.py),
CUSUM thresholds for every detector (1 false alarm / 30 d target), and h for baseline F1.
Never touches a verify (test) seed. Writes results_verify/{fitted.pkl (ignored), thresholds.json, seeds.json}.
Commit thresholds.json BEFORE running verify_clean.py / verify_sweep.py.

    python verify_fit.py
"""
import time, pickle, json
import numpy as np, pandas as pd
from multiprocessing import Pool
import verify_common as V
import fixed_cusum as F
import run_experiments as RE            # imported, not modified; only its helper functions are used
import model as M
from truth_sim import make_scenario


def f1_job(seed):
    scn = make_scenario(seed, 'tune')
    _, v = V.sim_view(scn)
    t, z, mask = F.fixed_z(v, 10.0)
    return t, z, mask, v['days']


def main():
    assert not (set(V.TRAIN_SEEDS + V.TUNE_SEEDS) & set(V.CLEAN_SEEDS + V.SWEEP_SEEDS))
    t0 = time.time()
    log = lambda *a: print('[%5.0fs]' % (time.time() - t0), *a, flush=True)
    W = V.WORKERS
    with Pool(W) as pool:
        out = pool.map(RE.corpus_job, V.TRAIN_SEEDS, chunksize=8)
    guess = M.Guess().fit([o[0] for o in out], [o[1] for o in out])
    log('starting-guess model fitted on', len(V.TRAIN_SEEDS), 'train tubes')

    cfgs = {k: dict(v) for k, v in M.CONFIGS.items()}
    tune = V.TUNE_SEEDS
    n_leak, n_ev = 30, 25                       # same as the full run in run_experiments.py
    best, rows = None, []
    nm = 'D  Adaptive, all guardrails'
    for rho, pz in [(r, p) for r in (0.001, 0.003, 0.01, 0.03) for p in (0.25, 0.5)]:
        cfgs[nm] = dict(M.CONFIGS[nm], rho=rho, pause=pz)
        with Pool(W, initializer=RE._init, initargs=(guess, cfgs)) as pool:
            c, _ = RE.calibrate(nm, cfgs, guess, tune[:max(24, len(tune) // 2)], pool)
        cfgs[nm] = c
        with Pool(W, initializer=RE._init, initargs=(guess, cfgs)) as pool:
            jobs = [dict(tag='tune_creep', names=[nm], twin=False,
                         scn=make_scenario(21000 + i, 'tune', days=120, leak=dict(type='creep', size=0.10, start_day=20.0)))
                    for i in range(n_leak)]
            rr = RE.run_jobs(pool, RE.score_job, jobs)
            ev_jobs = [dict(tag='tune_ev', names=[nm], twin=False,
                            scn=make_scenario(22000 + i, 'tune', event=dict(type=['seal_swap', 'outdoor_move'][i % 2])))
                       for i in range(max(8, n_ev * 2))]
            fa_ev = np.mean([r['fa_week_after'] for r in RE.run_jobs(pool, RE.score_job, ev_jobs)])
        det = np.mean([r['detected'] for r in rr])
        dl = np.nanmedian([r['delay_h'] for r in rr]) / 24
        rows.append(dict(rho=rho, pause=pz, h=c['h'], detect_rate=det, median_delay_days=dl, fa_week_after_change=fa_ev))
        score = det - 0.01 * (dl if np.isfinite(dl) else 100) - 0.1 * fa_ev
        if best is None or score > best[0]:
            best = (score, rho, pz)
        log('rho=%g pause=%g  score=%.3f' % (rho, pz, score))
    rho, pz = best[1], best[2]
    log('chosen on tune split: rho=%g pause=%g' % (rho, pz))
    for k in cfgs:
        if k.startswith('D'):
            cfgs[k]['rho'] = 0.1 if 'fast' in k else rho
            if cfgs[k]['pause'] is not None:
                cfgs[k]['pause'] = pz

    for k in list(M.CONFIGS):
        with Pool(W, initializer=RE._init, initargs=(guess, cfgs)) as pool:
            c, _ = RE.calibrate(k, cfgs, guess, tune, pool)
        cfgs[k] = c
        log('calibrated %-36s h=%.2f h_d=%.2f c_v=%.2f' % (k, c['h'], c['h_d'], c['c_v']))

    # baselines: F0 keeps h=5.0 untouched; F1 gets h from the tune split
    with Pool(W) as pool:
        fz = pool.map(f1_job, tune, chunksize=4)
    rates = []
    for h in RE.H_GRID:
        r = [len(M.cusum_alarms(np.nan_to_num(z), m, t, h)) / max(d - 10.0, 1) * 30 for t, z, m, d in fz]
        rates.append(np.mean(r))
    h1 = RE.pick(np.array(rates), RE.H_GRID, RE.FA_TARGET)
    cfgs[F.F0] = dict(F.FIXED_CONFIGS[F.F0])
    cfgs[F.F1] = dict(F.FIXED_CONFIGS[F.F1], h=h1)
    log('baseline F0 h=5.0 (a priori); F1 tuned h=%.2f; tune FA/30d by h:' % h1, np.round(rates, 2).tolist())

    pk = V.OUT + '/fitted.pkl'
    pickle.dump((guess, cfgs), open(pk, 'wb'))
    det = {}
    for k, c in cfgs.items():
        det[k] = dict(h=float(c['h']), h_d=float(c['h_d']) if c.get('h_d') is not None else None,
                      c_v=float(c['c_v']) if c.get('c_v') is not None else None,
                      rho=float(c['rho']) if c.get('rho') is not None else None,
                      pause=float(c['pause']) if c.get('pause') is not None else None)
    json.dump(dict(fitted_pkl_sha256=V.sha256(pk), chosen_rho=rho, chosen_pause=pz, detectors=det,
                   tune_grid=rows, fa_target_per_30d=RE.FA_TARGET), open(V.OUT + '/thresholds.json', 'w'), indent=1)
    json.dump(dict(train=[V.TRAIN_SEEDS[0], V.TRAIN_SEEDS[-1]], tune=[V.TUNE_SEEDS[0], V.TUNE_SEEDS[-1]],
                   verify_clean=[V.CLEAN_SEEDS[0], V.CLEAN_SEEDS[-1]], verify_sweep=[V.SWEEP_SEEDS[0], V.SWEEP_SEEDS[-1]],
                   tune_extra=dict(creep=[21000, 21029], events=[22000, 22049]), bootstrap_seed=12345,
                   gbr_cv_random_state=0, note='scenario RNG = SeedSequence([seed,1]) inside truth_sim.make_scenario'),
              open(V.OUT + '/seeds.json', 'w'), indent=1)
    log('done; thresholds.json written')


if __name__ == '__main__':
    main()
