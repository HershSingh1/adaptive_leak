"""analyze.py -- turns results/raw_*.csv into summary tables (results/summary.md) and figures."""
import os, sys, pickle
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'results')
R = {k: pd.read_csv(os.path.join(OUT, 'raw_%s.csv' % k)) for k in ['E0', 'E1', 'E2', 'E3', 'E4', 'E6', 'E7']}
SHORT = {'A  Night-only level model': 'A Night-only', 'B  Static physics, calibrated once': 'B Static physics',
         'C  Adaptive, no guardrails': 'C Adaptive, no guardrails', 'D  Adaptive, all guardrails': 'D Adaptive + guardrails'}
COL = {'A Night-only': '#8a8984', 'B Static physics': '#6250d6', 'C Adaptive, no guardrails': '#eb6834',
       'D Adaptive + guardrails': '#2a78d6'}
INK, SUB, GRID = '#0b0b0b', '#52514e', '#e4e3df'
plt.rcParams.update({'font.size': 10, 'axes.edgecolor': GRID, 'axes.labelcolor': SUB, 'xtick.color': SUB,
                     'ytick.color': SUB, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.6, 'axes.axisbelow': True,
                     'figure.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb'})
for d in R.values():
    d['det'] = d['name'].map(lambda n: SHORT.get(n, n))
MAIN = list(SHORT.values())
md = []


def tab(df, title, note=''):
    md.append('\n### %s\n' % title)
    if note:
        md.append(note + '\n')
    md.append(df.to_markdown())
    md.append('')


# ---------- E0 / E1 false alarms
e0 = R['E0'].groupby('name').agg(fa30=('fa30', 'mean'), fa_cusum=('fa_cusum', 'mean'), fa_frozen=('fa_frozen', 'mean'),
                                 fa_verify=('fa_verify', 'mean')).round(2)
tab(e0, 'E0  False alarms per 30 days on clean test tubes (all hidden effects, unseen materials; budget was 1.0 on tune)')
e1 = R['E1'].copy()
e1['event'] = e1.job.str.replace('E1_', '')
g = e1.groupby(['name', 'event'])
t1 = pd.DataFrame(dict(week_after=g.fa_week_after.mean(), steady_per30=(g.fa_other.sum() / g.days_other.sum() * 30)))
t1 = t1.unstack('event').round(2)
tab(t1, 'E1  Alarms per run in the 7 days after a change (week_after) and false alarms per 30 days elsewhere (steady_per30)')
rms = e1.groupby(['name', 'event'])[['z_d0_3', 'z_d3_7']].mean().round(2).unstack('event')
tab(rms, 'E1  Residual size after a change (RMS of standardized residual; about 1.0 means well-behaved)')

# ---------- E2
e2 = R['E2'].copy()
e2['typ'] = e2.job.str.split('_').str[1]
e2['size'] = e2.job.str.split('_').str[2].astype(float)
det = e2.groupby(['name', 'typ', 'size']).detected.mean().unstack(['typ', 'size']).round(2)
tab(det, 'E2  Share of leaks detected (leak size = extra rise in Pa/h)')
dl = (e2.groupby(['name', 'typ', 'size']).delay_h.median().unstack(['typ', 'size'])).round(0)
tab(dl, 'E2  Median detection delay (hours)')

# ---------- E3
e3 = R['E3'].copy()
e3['size'] = e3.job.str.split('_').str[1].astype(float)
t3 = e3.groupby(['name', 'size']).agg(detected=('detected', 'mean'), delay_days=('delay_h', lambda x: np.nanmedian(x) / 24),
                                      absorbed=('absorbed', 'median'), fa_before=('fa_pre', 'mean')).unstack('size').round(2)
tab(t3, 'E3  Creeping leaks (grow over 21 days; 120-day runs). absorbed = share of the leak the model had already learned as normal when it alarmed')
# ---------- E4
e4 = R['E4'].copy()
e4['cond'] = e4.job.str.split('_').str[1]
e4['kind'] = e4.job.str.split('_').str[-1]
fa4 = e4[e4.kind == 'clean'].groupby(['cond', 'det']).fa30.mean().unstack('det')[MAIN].round(2)
dt4 = e4[e4.kind == 'leak'].groupby(['cond', 'det']).detected.mean().unstack('det')[MAIN].round(2)
order = ['none'] + [c for c in fa4.index if c not in ('none', 'all')] + ['all']
tab(fa4.loc[order], 'E4  False alarms per 30 days, one hidden effect switched on at a time')
tab(dt4.loc[order], 'E4  Share of 0.10 Pa/h ramp leaks detected, one hidden effect on at a time')
# ---------- E6
e6 = R['E6'].copy()
e6['kind'] = e6.job.str.replace('E6_', '')
a = e6[e6.kind == 'clean'].groupby('det').fa30.mean().round(2)
b = e6[e6.kind != 'clean'].groupby(['det', 'kind']).detected.mean().unstack('kind').round(2)
tab(pd.concat([a.rename('FA per 30 d (clean)'), b], axis=1).loc[MAIN],
    'E6  Simulator B (different functional forms; detector and thresholds trained on simulator A)')
