"""
run_experiments.py -- builds the synthetic corpus, trains the starting-guess model,
calibrates thresholds on the TUNE split, then scores every detector on held-out TEST
scenarios (unseen materials + hidden effects never present in train/tune).

    python run_experiments.py            # full run (several minutes on 2 cores)
    python run_experiments.py --quick    # small run for a smoke test
Outputs go to ./results/
"""
import argparse, os, sys, time, json, pickle
import numpy as np
import pandas as pd
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from truth_sim import (make_scenario, simulate, observations, HIDDEN_ALL, HIDDEN_TRAIN, hidden_dict, SPD, DT)
import model as M

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
os.makedirs(OUT, exist_ok=True)
G = {}                                    # per-process globals (guess model + calibrated configs)
FA_TARGET = 1.0                           # false alarms per 30 days, total budget per detector
LEAK_SIZES = [0.05, 0.10, 0.25]           # Pa/h of extra rise


def _init(guess, cfgs):
    G['guess'], G['cfgs'] = guess, cfgs


def sim_view(scn):
    ds = simulate(scn)
    return ds, observations(ds)


# ------------------------------------------------------------------ stage 1: corpus
def corpus_job(seed):
    scn = make_scenario(seed, 'train')
    _, v = sim_view(scn)
    return v['settings'], M.fit_corpus_run(v, None)


# ------------------------------------------------------------------ stage 2: calibration
H_GRID = np.array([0.8, 1.2, 1.7, 2.5, 3.5, 4.5, 6, 8, 10, 13, 17, 22, 30, 40, 55])


def fa_rate(alarms, t0, t1):
    n = sum(1 for a, _ in alarms if t0 <= a < t1)
    return n / max((t1 - t0) / 24.0, 1e-9) * 30.0


def calib_job(args):
    seed, name, h = args
    scn = make_scenario(seed, 'tune')
    _, v = sim_view(scn)
    cfg = G['cfgs'][name]
    r = M.run(v, dict(cfg, frozen=False, verify=False) if cfg['mode'] == 'KF' else cfg, G['guess'], h=h)
    t0 = cfg['warm'] * 24.0
    return dict(fa=fa_rate(r['alarms'], t0, v['days'] * 24.0), n_days=v['days'] - cfg['warm'])


def side_job(args):
    """frozen-copy d-series and hold residuals at the chosen h, for sweeping h_d and c_v."""
    seed, name, h = args
    scn = make_scenario(seed, 'tune')
    _, v = sim_view(scn)
    cfg = G['cfgs'][name]
    r = M.run(v, dict(cfg, frozen=True, verify=True, h_d=1e9, c_v=1e9), G['guess'], h=h)
    return dict(t=r['t'], d=r['d'], hold=r['hold_r'], days=v['days'])


def pick(rates, grid, target):
    """smallest threshold whose mean false-alarm rate is <= target (log-linear interpolation)."""
    rates = np.maximum.accumulate(rates[::-1])[::-1]
    for i, rt in enumerate(rates):
        if rt <= target:
            if i == 0:
                return grid[0]
            r0, r1 = rates[i - 1], max(rt, 1e-3)
            w = (np.log(r0) - np.log(target)) / (np.log(r0) - np.log(r1) + 1e-12)
            return float(grid[i - 1] + w * (grid[i] - grid[i - 1]))
    return float(grid[-1])


def calibrate(name, cfgs, guess, tune_seeds, pool):
    cfg = cfgs[name]
    share_f = 0.25 if cfg.get('frozen') else 0.0
    share_v = 0.15 if cfg.get('verify') else 0.0
    t_main = FA_TARGET * (1 - share_f - share_v)
    jobs = [(s, name, float(h)) for h in H_GRID for s in tune_seeds]
    out = pool.map(calib_job, jobs, chunksize=8)
    n = len(tune_seeds)
    rates = np.array([np.mean([o['fa'] for o in out[i * n:(i + 1) * n]]) for i in range(len(H_GRID))])
    h = pick(rates, H_GRID, t_main)
    new = dict(cfg, h=h)
    if cfg['mode'] == 'KF' and (share_f or share_v):
        sides = pool.map(side_job, [(s, name, h) for s in tune_seeds], chunksize=8)
        if share_f:
            grid = np.array([2, 3, 4, 6, 8, 11, 15, 20, 30, 45, 70, 100.0])
            rt = []
            for g in grid:
                rt.append(np.mean([M.cusum_alarms(np.nan_to_num(x['d']), ~np.isnan(x['d']), x['t'], g, M.K_DIV).__len__()
                                   / max(x['days'] - cfg['warm'], 1) * 30 for x in sides]))
            new['h_d'] = pick(np.array(rt), grid, FA_TARGET * share_f)
        if share_v:
            grid = np.array([1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 14.0])
            rt = [np.mean([sum(1 for _, r in x['hold'] if r > g) / max(x['days'] - cfg['warm'], 1) * 30 for x in sides])
                  for g in grid]
            new['c_v'] = pick(np.array(rt), grid, FA_TARGET * share_v)
    return new, rates


