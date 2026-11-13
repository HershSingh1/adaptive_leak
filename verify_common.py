"""Shared constants and loaders for the verification scripts (frozen-split protocol, see VERIFICATION_PLAN.md)."""
import os, sys, json, hashlib, pickle
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model as M
from truth_sim import make_scenario, simulate, observations
import fixed_cusum as F

OUT = os.path.join(HERE, 'results_verify')
os.makedirs(OUT, exist_ok=True)

TRAIN_SEEDS = list(range(10000, 10240))
TUNE_SEEDS = list(range(20000, 20080))
CLEAN_SEEDS = list(range(50000, 50300))      # 300 clean test runs
SWEEP_SEEDS = list(range(51000, 51030))      # 30 tubes, reused at every growth rate
CLEAN_DAYS, SWEEP_DAYS = 60, 180
LEAK_SIZE, LEAK_START_DAY = 0.10, 20.0
CREEP_DAYS = [2, 7, 14, 28, 56, 112]         # growth = LEAK_SIZE / creep_days  Pa/h per day
HORIZON_AFTER_FULL_DAYS = 30
WIN = (10 * 24.0, 40 * 24.0)                 # 30-day evaluation window (hours)
WORKERS = max(1, min(7, (os.cpu_count() or 2) - 1))

G = {}


def init_worker(guess, cfgs):
    G['guess'], G['cfgs'] = guess, cfgs


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def load_frozen():
    """Load fitted (guess, cfgs); refuse to run if it differs from the committed thresholds.json."""
    th = json.load(open(os.path.join(OUT, 'thresholds.json')))
    pk = os.path.join(OUT, 'fitted.pkl')
    if sha256(pk) != th['fitted_pkl_sha256']:
        raise SystemExit('fitted.pkl does not match thresholds.json -- test split is frozen, refusing to run.')
    guess, cfgs = pickle.load(open(pk, 'rb'))
    for nm, c in th['detectors'].items():          # thresholds in the pickle must equal the committed ones
        for k in ('h', 'h_d', 'c_v', 'rho', 'pause'):
            assert cfgs[nm].get(k) == c.get(k), (nm, k)
    return guess, cfgs


def alarm_str(al):
    return ';'.join('%.2f:%s' % (a, k) for a, k in al)


def sim_view(scn):
    ds = simulate(scn)
    return ds, observations(ds)
