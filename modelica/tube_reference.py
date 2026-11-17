"""
tube_reference.py -- drivers, parameter mapping, and a Python mirror of TubeStudy.Tube.

* make_drivers()  : weather / solar / wind-rain / pod traffic -> drivers.txt (Modelica table format)
* modelica_params(): truth-sim scenario (settings+params) -> TubeStudy.Tube parameter overrides
* reference_run() : same ODEs as TubeStudy.mo, solved with scipy; writes a CSV with the same
                    column names omc produces.  Used to test the adapter + detectors when omc is
                    not available, and to cross-check omc output when it is.
The drivers are generated here with their own code (not truth_sim's), so the weather the Modelica
tube sees is not the weather the detectors were tuned on.
"""
import numpy as np
from scipy.integrate import solve_ivp
from scipy.signal import lfilter

R, TREF = 8.314, 293.15
N_SEG = 10                       # must equal `constant Integer N` in TubeStudy.mo
DT_S = 600.0                     # driver / output grid [s]


def _ar1(rng, n, phi, sd):
    return lfilter([sd * np.sqrt(1 - phi ** 2)], [1, -phi], rng.normal(0, 1, n))


def make_drivers(settings, days, seed, wind_rain=True, path=None):
    """columns: time[s], T_eff[K], solar 0..1, wall dip[K], pods"""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 77]))
    n = int(days * 144) + 2
    t_h = np.arange(n) * DT_S / 3600
    hod, dayi = t_h % 24, t_h / 24
    s = settings
    w = _ar1(rng, n, np.exp(-(1 / 6) / 30), 2.5)
    out = s['Tmean'] + rng.normal(0, 0.05) * dayi + s['amp'] * np.sin(2 * np.pi * (hod - 9) / 24) + w
    inn = s['Tmean'] + 1.5 + 0.25 * (s['amp'] * np.sin(2 * np.pi * (hod - 9) / 24) + w) + _ar1(rng, n, np.exp(-(1 / 6) / 20), 0.3)
    ow = 1.0 if s['outdoor'] else 0.0
    Teff = ow * out + (1 - ow) * inn
    sun = np.maximum(0, np.sin(np.pi * (hod - 6) / 12))
    cloud = np.clip(0.35 + _ar1(rng, n, np.exp(-(1 / 6) / 6), 0.35), 0, 1)
    solar = sun * (1 - 0.8 * cloud) * ow
    dip = np.zeros(n)
    if wind_rain and ow:
        for _ in range(rng.poisson(0.2 * days)):
            k0 = int(rng.uniform(0, n)); dur = int(rng.uniform(3, 8) * 6); mag = rng.uniform(3, 8)
            kk = np.arange(k0, min(n, k0 + dur))
            dip[kk] += mag * np.sin(np.pi * (kk - k0) / dur) ** 2
    wk = (np.floor(dayi) % 7) >= 5
    m = s['pod_peak'] * (0.3 + np.exp(-(hod - 8) ** 2 / (2 * 1.2 ** 2)) + np.exp(-(hod - 17.5) ** 2 / (2 * 1.5 ** 2))) * np.where(wk, 0.6, 1.0)
    pods = rng.poisson(np.where((hod >= 6) & (hod < 24), np.maximum(m, 0), 0)).astype(float)
    tab = np.column_stack([np.arange(n) * DT_S, Teff, solar, dip, pods])
    if path:
        with open(path, 'w') as f:
            f.write('#1\ndouble drivers(%d,5)\n' % n)
            np.savetxt(f, tab, fmt='%.6g')
    return tab


def modelica_params(scn, tube_len=5000.0):
    """Map a truth-sim scenario's settings/params to Tube parameters (what an engineer would enter)."""
    s, p, hid = scn['settings'], scn['params'], scn['hidden']
    ev = scn.get('event') or {}
    par = dict(L=tube_len, D=s['D'], Cperm=p['C'], Ep=p['Ep'], q300=p['q300'], alpha=p['alpha'], Ed=p['Ed'],
               gammaPod=p['gamma'], tau0=p['tau0'], Sgain=5.0 if s['outdoor'] else 0.0,
               secondFrac=0.25 if hid.get('second_outgas') else 0.0,
               agingPerMonth=p['aging'] if hid.get('seal_aging') else 0.0,
               tVent=1e12, humAmp=0.0)
    if ev.get('type') == 'vent':
        par['tVent'] = ev['day'] * 86400.0
        par['humAmp'] = (2.0 / s['D']) if hid.get('vent_humidity') else 0.0
    lk = scn.get('leak')
    if lk:
        typ = dict(sudden=1, ramp=2, creep=3, intermittent=4)[lk['type']]
        par.update(leakType=typ, leakSize=lk['size'], leakT0=lk['start_day'] * 86400.0,
                   rampH=lk.get('ramp_h', 24.0), creepDays=lk.get('creep_days', 21.0))
    return par


DEFAULTS = dict(L=5000, D=3.0, eta=1.8e-5, Spump=40, Plo=97, Phi=103, gaugeSeg=10, Cperm=0.3, Ep=50000,
                q300=0.2, alpha=1.0, Ed=45000, secondFrac=0.25, E2=80000, agingPerMonth=0.1, gammaPod=0.02,
                tau0=500, tVent=1e12, humAmp=0, Sgain=5, tauG=5400, shade=0, leakType=0, leakSize=0.1,
                leakT0=1.5e6, leakSeg=5, rampH=24, creepDays=21, onH=24, offH=24)


