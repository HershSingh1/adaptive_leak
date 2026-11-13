"""
fixed_cusum.py -- non-adaptive baselines for the verification study.

The statistic is the raw pressure rise, standardised once against the first `warm` days of the run
(sample mean and sd), then a one-sided CUSUM. No temperature/traffic model, no re-learning, no
recalibration after announced changes. Only the threshold h differs between the two baselines:

  F0  h = 5.0, a textbook constant fixed before any run (see VERIFICATION_PLAN.md).
  F1  h tuned once on the tune split by verify_fit.py (same 1 false alarm / 30 d rule as the others).
"""
import numpy as np
import model as M

K_REF = M.K_REF   # 0.5, same CUSUM reference value as the other detectors

F0 = 'F0 Fixed CUSUM, h=5 (no adaptation)'
F1 = 'F1 Fixed CUSUM, h tuned on tune split'
FIXED_CONFIGS = {
    F0: dict(mode='F', adapt=False, warm=10.0, h=5.0),
    F1: dict(mode='F', adapt=False, warm=10.0, h=5.0),   # h overwritten by verify_fit.py
}


def fixed_z(view, warm_days):
    o = view['obs']
    t, y = o['t'], o['rise']
    cal = (t < warm_days * 24.0) & ~np.isnan(y)
    mu = float(np.mean(y[cal]))
    sd = max(float(np.std(y[cal], ddof=1)), 1e-6)
    z = (y - mu) / sd
    mask = (t >= warm_days * 24.0) & ~np.isnan(y)
    return t, np.where(mask, z, np.nan), mask


def run_fixed(view, cfg, h=None):
    t, z, mask = fixed_z(view, cfg['warm'])
    al = M.cusum_alarms(np.nan_to_num(z), mask, t, cfg['h'] if h is None else h)
    return dict(t=t, z=z, mask=mask, alarms=[(a, 'cusum') for a in al], cfg=cfg)


def run_any(view, cfg, guess):
    """Dispatch: baselines here, everything else through model.run (unchanged)."""
    if cfg['mode'] == 'F':
        return run_fixed(view, cfg)
    return M.run(view, cfg, guess)