# ---------- E7
e7 = R['E7'].groupby('name')[['d0_1', 'd1_3', 'd3_10']].mean().round(3)
tab(e7, 'E7  Warm-up: mean absolute one-step error (Pa/h) by days since commissioning')
open(os.path.join(OUT, 'summary.md'), 'w').write('\n'.join(md))

# ================= figures
def bars(ax, df, cols, width=0.8):
    x = np.arange(len(df))
    w = width / len(cols)
    for i, c in enumerate(cols):
        ax.bar(x + (i - (len(cols) - 1) / 2) * w, df[c].values, w * 0.88, color=COL[c], label=c)
    ax.set_xticks(x)
    return x

# Fig 1: detection of ramp leaks
fig, axs = plt.subplots(1, 2, figsize=(10.5, 3.8))
sel = e2[e2.typ == 'ramp']
d1 = sel.groupby(['size', 'det']).detected.mean().unstack('det')[MAIN]
x = bars(axs[0], d1, MAIN)
axs[0].set_xticklabels(['%.2f' % s for s in d1.index]); axs[0].set_ylim(0, 1.05)
axs[0].set_xlabel('leak size (extra rise, Pa/h)'); axs[0].set_title('Share of ramp leaks detected', loc='left', color=INK, fontsize=11)
d2 = sel.groupby(['size', 'det']).delay_h.median().unstack('det')[MAIN]
bars(axs[1], d2, MAIN)
axs[1].set_xticklabels(['%.2f' % s for s in d2.index]); axs[1].set_xlabel('leak size (extra rise, Pa/h)')
axs[1].set_title('Median hours to alarm', loc='left', color=INK, fontsize=11)
h, l = axs[0].get_legend_handles_labels()
fig.legend(h, l, loc='lower center', ncol=4, frameon=False, fontsize=9)
fig.tight_layout(rect=(0, 0.08, 1, 1)); fig.savefig(os.path.join(OUT, 'fig1_detection.png'), dpi=160); plt.close(fig)

# Fig 2: absorption / creeping leaks
v = e3[e3.name.isin(['C  Adaptive, no guardrails', 'D- no pause', 'D- fast learning', 'D- no hold test', 'D- no frozen copy',
                     'D- no bounds', 'D  Adaptive, all guardrails'])]
lab = {'C  Adaptive, no guardrails': 'C: none', 'D- no pause': 'D minus pause', 'D- fast learning': 'D minus slow learning',
       'D- no hold test': 'D minus hold test', 'D- no frozen copy': 'D minus frozen copy', 'D- no bounds': 'D minus bounds',
       'D  Adaptive, all guardrails': 'D: all five'}
p = v.groupby('name').agg(absorbed=('absorbed', 'median'), delay=('delay_h', lambda s: np.nanmedian(s) / 24)).loc[list(lab)]
fig, axs = plt.subplots(1, 2, figsize=(10.5, 3.8))
y = np.arange(len(p))[::-1]
axs[0].barh(y, p.absorbed.values, 0.6, color=['#eb6834'] + ['#8a8984'] * 5 + ['#2a78d6'])
axs[0].set_yticks(y); axs[0].set_yticklabels([lab[n] for n in p.index]); axs[0].set_xlabel('share of leak learned away before the alarm (median)')
axs[0].set_title('How much of a creeping leak gets absorbed', loc='left', color=INK, fontsize=11)
axs[1].barh(y, p.delay.values, 0.6, color=['#eb6834'] + ['#8a8984'] * 5 + ['#2a78d6'])
axs[1].set_yticks(y); axs[1].set_yticklabels([]); axs[1].set_xlabel('days from leak start to alarm (median)')
axs[1].set_title('How long the alarm takes', loc='left', color=INK, fontsize=11)
fig.tight_layout(); fig.savefig(os.path.join(OUT, 'fig2_absorption.png'), dpi=160); plt.close(fig)