# ------------------------------------------------------------------ stage 3: scoring
def score_job(job):
    """job: dict(kind, scn, names). returns per-detector records."""
    scn = job['scn']
    ds, v = sim_view(scn)
    tw = None
    if job.get('twin'):
        tscn = dict(scn, leak=None)
        _, tw = sim_view(tscn)
    recs = []
    lk, ev = scn['leak'], scn['event']
    for name in job['names']:
        cfg = G['cfgs'][name]
        r = M.run(v, cfg, G['guess'])
        al = r['alarms']
        days = scn['days']
        t_warm = cfg['warm'] * 24.0
        rec = dict(job=job['tag'], name=name, seed=scn['seed'], days=days)
        if lk is not None:
            t_l = lk['start_day'] * 24
            pre = [a for a, _ in al if t_warm <= a < t_l]
            post = [(a, k) for a, k in al if a >= t_l]
            rec.update(fa_pre=len(pre) / max(t_l - t_warm, 1) * 24 * 30,
                       detected=bool(post), delay_h=(post[0][0] - t_l) if post else np.nan,
                       first_channel=post[0][1] if post else '')
            if job.get('twin') and cfg['mode'] == 'KF':
                rt = M.run(tw, cfg, G['guess'])
                tc = post[0][0] if post else days * 24.0 - 1.0
                S_now = float(np.interp(tc, np.arange(len(ds['truth']['leak_series'])) * DT, ds['truth']['leak_series']))

                def lvl(rr, vv):
                    idx = np.where((vv['obs']['t'] <= tc) & ~np.isnan(rr['Lref']))[0][-12:]
                    return np.nanmean(rr['Lref'][idx])
                rec['absorbed'] = (lvl(r, v) - lvl(rt, tw)) / max(S_now, 1e-9)
                rec['leak_at_check'] = S_now
        else:
            rec['fa30'] = fa_rate(al, t_warm, days * 24.0)
            rec['fa_total'] = len([1 for a, _ in al if a >= t_warm])
            for ch in ('cusum', 'frozen', 'verify'):
                rec['fa_' + ch] = sum(1 for a, k in al if a >= t_warm and k == ch) / max(days - cfg['warm'], 1) * 30
            rec['days_eval'] = days - cfg['warm']
            if ev is not None:
                te = ev['day'] * 24
                rec['fa_week_after'] = sum(1 for a, _ in al if te <= a < te + 7 * 24)
                rec['fa_other'] = sum(1 for a, _ in al if t_warm <= a and not (te <= a < te + 7 * 24))
                rec['days_other'] = days - cfg['warm'] - 7
                z, t = r['z'], r['t']
                for lab, (a, b) in dict(z_d0_3=(0, 3), z_d3_7=(3, 7), z_pre=(-14, 0)).items():
                    m = (t >= te + a * 24) & (t < te + b * 24) & ~np.isnan(z)
                    rec[lab] = float(np.sqrt(np.mean(z[m] ** 2))) if m.sum() > 3 else np.nan
        recs.append(rec)
    return recs


def warm_job(job):
    scn = job['scn']
    _, v = sim_view(scn)
    recs = []
    for name in job['names']:
        r = M.run(v, G['cfgs'][name], G['guess'])
        t, e = r['t'], np.abs(r['e'])
        rec = dict(name=name, seed=scn['seed'])
        for lab, (a, b) in dict(d0_1=(0, 1), d1_3=(1, 3), d3_10=(3, 10)).items():
            m = (t >= a * 24) & (t < b * 24)
            rec[lab] = float(np.mean(e[m])) if m.sum() else np.nan
        recs.append(rec)
    return recs


