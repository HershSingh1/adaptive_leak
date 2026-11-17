"""
modelica_adapter.py -- turns a TubeStudy.Tube result CSV into the `view` dict the detectors consume.

What lives HERE and not in the Modelica model (it is instrument behaviour, not tube physics):
  gauge noise (0.10 Pa/sample), gauge random-walk drift, gauge temperature coefficient beta,
  rise under-read kappa, occasional glitches, wall-sensor noise 0.05 K, ambient-sensor noise 0.10 K.
Windowing is done exactly as the detector expects: pump-off periods are cut into windows of 1-6 h,
one OLS slope of the gauge pressure per window (Pa/h).
"""
import sys, os
import numpy as np
from scipy.signal import lfilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import truth_sim as ts

TREF, DT = ts.TREF, ts.DT        # DT = 1/6 h = the 600 s output grid
WIN_MAX, WIN_MIN = ts.WIN_MAX, ts.WIN_MIN


def read_csv(path):
    with open(path) as f:
        head = [h.strip().strip('"') for h in f.readline().strip().split(',')]
    a = np.genfromtxt(path, delimiter=',', skip_header=1)
    return {h: a[:, i] for i, h in enumerate(head)}


def to_view(res, scn, tau0, seed=0, settle=1):
    """res: dict of columns (time[s], Pg, nPumpsReal, Tsensor, Tamb, podsOut, ...)."""
    s, p, hid = scn['settings'], scn['params'], scn['hidden']
    rng = np.random.default_rng(np.random.SeedSequence([seed, 99]))
    t = res['time']; n = len(t)
    # resample to the 600 s grid (omc may add event rows)
    g = np.arange(0, t[-1] + 1, 600.0)
    def rs(x): return np.interp(g, t, x)
    Pg, Tw, Ta, pods = rs(res['Pg']), rs(res['Tsensor']), rs(res['Tamb']), rs(res['podsOut'])
    npump = np.round(rs(res['nPumpsReal']))
    n = len(g); k = np.arange(n); t_h = g / 3600.0
    # gauge as hardware
    a = 1 - np.exp(-DT / 1.0)
    Tgauge = lfilter([a], [1, -(1 - a)], Ta, zi=[(1 - a) * Ta[0]])[0]
    rw = np.cumsum(rng.normal(0, ts.RW_SIG * np.sqrt(DT), n))
    b = p['beta'] * (Tgauge - TREF) + rw
    eps = rng.normal(0, ts.SIGMA_P, n)
    kappa = p['kappa'] if hid.get('gauge_glitch') else 0.0
    Pm = (1 - kappa) * Pg + b + eps
    wall = Tw + rng.normal(0, 0.05, n); amb = Ta + rng.normal(0, 0.10, n)
    # pump events: counter increments, or a pressure drop
    ev = np.zeros(n, bool); ev[1:] = (np.diff(npump) > 0) | (np.diff(Pg) < -0.5)
    starts = [0] + list(np.where(ev)[0]); ends = list(np.where(ev)[0] - 1) + [n - 1]
    W = []
    for a0, b0 in zip(starts, ends):
        i = a0 + (settle if a0 > 0 else 0)
        while i < b0:
            j = min(i + WIN_MAX - 1, b0)
            if j - i + 1 >= WIN_MIN: W.append((i, j))
            i = j + 1
    def slope(y, i, j):
        x = np.arange(i, j + 1) * DT; yy = y[i:j + 1]
        x = x - x.mean()
        return float((x * (yy - yy.mean())).sum() / (x * x).sum())
    rise = np.array([slope(Pm, i, j) for i, j in W])
    if hid.get('gauge_glitch'):
        rise = rise + (rng.random(len(W)) < 0.005) * rng.normal(0, 0.25, len(W))
    mid = np.array([(i + j) // 2 for i, j in W]); nW = np.array([j - i + 1 for i, j in W], float)
    obs = dict(t=mid * DT, dur=nW * DT, n=nW, rise=rise,
               T=np.array([wall[i:j + 1].mean() for i, j in W]),
               tube_slope=np.array([slope(wall, i, j) for i, j in W]),
               amb_slope=np.array([slope(amb, i, j) for i, j in W]),
               pods=np.array([pods[i:j + 1].mean() for i, j in W]),
               tau=np.where(True, tau0 + t_h[mid], 0.0), hour=t_h[mid] % 24, day=t_h[mid] / 24)
    announce = []
    ev_ = scn.get('event')
    if ev_ and ev_['type'] == 'vent':
        announce.append(dict(t=ev_['day'] * 24, settings=dict(s), vent=True))
        obs['tau'] = np.where(obs['t'] >= ev_['day'] * 24, 24 + obs['t'] - ev_['day'] * 24, obs['tau'])
    holds = dict(t=np.array([]), rise=np.array([]), T=np.array([]), tau=np.array([]))
    return dict(obs=obs, settings=dict(s), announce=announce, holds=holds, days=int(t_h[-1] // 24))