def reference_run(par, drivers, stop_s, csv_path):
    """Python mirror of TubeStudy.Tube (same equations, same output columns)."""
    q = dict(DEFAULTS, **par)
    N = N_SEG
    V = np.pi * q['D'] ** 2 / 4 * q['L'] / N
    Ls = q['L'] / N
    gs, ls = int(q['gaugeSeg']) - 1, int(q['leakSeg']) - 1
    td = drivers[:, 0]
    D_ = lambda t: [np.interp(t, td, drivers[:, j]) for j in (1, 2, 3, 4)]

    def leak(t):
        th = (t - q['leakT0']) / 3600
        if t < q['leakT0'] or q['leakType'] < .5:
            return 0.0
        ty = q['leakType']
        if ty < 1.5: return q['leakSize'] * min(max(th, 0), 1)
        if ty < 2.5: return q['leakSize'] * min(max(th / q['rampH'], 0), 1)
        if ty < 3.5: return q['leakSize'] * min(max(th / (q['creepDays'] * 24), 0), 1)
        return q['leakSize'] * min(max(th, 0), 1) * (1.0 if th % (q['onH'] + q['offH']) < q['onH'] else 0.0)

    def sources(t, Tg):
        Tamb, sol, dip, pods = D_(t)
        tau = 24 + (t - q['tVent']) / 3600 if t >= q['tVent'] else q['tau0'] + t / 3600
        expo = 1 - q['shade'] * np.arange(N) / (N - 1)
        Tw = Tamb + expo * q['Sgain'] * sol - dip
        f = lambda E: np.exp(-E / R * (1 / Tg - 1 / TREF))
        src = (q['Cperm'] * (1 + q['agingPerMonth'] * t / (720 * 3600)) * f(q['Ep'])
               + q['q300'] * (tau / 300) ** (-q['alpha']) * f(q['Ed'])
               + q['secondFrac'] * q['q300'] * np.sqrt(300 / tau) * f(q['E2'])
               + (q['humAmp'] * np.exp(-(t - q['tVent']) / (60 * 3600)) if t >= q['tVent'] else 0.0)
               + q['gammaPod'] * pods)
        src = src.copy(); src[ls] += leak(t) * N
        return Tw, src

    def rhs(t, y, on):
        P, Tg = y[:N], y[N:]
        Tw, src = sources(t, Tg)
        dT = (Tw - Tg) / q['tauG']
        cond = np.pi * q['D'] ** 4 / (256 * q['eta'] * Ls) * (P[:-1] + P[1:]) / 2
        Q = cond * (P[:-1] - P[1:])
        net = np.zeros(N); net[1:] += Q; net[:-1] -= Q
        if on: net[0] -= q['Spump'] * P[0]
        return np.concatenate([P / Tg * dT + src / 3600 + net / V, dT])

    t_out = np.arange(0, stop_s + 1, DT_S)
    Tw0, _ = sources(0.0, np.full(N, 293.0))
    y = np.concatenate([np.full(N, 97.5), Tw0])
    t, on, npump = 0.0, False, 0
    rows = []
    ig = 0
    while t < stop_s - 1e-6:
        def ev_hi(tt, yy, on_): return yy[gs] - q['Phi']
        def ev_lo(tt, yy, on_): return yy[gs] - q['Plo']
        ev = ev_lo if on else ev_hi
        ev.terminal, ev.direction = True, (-1 if on else 1)
        sol = solve_ivp(rhs, (t, stop_s), y, args=(on,), method='LSODA', events=ev,
                        t_eval=t_out[(t_out >= t) & (t_out <= stop_s)], rtol=1e-7, atol=1e-9, max_step=1800)
        st, sy = np.asarray(sol.t), np.asarray(sol.y)
        for k in range(st.size):
            rows.append((st[k], float(on), npump, sy[gs, k], sy[N + gs, k]))
        if sol.t_events[0].size:
            t, y = sol.t_events[0][0], sol.y_events[0][0]
            on = not on
            npump += int(on)
            y = y.copy()
        else:
            break
    rows.sort(key=lambda r: r[0])
    tt = np.array([r[0] for r in rows]); keep = np.concatenate([[True], np.diff(tt) > 1e-6])
    A = np.array(rows)[keep]
    Tamb = np.array([D_(x)[0] for x in A[:, 0]]); sol_ = np.array([D_(x)[1] for x in A[:, 0]])
    dip = np.array([D_(x)[2] for x in A[:, 0]]); pods = np.array([D_(x)[3] for x in A[:, 0]])
    expo = 1 - q['shade'] * gs / (N - 1)
    out = np.column_stack([A[:, 0], A[:, 3], A[:, 1], A[:, 2], Tamb + expo * q['Sgain'] * sol_ - 0.3 * dip,
                           Tamb, pods, [leak(x) for x in A[:, 0]], A[:, 4]])
    hdr = 'time,Pg,pumpOnReal,nPumpsReal,Tsensor,Tamb,podsOut,leakTotal,Tgas'
    np.savetxt(csv_path, out, delimiter=',', header=hdr, comments='')
    return csv_path
