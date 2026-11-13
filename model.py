"""
model.py -- the detector side.  Never imports truth parameters; only the equation,
datasheet nominal values, and what `observations()` hands over.

Model equation (per observation window, Pa/h):
    rise = C * exp(-Ep/R (1/T - 1/Tref))                       seal permeation
         + q300 * (tau/300)^-alpha * exp(-Ed/R (1/T - 1/Tref)) outgassing
         + (100/T) * tube_slope                                gas law (fixed physics)
         + beta * amb_slope                                    gauge tempco
         + gamma * pods                                        traffic
Linear scales theta = [C, q300, beta, gamma] are updated every window (Kalman filter);
shape parameters phi = [Ep, alpha, Ed] are refitted every couple of weeks.
"""
import math
import numpy as np
from scipy.optimize import least_squares
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.ensemble import GradientBoostingRegressor
from truth_sim import R, TREF, DT, SIGMA_P, GLASS, SEAL

PN = ['C', 'q300', 'beta', 'gamma', 'Ep', 'alpha', 'Ed']       # Ep, Ed in kJ/mol
LOGP = [True, True, False, True, False, False, False]
PHYS_LO = np.array([0.0, 0.0, 0.0, 0.0, 10.0, 0.3, 20.0])
WIDE_LO = np.array([0.0, 0.0, -1.0, -1.0, 5.0, 0.1, 10.0])
WIDE_HI = np.array([10.0, 10.0, 1.0, 1.0, 150.0, 3.0, 150.0])
S_HOLD = 0.02            # Pa/h, allowance used by the hold-test guardrail
K_REF = 0.5              # CUSUM reference value (sigma units)
K_DIV = 0.3              # frozen-copy divergence CUSUM reference value
SPD = 144


def gauge_var(n):
    return 12.0 * SIGMA_P ** 2 / (DT ** 2 * n * (n * n - 1.0))


def nominal(s):
    """Datasheet-only guess from published nominal values and geometry."""
    g, sl = GLASS[s['glass']], SEAL[s['seal']]
    geo = 2.0 / s['D']
    return np.array([sl['c'] * (s['seals_per_km'] / 6.0) * geo ** 2, g['q300'] * geo, 0.05,
                     0.02 * geo, sl['Ep'] / 1e3, g['alpha'], g['Ed'] / 1e3])


def shapes(T, tau, Ep, alpha, Ed):
    d = 1.0 / T - 1.0 / TREF
    fp = np.exp(-Ep * 1e3 / R * d)
    fo = (tau / 300.0) ** (-alpha) * np.exp(-Ed * 1e3 / R * d)
    return fp, fo


def model_rise(p, o):
    fp, fo = shapes(o['T'], o['tau'], p[4], p[5], p[6])
    return p[0] * fp + p[1] * fo + 100.0 / o['T'] * o['tube_slope'] + p[2] * o['amb_slope'] + p[3] * o['pods']


def sub(o, idx):
    return {k: v[idx] for k, v in o.items() if isinstance(v, np.ndarray)}


def fit_batch(o, idx, p0, sd0, lo, hi, s0=0.03, max_nfev=60):
    oo = sub(o, idx)
    sig = np.sqrt(s0 ** 2 + gauge_var(oo['n']))
    sd0 = np.asarray(sd0, float)

    def res(p):
        return np.concatenate([(model_rise(p, oo) - oo['rise']) / sig, (p - p0) / sd0])
    x0 = np.clip(p0, lo + 1e-9, hi - 1e-9)
    r = least_squares(res, x0, bounds=(lo, hi), x_scale=np.maximum(sd0, 1e-3), max_nfev=max_nfev)
    return r.x


# ---------------------------------------------------------- starting-guess model
def settings_features(s):
    n = nominal(s)
    return np.array([math.log(n[0]), math.log(n[1]), math.log(n[3]), n[5], n[6] / 10.0, n[4] / 10.0,
                     float(s['outdoor']), s['amp'] / 5.0, (s['Tmean'] - 290.0) / 10.0, s['pod_peak'] / 10.0])


