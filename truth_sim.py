"""
truth_sim.py  --  the "truth world" for the adaptive leak-detection study.

This simulator stands in for reality.  It contains everything the detector's
model contains (gas law, outgassing, seal permeation, gauge tempco, pod traffic)
PLUS physics the model has never seen ("hidden effects").  The detector only
ever receives the output of `observations()`; it never sees true parameters,
hidden switches, leak or event labels.

Time step 10 min.  The pump is on/off with a 97-103 Pa deadband, so the leak
signal is the pressure RISE RATE (Pa/h) while the pump is off.  Each pump-off
period is cut into windows of at most 6 h; each window is one observation.
"""
import numpy as np
from scipy.signal import lfilter

R = 8.314
TREF = 293.15
DT = 1.0 / 6.0            # hours per step
SPD = 144                 # steps per day
P_LO, P_HI = 97.0, 103.0
WIN_MAX = 36              # samples (6 h)
WIN_MIN = 6               # samples (1 h)
SIGMA_P = 0.10            # gauge white noise, Pa per sample (public sensor spec)
RW_SIG = 0.03             # gauge random-walk drift, Pa / sqrt(h)

# "datasheet" nominal material values the operator can look up.
GLASS = {
    'borosilicate': dict(q300=0.20, alpha=1.00, Ed=45e3),
    'soda_lime':    dict(q300=0.32, alpha=0.90, Ed=40e3),
    'fused_silica': dict(q300=0.10, alpha=1.10, Ed=55e3),   # held out of train/tune
}
SEAL = {
    'elastomer': dict(c=0.30, Ep=50e3),
    'metal':     dict(c=0.05, Ep=25e3),
    'mixed':     dict(c=0.14, Ep=38e3),                      # held out of train/tune
}
TRAIN_GLASS = ['borosilicate', 'soda_lime']
TRAIN_SEAL = ['elastomer', 'metal']

HIDDEN_ALL = ['second_outgas', 'solar_lag', 'vent_humidity', 'seal_aging',
              'gauge_glitch', 'wind_rain']
HIDDEN_TRAIN = ['second_outgas', 'seal_aging']              # tune split uses the same subset


def hidden_dict(on):
    return {k: (k in on) for k in HIDDEN_ALL}


# ------------------------------------------------------------------ scenarios
def draw_settings(rng, split):
    glass = rng.choice(TRAIN_GLASS if split != 'test' else list(GLASS))
    seal = rng.choice(TRAIN_SEAL if split != 'test' else list(SEAL))
    outdoor = bool(rng.random() < 0.5)
    return dict(
        D=float(np.exp(rng.uniform(np.log(1.2), np.log(4.5)))),
        glass=str(glass), seal=str(seal),
        seals_per_km=float(rng.uniform(3, 12)),
        outdoor=outdoor,
        Tmean=float(rng.uniform(280, 298)),
        amp=float(rng.uniform(4, 9)) if outdoor else float(rng.uniform(0.5, 2.0)),
        pod_peak=float(rng.uniform(3, 12)),
    )


def draw_true_params(rng, s):
    g, sl = GLASS[s['glass']], SEAL[s['seal']]
    geo = 2.0 / s['D']
    return dict(
        q300=g['q300'] * geo * float(np.exp(rng.normal(0, 0.45))),
        alpha=float(np.clip(g['alpha'] + rng.normal(0, 0.08), 0.5, 1.5)),
        Ed=float(g['Ed'] + rng.normal(0, 4e3)),
        C=sl['c'] * (s['seals_per_km'] / 6.0) * geo ** 2 * float(np.exp(rng.normal(0, 0.35))),
        Ep=float(sl['Ep'] + rng.normal(0, 4e3)),
        beta=float(max(0.0, rng.normal(0.05, 0.03))),
        gamma=float(0.02 * geo * np.exp(rng.normal(0, 0.35))),
        aging=float(rng.uniform(0.05, 0.25)),       # fractional perm growth per 30 d
        kappa=float(rng.uniform(0.0, 0.03)),        # gauge rise under-read
        tau0=float(rng.uniform(150, 900)),          # hours since last pump-down at t=0
    )