# Fig 3: hidden effects
fig, ax = plt.subplots(figsize=(10.5, 3.9))
f4 = fa4.loc[order]
bars(ax, f4, MAIN)
NICE = dict(none='no hidden\neffect', gauge='gauge\nglitches', seal='seal\naging', second='second\noutgassing', solar='sunlight +\nthermal lag', vent='vent\nhumidity', wind='wind /\nrain', all='all six')
ax.set_xticklabels([NICE[c] for c in f4.index], rotation=0, fontsize=9)
ax.axhline(1.0, color=INK, lw=0.8, ls='--'); ax.text(-0.45, 1.04, 'false-alarm budget used for tuning = 1', ha='left', color=SUB, fontsize=9)
ax.set_ylabel('false alarms per 30 days'); ax.set_title('False alarms when one unseen physical effect is switched on', loc='left', color=INK, fontsize=11)
ax.legend(frameon=False, ncol=4, fontsize=9, loc='upper left')
fig.tight_layout(); fig.savefig(os.path.join(OUT, 'fig3_hidden_effects.png'), dpi=160); plt.close(fig)

# Fig 4: one example run
from truth_sim import make_scenario, simulate, observations, DT
import model as M
guess, cfgs = pickle.load(open(os.path.join(OUT, 'fitted.pkl'), 'rb'))
best = None
for sd in range(40000, 40040):
    scn = make_scenario(sd, 'test', days=120, leak=dict(type='creep', size=0.10, creep_days=21.0, start_day=20.0))
    if scn['settings']['outdoor']:
        best = scn; break
ds = simulate(best); v = observations(ds)
tw = observations(simulate(dict(best, leak=None)))
rD = M.run(v, cfgs['D  Adaptive, all guardrails'], guess)
rC = M.run(v, cfgs['C  Adaptive, no guardrails'], guess)
rB = M.run(v, cfgs['B  Static physics, calibrated once'], guess)
rDt = M.run(tw, cfgs['D  Adaptive, all guardrails'], guess)
rCt = M.run(tw, cfgs['C  Adaptive, no guardrails'], guess)
tt = v['obs']['t'] / 24
tl = np.arange(len(ds['truth']['leak_series'])) * DT / 24
fig, axs = plt.subplots(3, 1, figsize=(10.5, 8.2), sharex=True)
axs[0].plot(tt, v['obs']['rise'], '.', ms=3, color='#8a8984', label='measured rise rate')
axs[0].plot(tl, ds['truth']['leak_series'], color=INK, lw=1.6, label='true leak (hidden from detector)')
axs[0].set_ylabel('Pa/h'); axs[0].set_title('What the detector sees, and the leak it cannot see', loc='left', color=INK, fontsize=11)
axs[0].legend(frameon=False, fontsize=9, loc='lower right', bbox_to_anchor=(1.0, 1.0), ncol=2)
tc = rC['t'] / 24
axs[1].plot(tl, ds['truth']['leak_series'], color=INK, lw=1.6, label='true leak')
axs[1].plot(rC['t'] / 24, rC['Lref'] - rCt['Lref'][:len(rC['Lref'])] if len(rCt['Lref']) == len(rC['Lref']) else np.interp(rC['t'], rCt['t'], rCt['Lref']) * 0 + np.nan, color='#eb6834', lw=1.4)
cC = np.interp(rC['t'], rCt['t'], rCt['Lref'])
cD = np.interp(rD['t'], rDt['t'], rDt['Lref'])
axs[1].lines[-1].remove()
axs[1].plot(rC['t'] / 24, np.nan_to_num(rC['Lref'] - cC), color='#eb6834', lw=1.4, label='C: learned as "normal"')
axs[1].plot(rD['t'] / 24, np.nan_to_num(rD['Lref'] - cD), color='#2a78d6', lw=1.4, label='D: learned as "normal"')
axs[1].set_ylabel('Pa/h'); axs[1].set_title('How much of the leak each adaptive model absorbed into its baseline', loc='left', color=INK, fontsize=11)
axs[1].legend(frameon=False, fontsize=9, loc='upper left')
for i, (nm, r, c) in enumerate([('B', rB, '#6250d6'), ('C', rC, '#eb6834'), ('D', rD, '#2a78d6')]):
    a = [x[0] / 24 for x in r['alarms']]
    axs[2].plot(a, np.full(len(a), 2 - i), '|', ms=14, mew=2, color=c)
axs[2].set_yticks([2, 1, 0]); axs[2].set_yticklabels(['B static', 'C no guardrails', 'D guardrails']); axs[2].set_ylim(-0.7, 2.7)
axs[2].set_title('Alarms raised (leak starts at day 20)', loc='left', color=INK, fontsize=11); axs[2].set_xlabel('day')
for a in axs:
    a.axvline(20, color=GRID, lw=1.2)
fig.tight_layout(); fig.savefig(os.path.join(OUT, 'fig4_example_run.png'), dpi=160); plt.close(fig)
print(open(os.path.join(OUT, 'summary.md')).read())