def to_t(p):      # raw -> transformed (log for positive scales)
    q = np.array(p, float)
    for i, lg in enumerate(LOGP):
        if lg:
            q[i] = math.log(max(q[i], 0.003))
    return q


def from_t(q):
    p = np.array(q, float)
    for i, lg in enumerate(LOGP):
        if lg:
            p[i] = math.exp(q[i])
    return p


class Guess:
    """Maps settings -> starting parameter values + uncertainty, trained on the synthetic corpus."""

    def __init__(self):
        self.ok = False

    def fit(self, settings_list, P_fit, use_gbr=False):
        X = np.array([settings_features(s) for s in settings_list])
        Y = np.array([to_t(p) for p in P_fit])
        self.mu_x, self.sd_x = X.mean(0), X.std(0) + 1e-9
        Xs = (X - self.mu_x) / self.sd_x
        self.models, cvp = [], np.zeros_like(Y)
        kf = KFold(5, shuffle=True, random_state=0)
        self.r2 = []
        self.r2_gbr = []
        for j in range(Y.shape[1]):
            m = Ridge(alpha=3.0)
            cvp[:, j] = cross_val_predict(m, Xs, Y[:, j], cv=kf)
            self.models.append(Ridge(alpha=3.0).fit(Xs, Y[:, j]))
            self.r2.append(1 - np.var(Y[:, j] - cvp[:, j]) / np.var(Y[:, j]))
            g = cross_val_predict(GradientBoostingRegressor(n_estimators=80, max_depth=2, learning_rate=0.08,
                                                            random_state=0), Xs, Y[:, j], cv=kf)
            self.r2_gbr.append(1 - np.var(Y[:, j] - g) / np.var(Y[:, j]))
        self.sd_t = (Y - cvp).std(0)                                   # learned-guess uncertainty
        self.mu_t, self.cold_sd_t = Y.mean(0), Y.std(0)                  # cold start (no settings)
        Nom = np.array([to_t(nominal(s)) for s in settings_list])
        self.nom_sd_t = (Y - Nom).std(0)                                # datasheet-only uncertainty
        raw = np.array(P_fit)
        span = raw.max(0) - raw.min(0)
        self.lo = np.maximum(raw.min(0) - 0.25 * span, PHYS_LO)
        self.hi = raw.max(0) + 0.25 * span
        self.lo[2] = min(self.lo[2], 0.0)
        # initial per-block model misfit (Pa/h) learned from the corpus
        self.s_init = 0.04
        self.ok = True
        return self

    def predict(self, s, kind='learned'):
        if kind == 'learned':
            x = (settings_features(s) - self.mu_x) / self.sd_x
            q = np.array([m.predict(x[None])[0] for m in self.models])
            sd_t = self.sd_t
        elif kind == 'nominal':
            q, sd_t = to_t(nominal(s)), self.nom_sd_t
        else:
            q, sd_t = self.mu_t, self.cold_sd_t
        p = from_t(q)
        sd = np.where(LOGP, p * sd_t, sd_t)
        return p, np.maximum(sd, 1e-3)


def fit_corpus_run(view, guess_nominal_sd, s0=0.03):
    """Fit the model equation to one leak-free training run (what the detector could do at commissioning)."""
    o = view['obs']
    p0 = nominal(view['settings'])
    sd0 = np.where(LOGP, p0 * 1.0, np.array([0.0, 0.0, 0.08, 0.0, 8.0, 0.3, 8.0]))
    sd0 = np.where(np.array(LOGP), sd0, sd0)
    sd0[[0, 1, 3]] = p0[[0, 1, 3]] * 1.0
    pf = fit_batch(o, np.arange(len(o['t'])), p0, sd0, WIDE_LO, WIDE_HI, s0=s0)
    return pf


# ---------------------------------------------------------- CUSUM utilities
def cusum_alarms(z, mask, t, h, k=K_REF):
    G, out = 0.0, []
    for i in range(len(z)):
        if not mask[i]:
            continue
        G = max(0.0, G + z[i] - k)
        if G > h:
            out.append(t[i])
            G = 0.0
    return out