def make_scenario(seed, split='test', hidden=None, days=60, event=None, leak=None,
                  variant='A'):
    """A scenario is plain data.  `event` / `leak` are dicts or None."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 1]))
    s = draw_settings(rng, split)
    p = draw_true_params(rng, s)
    if hidden is None:
        hidden = hidden_dict(HIDDEN_TRAIN if split != 'test' else HIDDEN_ALL)
    scn = dict(seed=int(seed), split=split, days=int(days), settings=s, params=p,
               hidden=hidden, event=None, leak=None, variant=variant)
    if event is not None:
        ev = dict(event)
        ev.setdefault('day', float(rng.uniform(25, 40)))
        if ev['type'] == 'outdoor_move':
            scn['settings']['outdoor'] = False
            scn['settings']['amp'] = float(rng.uniform(0.5, 2.0))
            ev['new_amp'] = float(rng.uniform(4, 9))
        if ev['type'] == 'seal_swap':
            new = str(rng.choice([k for k in (TRAIN_SEAL if split != 'test' else list(SEAL))
                                  if k != s['seal']]))
            ev['new_seal'] = new
            ev['C_new'] = SEAL[new]['c'] * (s['seals_per_km'] / 6.0) * (2.0 / s['D']) ** 2 * \
                float(np.exp(rng.normal(0, 0.35)))
            ev['Ep_new'] = float(SEAL[new]['Ep'] + rng.normal(0, 4e3))
        if ev['type'] == 'weather_front':
            ev['dT'] = float(rng.choice([-1, 1]) * rng.uniform(6, 12))
        scn['event'] = ev
    if leak is not None:
        lk = dict(leak)
        lk.setdefault('start_day', float(rng.uniform(15, 30)))
        scn['leak'] = lk
    return scn


# ------------------------------------------------------------------ simulator
def _ar1(rng, n, phi, sd):
    e = rng.normal(0, 1, n)
    return lfilter([sd * np.sqrt(1 - phi ** 2)], [1, -phi], e)


def _ema(x, tau_h):
    a = 1 - np.exp(-DT / tau_h)
    y, _ = lfilter([a], [1, -(1 - a)], x, zi=[(1 - a) * x[0]])
    return y


def leak_series(lk, N, rng):
    out = np.zeros(N)
    if lk is None:
        return out
    k0 = int(lk['start_day'] * SPD)
    t = (np.arange(N) - k0) * DT          # hours since leak start
    S = lk['size']
    typ = lk['type']
    if typ == 'sudden':
        out = S * np.clip(t / 1.0, 0, 1)
    elif typ == 'ramp':
        out = S * np.clip(t / lk.get('ramp_h', 24.0), 0, 1)
    elif typ == 'creep':
        out = S * np.clip(t / (lk.get('creep_days', 21.0) * 24), 0, 1)
    elif typ == 'intermittent':
        on = np.zeros(N)
        k, state = k0, True
        r2 = np.random.default_rng(int(lk.get('pat_seed', 0)) + 17)
        while k < N:
            L = int(r2.uniform(12, 36) * 6)
            if state:
                on[k:k + L] = 1.0
            k += L
            state = not state
        out = S * on * np.clip(t / 1.0, 0, 1)
    else:
        raise ValueError(typ)
    out[t < 0] = 0.0
    return out


def simulate(scn, hold_every_days=14):
    """Run the truth world.  Returns a dict `ds` with observations (what a detector may
    see) and `truth` (labels, only for scoring)."""
    N = scn['days'] * SPD
    seed = scn['seed']
    ss = np.random.SeedSequence([seed, 2]).spawn(12)
    R_ = [np.random.default_rng(x) for x in ss]
    (r_wx, r_cl, r_wind, r_pod, r_eps, r_rw, r_sn, r_gl, r_misc, r_in, r_hold, r_x) = R_
    s, p, hid, ev, variant = scn['settings'], scn['params'], scn['hidden'], scn['event'], scn['variant']
    k = np.arange(N)
    t_h = k * DT
    hod = t_h % 24.0
    dayi = t_h / 24.0

    # ---- announced / unannounced events as arrays
    k_ev = int(ev['day'] * SPD) if ev else None
    outdoor0 = s['outdoor']
    out_w = np.full(N, 1.0 if outdoor0 else 0.0)
    amp = np.full(N, s['amp'])
    front = np.zeros(N)
    tau = p['tau0'] + t_h
    C_arr = np.full(N, p['C'])
    Ep_arr = np.full(N, p['Ep'])
    vent_k = None
    if ev:
        if ev['type'] == 'outdoor_move':
            ramp = np.clip((k - k_ev) / 72.0, 0, 1)
            out_w = ramp
            amp = s['amp'] + ramp * (ev['new_amp'] - s['amp'])
        elif ev['type'] == 'weather_front':
            up = np.clip((k - k_ev) / 36.0, 0, 1)
            relax = np.where(k >= k_ev + 36, np.exp(-(k - k_ev - 36) * DT / 60.0), 1.0)
            front = ev['dT'] * up * relax
        elif ev['type'] == 'seal_swap':
            C_arr = np.where(k >= k_ev, ev['C_new'], p['C'])
            Ep_arr = np.where(k >= k_ev, ev['Ep_new'], p['Ep'])
        elif ev['type'] == 'vent':
            vent_k = k_ev
            tau = np.where(k >= k_ev, 24.0 + (k - k_ev) * DT, tau)

    # ---- temperature world
    weather = _ar1(r_wx, N, np.exp(-DT / 30.0), 2.5)
    trend = r_wx.normal(0, 0.05) * dayi
    diurnal = amp * np.sin(2 * np.pi * (hod - 9) / 24.0)
    if variant == 'B':
        diurnal = diurnal + 0.35 * amp * np.sin(4 * np.pi * (hod - 5) / 24.0)
    Tmean_t = s['Tmean'] + trend
    T_out = Tmean_t + diurnal + weather + front
    T_in = s['Tmean'] + 1.5 + 0.25 * (diurnal + weather + front) + _ar1(r_in, N, np.exp(-DT / 20), 0.3)
    T_eff = out_w * T_out + (1 - out_w) * T_in
    sun = np.maximum(0, np.sin(np.pi * (hod - 6) / 12.0))
    cloud = np.clip(0.35 + _ar1(r_cl, N, np.exp(-DT / 6.0), 0.35), 0, 1)
    solar = sun * (1 - 0.8 * cloud) * out_w
    if variant == 'B':
        S_gain, tau_g, solar_on, wind_on = 4.0, 1.0, True, False
    else:
        S_gain, tau_g = 5.0, 1.5
        solar_on, wind_on = hid['solar_lag'], hid['wind_rain']
    # wind / rain cooling pulses (outdoor only)
    dip = np.zeros(N)
    if wind_on:
        n_ev = r_wind.poisson(0.2 * scn['days'])
        for _ in range(n_ev):
            k0 = int(r_wind.uniform(0, N))
            dur = int(r_wind.uniform(3, 8) * 6)
            mag = r_wind.uniform(3, 8)
            kk = np.arange(k0, min(N, k0 + dur))
            dip[kk] += mag * np.sin(np.pi * (kk - k0) / dur) ** 2
        dip *= out_w
    sol_term = S_gain * solar if solar_on else np.zeros(N)
    wall_true = T_eff + sol_term - dip
    wall_meas = T_eff + sol_term - 0.3 * dip + r_sn.normal(0, 0.05, N)
    if solar_on:
        Tg = _ema(wall_true, tau_g)
    else:
        Tg = wall_true.copy()
    amb_meas = T_eff + r_sn.normal(0, 0.10, N)
    Tgauge = _ema(T_eff, 1.0)
    dTg = np.empty(N)
    dTg[:-1] = np.diff(Tg) / DT
    dTg[-1] = dTg[-2]
    gdT = dTg / Tg

    # ---- pods
    wk = (np.floor(dayi) % 7) >= 5
    m = s['pod_peak'] * (0.3 + np.exp(-(hod - 8) ** 2 / (2 * 1.2 ** 2)) +
                         np.exp(-(hod - 17.5) ** 2 / (2 * 1.5 ** 2))) * np.where(wk, 0.6, 1.0)
    m = np.where((hod >= 6) & (hod < 24), m, 0.0)
    pods = r_pod.poisson(np.maximum(m, 0)).astype(float)

    # ---- gas sources (Pa/h)
    fE_p = np.exp(-Ep_arr / R * (1 / Tg - 1 / TREF))
    aging = np.ones(N)
    if hid['seal_aging']:
        aging = 1 + p['aging'] * t_h / 720.0
    perm = C_arr * aging * fE_p
    fE_d = np.exp(-p['Ed'] / R * (1 / Tg - 1 / TREF))
    if variant == 'B':
        shape = 0.6 * np.exp(-tau / 250.0) + 0.4 * np.exp(-tau / 1500.0) + 0.04
        shape300 = 0.6 * np.exp(-300 / 250.0) + 0.4 * np.exp(-300 / 1500.0) + 0.04
        out_main = p['q300'] * (shape / shape300) * fE_d
    else:
        out_main = p['q300'] * (tau / 300.0) ** (-p['alpha']) * fE_d
    out2 = np.zeros(N)
    if hid['second_outgas'] and variant == 'A':
        q2 = 0.25 * p['q300'] / (300.0 ** (-0.5))   # 25% of the main source at 300 h
        out2 = q2 * tau ** (-0.5) * np.exp(-80e3 / R * (1 / Tg - 1 / TREF))
    hum = np.zeros(N)
    if hid['vent_humidity'] and vent_k is not None:
        hum[vent_k:] = 1.0 * (2.0 / s['D']) * np.exp(-(k[vent_k:] - vent_k) * DT / 60.0)
    pod_eff = p['gamma'] * pods if variant == 'A' else p['gamma'] * 3.0 * np.sqrt(pods)
    leak = leak_series(scn['leak'], N, r_misc)
    base = perm + out_main + out2 + hum + pod_eff + leak

    # ---- gauge
    rw = np.cumsum(r_rw.normal(0, RW_SIG * np.sqrt(DT), N))
    b = p['beta'] * (Tgauge - TREF) + rw
    if variant == 'B':
        b = b + 0.002 * (Tgauge - TREF) ** 2
    eps = r_eps.normal(0, SIGMA_P, N)
    kappa = p['kappa'] if hid['gauge_glitch'] else 0.0

    # ---- pressure dynamics with on/off pump
    Pt = np.zeros(N)
    P = 97.0
    k_i = 0
    wins = []          # (i0, i1) inclusive sample indices
    in_off = True
    start = 0
    Pt[0] = P
    while k_i < N - 1:
        rate = base[k_i] + P * gdT[k_i]
        P = P + rate * DT
        k_i += 1
        if P < 60:
            P = 60.0
        Pt[k_i] = P
        if P >= P_HI:
            wins.append((start, k_i))
            # pump-on for 3 steps, then restart at 97
            for _ in range(3):
                if k_i < N - 1:
                    k_i += 1
                    Pt[k_i] = np.nan
            if k_i < N - 1:
                P = P_LO
                k_i += 1
                Pt[k_i] = P
                start = k_i
    wins.append((start, min(k_i, N - 1)))
    # cut long pump-off periods into windows of <= WIN_MAX samples
    W = []
    for a, bnd in wins:
        i = a
        while i < bnd:
            j = min(i + WIN_MAX - 1, bnd)
            if j - i + 1 >= WIN_MIN:
                W.append((i, j))
            i = j + 1
    W = np.array(W, dtype=int)

    # ---- prefix-sum OLS slopes (per hour)
    def slope(y):
        yy = np.where(np.isnan(y), 0.0, y)
        Sy = np.concatenate([[0], np.cumsum(yy)])
        Sky = np.concatenate([[0], np.cumsum(k * yy)])
        i0, i1 = W[:, 0], W[:, 1] + 1
        n = (i1 - i0).astype(float)
        sk = (np.cumsum(k.astype(float))[i1 - 1] - np.concatenate([[0], np.cumsum(k.astype(float))])[i0])
        skk = (np.cumsum(k.astype(float) ** 2)[i1 - 1] - np.concatenate([[0], np.cumsum(k.astype(float) ** 2)])[i0])
        sy = Sy[i1] - Sy[i0]
        sky = Sky[i1] - Sky[i0]
        den = n * skk - sk ** 2
        return (n * sky - sk * sy) / den / DT

    def wmean(y):
        yy = np.where(np.isnan(y), 0.0, y)
        S = np.concatenate([[0], np.cumsum(yy)])
        i0, i1 = W[:, 0], W[:, 1] + 1
        return (S[i1] - S[i0]) / (i1 - i0)

    nW = (W[:, 1] - W[:, 0] + 1)
    rise = (1 - kappa) * slope(Pt) + slope(b) + slope(eps)
    if hid['gauge_glitch']:
        gl = r_gl.random(len(W)) < 0.005
        rise = rise + gl * r_gl.normal(0, 0.25, len(W))
    mid = (W[:, 0] + W[:, 1]) // 2
    obs = dict(
        t=mid * DT, dur=nW * DT, n=nW.astype(float), rise=rise,
        T=wmean(wall_meas), tube_slope=slope(wall_meas), amb_slope=slope(amb_meas),
        pods=wmean(pods), tau=tau[mid], hour=hod[mid], day=dayi[mid],
    )

    # ---- controlled hold tests (tube closed to pods; 24 h; used only by guardrail 5)
    holds = dict(t=[], rise=[], T=[], tau=[])
    for d in np.arange(hold_every_days, scn['days'] - 1, hold_every_days):
        k0 = int((d + 0.12) * SPD)
        k1 = k0 + SPD
        if k1 >= N:
            break
        src = (perm + out_main + out2 + hum + leak)[k0:k1].mean()
        gas = 100.0 / Tg[k0:k1].mean() * (Tg[k1] - Tg[k0]) / 24.0
        meas_gas = 100.0 / wall_meas[k0:k1].mean() * (wall_meas[k1] - wall_meas[k0]) / 24.0
        noise = r_hold.normal(0, 0.006)
        holds['t'].append(k0 * DT + 12)
        holds['rise'].append(src + gas - meas_gas + noise)     # what the operator can compute
        holds['T'].append(wall_meas[k0:k1].mean())
        holds['tau'].append(tau[k0 + SPD // 2])
    holds = {kk: np.array(v) for kk, v in holds.items()}

    # ---- what the operator is told
    announce = []
    if ev and ev['type'] in ('outdoor_move', 'seal_swap'):
        new = dict(s)
        if ev['type'] == 'outdoor_move':
            new['outdoor'] = True
            new['amp'] = ev['new_amp']
        else:
            new['seal'] = ev['new_seal']
        announce.append(dict(t=k_ev * DT, settings=new))
    if ev and ev['type'] == 'vent':
        announce.append(dict(t=k_ev * DT, settings=dict(s), vent=True))

    truth = dict(
        leak_mean=wmean(leak), leak_series=leak, event=ev, leak_spec=scn['leak'],
        quiet_ref=None,
    )
    return dict(obs=obs, settings=dict(s), announce=announce, holds=holds, truth=truth,
                days=scn['days'])


def observations(ds):
    """The ONLY view detectors get."""
    return dict(obs=ds['obs'], settings=ds['settings'], announce=ds['announce'],
                holds=ds['holds'], days=ds['days'])


if __name__ == '__main__':
    import time
    t0 = time.time()
    scn = make_scenario(5, 'test', leak=dict(type='ramp', size=0.1))
    ds = simulate(scn)
    o = ds['obs']
    print('windows', len(o['t']), 'sim time', round(time.time() - t0, 3), 's')
    print('rise mean/sd', o['rise'].mean().round(3), o['rise'].std().round(3))
    print(scn['settings'])
