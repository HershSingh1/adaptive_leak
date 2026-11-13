"""Small statistics helpers: Wilson, Garwood (exact Poisson) and seeded bootstrap intervals."""
import numpy as np
from scipy import stats

BOOT_SEED = 12345
Z95 = 1.959963984540054


def wilson(k, n, z=Z95):
    if n == 0:
        return (np.nan, np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - h), min(1.0, c + h))


def garwood_rate(k, exposure_days, per=30.0):
    """k events over exposure_days -> rate per `per` days with exact 95% Poisson interval."""
    lo = 0.0 if k == 0 else stats.chi2.ppf(0.025, 2 * k) / 2
    hi = stats.chi2.ppf(0.975, 2 * k + 2) / 2
    f = per / exposure_days
    return (k * f, lo * f, hi * f)


def boot_ci(x, stat=np.mean, n=4000, seed=BOOT_SEED):
    """percentile bootstrap over the rows of x (one row per independent run)."""
    x = np.asarray(x, float)
    if len(x) == 0:
        return (np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    s = np.array([stat(x[i]) for i in idx])
    return (float(stat(x)), float(np.nanpercentile(s, 2.5)), float(np.nanpercentile(s, 97.5)))


def ratio_boot_ci(num, den, per=30.0, n=4000, seed=BOOT_SEED):
    """pooled rate = sum(num)/sum(den)*per, bootstrapped over runs."""
    num, den = np.asarray(num, float), np.asarray(den, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(num), size=(n, len(num)))
    s = num[idx].sum(1) / den[idx].sum(1) * per
    return (float(num.sum() / den.sum() * per), float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5)))


def paired_diff_ci(a, b, n=4000, seed=BOOT_SEED):
    """mean(a-b) with bootstrap 95% interval; a, b aligned by run."""
    d = np.asarray(a, float) - np.asarray(b, float)
    return boot_ci(d, np.mean, n, seed)