# ---------------------------------------------------------- detectors
def _segments(view, W0):
    """Calibration segments for non-adaptive detectors: start, and after every settings change."""
    segs = [(0.0, None)]
    for a in view['announce']:
        if not a.get('vent'):
            segs.append((a['t'], a['settings']))
    return segs


def run_A(view, cfg, guess):
    """Night-only level model, calibrated once per tube (and again after a settings change)."""
    o = view['obs']
    t, hr = o['t'], o['hour']
    night = (hr >= 0) & (hr < 6)
    z = np.full(len(t), np.nan)
    mask = np.zeros(len(t), bool)
    segs = _segments(view, cfg['warm'])
    bounds = [s[0] for s in segs] + [1e9]
    for si in range(len(segs)):
        a, b = bounds[si], bounds[si + 1]
        cal = np.where((t >= a) & (t < a + cfg['warm'] * 24) & night)[0]
        ev = np.where((t >= a + cfg['warm'] * 24) & (t < b) & night)[0]
        if len(cal) < 4 or len(ev) == 0:
            continue
        f = lambda idx: np.vstack([np.ones(len(idx)), 2.0 ** ((o['T'][idx] - TREF) / 12.0) - 1.0]).T
        X = f(cal)
        w = 1.0 / (0.03 ** 2 + gauge_var(o['n'][cal]))
        lam = np.diag([0.0, 1.0 / 0.3 ** 2])
        beta = np.linalg.solve(X.T @ (X * w[:, None]) + lam, X.T @ (w * o['rise'][cal]))
        sd = max(np.std(o['rise'][cal] - X @ beta, ddof=2), 0.01)
        e = o['rise'][ev] - f(ev) @ beta
        z[ev] = e / np.sqrt(sd ** 2 + gauge_var(o['n'][ev]))
        mask[ev] = True
    return dict(t=t, z=z, mask=mask, cfg=cfg)