def run_jobs(pool, fn, jobs):
    res = pool.map(fn, jobs, chunksize=4)
    return [r for rr in res for r in rr]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true')
    args = ap.parse_args()
    q = args.quick
    n_train, n_tune, n_clean = (60, 24, 24) if q else (240, 80, 100)
    n_ev, n_leak, n_creep, n_h = (6, 8, 8, 10) if q else (25, 30, 30, 30)
    t0 = time.time()
    log = lambda *a: print('[%5.0fs]' % (time.time() - t0), *a, flush=True)

    # ---- stage 1: corpus + starting-guess model
    with Pool(2) as pool:
        out = pool.map(corpus_job, range(10000, 10000 + n_train), chunksize=8)
    guess = M.Guess().fit([o[0] for o in out], [o[1] for o in out])
    log('corpus done', n_train, 'runs. Ridge CV R2 per parameter:', dict(zip(M.PN, np.round(guess.r2, 2))))
    corpus_tab = pd.DataFrame(dict(param=M.PN, ridge_R2=guess.r2, boosting_R2=guess.r2_gbr,
                                   learned_sd=guess.sd_t, datasheet_sd=guess.nom_sd_t, cold_sd=guess.cold_sd_t,
                                   lo=guess.lo, hi=guess.hi))
    corpus_tab.to_csv(os.path.join(OUT, 'starting_guess_model.csv'), index=False)

    cfgs = {k: dict(v) for k, v in M.CONFIGS.items()}
    tune_seeds = list(range(20000, 20000 + n_tune))

    with Pool(2, initializer=_init, initargs=(guess, cfgs)) as pool:
        # ---- stage 2a: pick learning rate and pause level for the guarded detector on the tune split
        log('tuning learning rate / pause level on the tune split ...')
        best = None
        grid = [(r, pz) for r in (0.001, 0.003, 0.01, 0.03) for pz in (0.25, 0.5)]
        tune_rows = []
        for rho, pz in grid:
            nm = 'D  Adaptive, all guardrails'
            cfgs[nm] = dict(M.CONFIGS[nm], rho=rho, pause=pz)
            _init(guess, cfgs)
            pool.close(); pool.join()
            pool = Pool(2, initializer=_init, initargs=(guess, cfgs))
            c, _ = calibrate(nm, cfgs, guess, tune_seeds[:max(24, n_tune // 2)], pool)
            cfgs[nm] = c
            pool.close(); pool.join()
            pool = Pool(2, initializer=_init, initargs=(guess, cfgs))
            jobs = [dict(tag='tune_creep', names=[nm], twin=False,
                         scn=make_scenario(21000 + i, 'tune', days=120, leak=dict(type='creep', size=0.10, start_day=20.0)))
                    for i in range(n_leak)]
            rr = run_jobs(pool, score_job, jobs)
            ev_jobs = [dict(tag='tune_ev', names=[nm], twin=False,
                            scn=make_scenario(22000 + i, 'tune', event=dict(type=['seal_swap', 'outdoor_move'][i % 2])))
                       for i in range(max(8, n_ev * 2))]
            fa_ev = np.mean([r['fa_week_after'] for r in run_jobs(pool, score_job, ev_jobs)])
            det = np.mean([r['detected'] for r in rr])
            dl = np.nanmedian([r['delay_h'] for r in rr]) / 24
            tune_rows.append(dict(rho=rho, pause=pz, h=c['h'], detect_rate=det, median_delay_days=dl, fa_week_after_change=fa_ev))
            score = det - 0.01 * (dl if np.isfinite(dl) else 100) - 0.1 * fa_ev
            if best is None or score > best[0]:
                best = (score, rho, pz)
        pd.DataFrame(tune_rows).to_csv(os.path.join(OUT, 'tune_learning_rate.csv'), index=False)
        log('chosen rho=%g pause=%g' % (best[1], best[2]), pd.DataFrame(tune_rows).round(2).to_string(index=False))
        rho, pz = best[1], best[2]
        for nm in cfgs:
            if nm.startswith('D'):
                cfgs[nm]['rho'] = 0.1 if 'fast' in nm else rho
                if cfgs[nm]['pause'] is not None:
                    cfgs[nm]['pause'] = pz
        pool.close(); pool.join()

        # ---- stage 2b: calibrate every detector to ~1 false alarm / 30 d on clean tune runs
        calib_log = {}
        for nm in list(cfgs):
            pool = Pool(2, initializer=_init, initargs=(guess, cfgs))
            c, rates = calibrate(nm, cfgs, guess, tune_seeds, pool)
            pool.close(); pool.join()
            cfgs[nm] = c
            calib_log[nm] = dict(h=c['h'], h_d=c.get('h_d'), c_v=c.get('c_v'), fa_grid=list(np.round(rates, 2)))
            log('calibrated %-36s h=%.1f h_d=%.1f c_v=%.1f' % (nm, c['h'], c['h_d'], c['c_v']))
        json.dump(dict(H_GRID=list(H_GRID), cal=calib_log), open(os.path.join(OUT, 'calibration.json'), 'w'), indent=1)
        pickle.dump((guess, cfgs), open(os.path.join(OUT, 'fitted.pkl'), 'wb'))

        pool = Pool(2, initializer=_init, initargs=(guess, cfgs))
        names = list(cfgs)
        main4 = [n for n in names if n[0] in 'ABC' or n.startswith('D  Adaptive')]
        res = {}

        # ---- E0: clean steady test runs (all hidden effects, unseen materials)
        log('E0 clean test runs ...')
        jobs = [dict(tag='E0', names=names, scn=make_scenario(30000 + i, 'test')) for i in range(n_clean)]
        res['E0'] = pd.DataFrame(run_jobs(pool, score_job, jobs))

        # ---- E1: condition changes
        log('E1 condition changes ...')
        jobs = []
        for ei, et in enumerate(['outdoor_move', 'weather_front', 'seal_swap', 'vent']):
            for i in range(n_ev):
                jobs.append(dict(tag='E1_' + et, names=names,
                                 scn=make_scenario(31000 + ei * 100 + i, 'test', event=dict(type=et))))
        res['E1'] = pd.DataFrame(run_jobs(pool, score_job, jobs))

        # ---- E2: leaks by type and size
        log('E2 leaks ...')
        jobs = []
        for ti, lt in enumerate(['sudden', 'ramp', 'intermittent']):
            for si, sz in enumerate(LEAK_SIZES):
                for i in range(n_leak):
                    jobs.append(dict(tag='E2_%s_%.2f' % (lt, sz), names=names,
                                     scn=make_scenario(32000 + ti * 1000 + si * 100 + i, 'test',
                                                       leak=dict(type=lt, size=sz, ramp_h=24.0, pat_seed=i))))
        res['E2'] = pd.DataFrame(run_jobs(pool, score_job, jobs))

        # ---- E3: creeping leaks over weeks (the absorption test), with a leak-free twin
        log('E3 creeping leaks + twins ...')
        jobs = []
        for si, sz in enumerate(LEAK_SIZES):
            for i in range(n_creep):
                jobs.append(dict(tag='E3_%.2f' % sz, names=names, twin=True, check_days=60,
                                 scn=make_scenario(33000 + si * 100 + i, 'test', days=120,
                                                   leak=dict(type='creep', size=sz, creep_days=21.0, start_day=20.0))))
        res['E3'] = pd.DataFrame(run_jobs(pool, score_job, jobs))

        # ---- E4: hidden effects one at a time
        log('E4 hidden effects one at a time ...')
        jobs = []
        conds = [('none', [])] + [(h, [h]) for h in HIDDEN_ALL] + [('all', HIDDEN_ALL)]
        for ci, (cn, on) in enumerate(conds):
            for i in range(n_h):
                jobs.append(dict(tag='E4_%s_clean' % cn, names=main4,
                                 scn=make_scenario(34000 + ci * 200 + i, 'test', hidden=hidden_dict(on))))
                jobs.append(dict(tag='E4_%s_leak' % cn, names=main4,
                                 scn=make_scenario(34100 + ci * 200 + i, 'test', hidden=hidden_dict(on),
                                                   leak=dict(type='ramp', size=0.10, ramp_h=24.0))))
        res['E4'] = pd.DataFrame(run_jobs(pool, score_job, jobs))

        # ---- E6: independent simulator B (different functional forms); detector never retuned
        log('E6 simulator B ...')
        jobs = []
        for i in range(n_clean // 2):
            jobs.append(dict(tag='E6_clean', names=main4, scn=make_scenario(35000 + i, 'test', variant='B')))
        for si, sz in enumerate(LEAK_SIZES):
            for i in range(n_leak):
                jobs.append(dict(tag='E6_ramp_%.2f' % sz, names=main4,
                                 scn=make_scenario(35100 + si * 100 + i, 'test', variant='B',
                                                   leak=dict(type='ramp', size=sz, ramp_h=24.0))))
        res['E6'] = pd.DataFrame(run_jobs(pool, score_job, jobs))

        # ---- E7: warm-up error, starting guess vs cold start
        log('E7 warm-up error ...')
        e7 = [n for n in names if n.startswith('D  ')]
        e7 = [n for n in e7 if ('cold' in n or 'datasheet' in n or n == 'D  Adaptive, all guardrails')]
        jobs = [dict(names=e7, scn=make_scenario(36000 + i, 'test')) for i in range(n_clean)]
        res['E7'] = pd.DataFrame(run_jobs(pool, warm_job, jobs))
        pool.close(); pool.join()

    for k, df in res.items():
        df.to_csv(os.path.join(OUT, 'raw_%s.csv' % k), index=False)
    log('done')


if __name__ == '__main__':
    main()