def run_B(view, cfg, guess):
    """Section-2 equation, fitted once on a warm-up window and then frozen."""
    o = view['obs']
    t = o['t']
    z = np.full(len(t), np.nan)
    mask = np.zeros(len(t), bool)
    segs = _segments(view, cfg['warm'])
    bounds = [s[0] for s in segs] + [1e9]
    for si, (a, news) in enumerate(segs):
        s = news if news is not None else view['settings']
        b = bounds[si + 1]
        p0, sd0 = guess.predict(s, cfg['prior'])
        cal = np.where((t >= a) & (t < a + cfg['warm'] * 24))[0]
        ev = np.where((t >= a + cfg['warm'] * 24) & (t < b))[0]
        if len(cal) < 10 or len(ev) == 0:
            continue
        sd_all = np.concatenate([sd0[:4], np.maximum(sd0[4:], 1e-3)])
        pf = fit_batch(o, cal, p0, sd_all, guess.lo, guess.hi)
        res = o['rise'][cal] - model_rise(pf, sub(o, cal))
        blk = (o['hour'][cal] // 6).astype(int)
        s2 = np.array([max(np.mean(res[blk == k] ** 2) - np.mean(gauge_var(o['n'][cal][blk == k])), 0.015 ** 2)
                       if np.sum(blk == k) >= 4 else 0.04 ** 2 for k in range(4)])
        eb = (o['hour'][ev] // 6).astype(int)
        e = o['rise'][ev] - model_rise(pf, sub(o, ev))
        z[ev] = e / np.sqrt(s2[eb] + gauge_var(o['n'][ev]))
        mask[ev] = True
    return dict(t=t, z=z, mask=mask, cfg=cfg)


def run_KF(view, cfg, guess):
    """Gray-box online model: Kalman filter on the linear scales, periodic shape refit,
    guardrails (pause / slow learning / bounds / frozen copy / hold-test verification)."""
    o = view['obs']
    t, n_obs = o['t'], len(o['t'])
    kind = cfg['prior']
    p, sd0 = guess.predict(view['settings'], kind)
    p = p.copy()
    P = np.diag(sd0[:4] ** 2)
    lo = guess.lo if cfg['bounds'] else WIDE_LO
    hi = guess.hi if cfg['bounds'] else WIDE_HI
    rho = cfg['rho']
    Q = np.diag((rho * sd0[:4]) ** 2)
    s2 = np.full(4, guess.s_init ** 2)
    lam = 0.05
    h, pause = cfg['h'], cfg['pause']
    G, Gd = 0.0, 0.0
    warm_end = cfg['warm'] * 24.0
    black_end = 0.0
    ann = sorted(view['announce'], key=lambda a: a['t'])
    ai = 0
    holds = view['holds']
    hi_idx = 0
    pf, frozen_set = None, False
    buf = []
    next_refit = warm_end + cfg['refit_days'] * 24.0 if cfg['refit_days'] else 1e18
    z_tr = np.full(n_obs, np.nan)
    mask = np.zeros(n_obs, bool)
    Lref = np.full(n_obs, np.nan)
    alarms, hold_r = [], []
    paused = np.zeros(n_obs, bool)
    d_tr = np.full(n_obs, np.nan)
    e_tr = np.full(n_obs, np.nan)
    p_tr = np.zeros((n_obs, 7))
    gv_all = gauge_var(o['n'])
    for i in range(n_obs):
        ti = t[i]
        # --- announced changes
        while ai < len(ann) and ann[ai]['t'] <= ti:
            a = ann[ai]
            ai += 1
            if a.get('vent'):
                black_end = max(black_end, a['t'] + 24.0)
            else:
                p, sd0 = guess.predict(a['settings'], kind)
                p = p.copy()
                P = np.diag(sd0[:4] ** 2)
                Q = np.diag((rho * sd0[:4]) ** 2)
                s2[:] = guess.s_init ** 2
                G = Gd = 0.0
                black_end = a['t'] + cfg['blackout_days'] * 24.0
                frozen_set, buf = False, []
                next_refit = black_end + cfg['refit_days'] * 24.0 if cfg['refit_days'] else 1e18
        in_black = ti < max(warm_end, black_end)
        # --- hold-test verification (guardrail 5)
        while hi_idx < len(holds['t']) and holds['t'][hi_idx] <= ti:
            th = holds['t'][hi_idx]
            if th > max(warm_end, black_end):
                fp_h, fo_h = shapes(holds['T'][hi_idx], holds['tau'][hi_idx], p[4], p[5], p[6])
                r = holds['rise'][hi_idx] - (p[0] * fp_h + p[1] * fo_h)
                hold_r.append((th, r / S_HOLD))
            hi_idx += 1
        # --- predict
        fp, fo = shapes(o['T'][i], o['tau'][i], p[4], p[5], p[6])
        f = np.array([fp, fo, o['amb_slope'][i], o['pods'][i]])
        y = o['rise'][i] - 100.0 / o['T'][i] * o['tube_slope'][i]
        e = y - f @ p[:4]
        Pf = P @ f
        fPf = float(f @ Pf)
        b = int(o['hour'][i] // 6) % 4
        gv = gv_all[i]
        sig = math.sqrt(s2[b] + gv + max(fPf, 0.0))
        z = e / sig
        z_tr[i] = z
        e_tr[i] = e
        # --- CUSUM / alarms
        Gn = max(0.0, G + z - K_REF)
        if not in_black:
            mask[i] = True
            if Gn > h:
                alarms.append((ti, 'cusum'))
                Gn = 0.0
        else:
            Gn = 0.0
        # --- frozen-copy divergence (guardrail 4)
        if cfg['frozen'] and not in_black:
            if not frozen_set:
                pf, frozen_set, Gd = p.copy(), True, 0.0
            fpf, fof = shapes(o['T'][i], o['tau'][i], pf[4], pf[5], pf[6])
            yf = pf[0] * fpf + pf[1] * fof + pf[2] * o['amb_slope'][i] + pf[3] * o['pods'][i]
            d_tr[i] = (f @ p[:4] - yf) / sig
        # --- learning gate (guardrail 1)
        learn = True
        if cfg['adapt'] is False:
            learn = False
        elif pause is not None and not in_black and Gn > pause * h:
            learn = False
        paused[i] = not learn
        G = Gn
        if learn:
            K = Pf / (fPf + s2[b] + gv)
            p[:4] = p[:4] + K * e
            P = P - np.outer(K, Pf)
            P = 0.5 * (P + P.T) + Q
            if cfg['bounds']:
                p[:4] = np.clip(p[:4], lo[:4], hi[:4])
            s2[b] += lam * (max(e * e - gv - max(fPf, 0.0), 0.0) - s2[b])
            s2[b] = max(s2[b], 0.01 ** 2)
            buf.append(i)
        # --- slow refit of shape parameters
        if learn and ti >= next_refit and len(buf) >= 60 and cfg['refit_days']:
            idx = np.array(buf[-150:])
            p_prior = p.copy()
            sd_pr = np.concatenate([np.maximum(np.sqrt(np.diag(P)), 0.3 * sd0[:4]), 0.5 * sd0[4:]])
            pn = fit_batch(o, idx, p_prior, sd_pr, lo, hi, s0=math.sqrt(float(np.mean(s2))), max_nfev=25)
            p = pn
            next_refit = ti + cfg['refit_days'] * 24.0
        Lref[i] = p[0] + p[1] * 2.0 ** (-p[5])           # level at Tref, tau=600
        p_tr[i] = p
    return dict(t=t, z=z_tr, mask=mask, alarms=alarms, Lref=Lref, paused=paused, cfg=cfg,
                p_final=p.copy(), warm_end=warm_end, d=d_tr, e=e_tr, hold_r=hold_r, p_tr=p_tr)


def run(view, cfg, guess, h=None, **over):
    c = dict(cfg)
    if h is not None:
        c['h'] = h
    c.update(over)
    if c['mode'] == 'A':
        r = run_A(view, c, guess)
    elif c['mode'] == 'B':
        r = run_B(view, c, guess)
    else:
        r = run_KF(view, c, guess)
    if c['mode'] in ('A', 'B'):
        al = cusum_alarms(r['z'], r['mask'], r['t'], c['h'])
        r['alarms'] = [(a, 'cusum') for a in al]
        r['Lref'] = np.full(len(r['t']), np.nan)
    else:
        r['alarms'] = merge_alarms(r, c)
    return r


def merge_alarms(r, c):
    out = list(r['alarms'])
    if c['frozen']:
        d = r['d']
        ok = ~np.isnan(d)
        out += [(a, 'frozen') for a in cusum_alarms(np.nan_to_num(d), ok, r['t'], c['h_d'], K_DIV)]
    if c['verify']:
        out += [(th, 'verify') for th, rr in r['hold_r'] if rr > c['c_v']]
    return sorted(out)


BASE = dict(mode='KF', prior='learned', adapt=True, rho=0.01, pause=None, bounds=False, frozen=False,
            verify=False, refit_days=14, warm=10.0, blackout_days=3.0, h=8.0, h_d=10.0, c_v=3.0)

CONFIGS = {
    'A  Night-only level model':        dict(BASE, mode='A', adapt=False, refit_days=None),
    'B  Static physics, calibrated once': dict(BASE, mode='B', adapt=False, refit_days=None),
    'C  Adaptive, no guardrails':       dict(BASE, rho=0.1),
    'D  Adaptive, all guardrails':      dict(BASE, rho=0.01, pause=0.35, bounds=True, frozen=True, verify=True),
    'D- no pause':                      dict(BASE, rho=0.01, pause=None, bounds=True, frozen=True, verify=True),
    'D- fast learning':                 dict(BASE, rho=0.1, pause=0.35, bounds=True, frozen=True, verify=True),
    'D- no bounds':                     dict(BASE, rho=0.01, pause=0.35, bounds=False, frozen=True, verify=True),
    'D- no frozen copy':                dict(BASE, rho=0.01, pause=0.35, bounds=True, frozen=False, verify=True),
    'D- no hold test':                  dict(BASE, rho=0.01, pause=0.35, bounds=True, frozen=True, verify=False),
    'D  cold start (no settings model)': dict(BASE, rho=0.01, pause=0.35, bounds=True, frozen=True, verify=True,
                                              prior='cold'),
    'D  datasheet-only start':          dict(BASE, rho=0.01, pause=0.35, bounds=True, frozen=True, verify=True,
                                              prior='nominal'),
}
