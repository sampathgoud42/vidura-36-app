"""Bake the per-engine btc15 report CSVs into btc15_dashboard.html.

Refresh flow:  python btc15_signal.py --days 30    (regenerates all engine CSVs)
               python bake_btc15_dashboard.py      (rebuilds the dashboard)

Reads btc15_signal_report_w{1..5}.csv, embeds every engine, and defaults the
dashboard to the engine with the highest overall next-15 match rate.
"""
import json
import os
from datetime import datetime

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(_HERE, "btc15_dashboard_template.html")
OUT = os.path.join(_HERE, "btc15_dashboard.html")


def _num(v):
    """Round to 2dp, or None for blank/NA cells (pending btc_next15)."""
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None

# (key, label) in display order — mirrors btc15_signal.py's default --engines
ENGINE_SPECS = [
    ("w2", "±2m"),
]

frames = {}
stats = {}
labels = {}
for key, label in ENGINE_SPECS:
    p = os.path.join(_HERE, f"btc15_signal_report_{key}.csv")
    if not os.path.exists(p):
        continue
    df = pd.read_csv(p, keep_default_na=False)
    frames[key] = df
    resolved = df.is_matched.astype(str).str.upper().isin(["TRUE", "FALSE"])
    stats[key] = round((df.is_matched.astype(str).str.upper() == "TRUE").sum()
                       / max(1, resolved.sum()) * 100, 1)
    labels[key] = label
if not frames:
    raise SystemExit("no btc15_signal_report_*.csv engine files found — run btc15_signal.py first")

all_dates = {d for df in frames.values() for d in df["date"]}
dates = sorted(all_dates, key=lambda d: datetime.strptime(d, "%m/%d/%Y"))
di = {d: i for i, d in enumerate(dates)}
dow = [datetime.strptime(d, "%m/%d/%Y").weekday() for d in dates]  # 0=Mon

RATIO_THRESHOLDS = [1.5, 1.75, 2.0, 2.5, 3.0, 4.0]   # expansion ratio |best_move| / pre-range width
TARGET_PCT = 70.0                               # default = smallest threshold reaching this

eng_rows = {}
ratio_stats = {}
ratio_def = {}
for key, df in frames.items():
    # previous record's momentum (knowable at trade time): valid only when the
    # previous row is exactly one quarter-hour earlier; 1/0/-1 = TRUE/FALSE/NA
    dt = pd.to_datetime(df["date"] + " " + df["15minute"], format="%m/%d/%Y %H:%M")
    adjacent = dt.diff() == pd.Timedelta(minutes=15)
    prev_mom_s = df["momentum"].astype(str).str.upper().shift(1)
    prev_m_s   = df["is_matched"].astype(str).str.upper().shift(1)
    mw = (df["minus_max"].astype(float) - df["minus_min"].astype(float)).clip(lower=1)
    bm = pd.to_numeric(df["best_move"].astype(str).str.replace("+", "", regex=False)).abs()
    df = df.assign(
        prev_mom=[{"TRUE": 1, "FALSE": 0}.get(pm, -1) if adj else -1
                  for pm, adj in zip(prev_mom_s, adjacent)],
        prev_matched=[{"TRUE": 1, "FALSE": 0}.get(pm, -1) if adj else -1
                      for pm, adj in zip(prev_m_s, adjacent)],
        ratio=(bm / mw).round(2),
    )
    # threshold -> [match %, kept n] over resolved rows; default = first >= TARGET_PCT
    is_m = df["is_matched"].astype(str).str.upper()
    resolved = is_m.isin(["TRUE", "FALSE"])
    ratio_stats[key] = {}
    ratio_def[key] = RATIO_THRESHOLDS[-1]
    for t in RATIO_THRESHOLDS:
        keep = resolved & (df["ratio"] >= t)
        pct = round((is_m[keep] == "TRUE").mean() * 100, 1) if keep.sum() else 0.0
        ratio_stats[key][str(t)] = [pct, int(keep.sum())]
    for t in RATIO_THRESHOLDS:
        if ratio_stats[key][str(t)][0] >= TARGET_PCT:
            ratio_def[key] = t
            break
    rows = []
    df = df.rename(columns={"15minute": "minute15"})   # named access (position-safe)
    for r in df.itertuples(index=False):
        rows.append([
            di[r.date], int(r.hour), int(r.minute15.split(":")[1]),
            round(float(r.minus_min), 2), round(float(r.minus_max), 2),
            round(float(r.plus_min), 2),  round(float(r.plus_max), 2),
            int(str(r.best_move).replace("+", "")),
            1 if r.direction == "LONG" else 0,
            round(float(r.btc_current15), 2), _num(r.btc_next15),
            {"TRUE": 1, "FALSE": 0}.get(str(r.is_matched).strip().upper(), -1),  # NA/pending -> -1
            {"TRUE": 1, "FALSE": 0}.get(str(r.momentum).strip().upper(), -1),  # NA -> -1
            int(r.prev_mom),                                                   # prev record's momentum
            int(r.prev_matched),                                               # prev record's is_matched
            float(r.ratio),                                                    # |best_move| / pre-range width
        ])
    eng_rows[key] = rows

best = max(stats, key=stats.get)
eng_list = [{"key": k, "label": labels[k], "match": stats[k]}
            for k, _ in ENGINE_SPECS if k in frames]

with open(TPL, encoding="utf-8") as f:
    html = f.read()
html = (html
        .replace("__DATES__",   json.dumps(dates, separators=(",", ":")))
        .replace("__DOW__",     json.dumps(dow,   separators=(",", ":")))
        .replace("__ENGINES__", json.dumps(eng_rows, separators=(",", ":")))
        .replace("__ENGLIST__", json.dumps(eng_list, separators=(",", ":")))
        .replace("__RATIOSTATS__", json.dumps(ratio_stats, separators=(",", ":")))
        .replace("__RATIODEF__",   json.dumps(ratio_def, separators=(",", ":")))
        .replace("__BEST__",    json.dumps(best)))
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

total = sum(len(r) for r in eng_rows.values())
print(f"[bake] {len(eng_rows)} engines, {total} total rows, {len(dates)} dates -> {OUT}")
print("[bake] match % by engine: " + ", ".join(f"{e['label']} {e['match']}%" for e in eng_list))
print(f"[bake] default engine: {labels[best]} ({best})")
print(f"[bake] ratio default (>= {TARGET_PCT:.0f}%): " +
      ", ".join(f"{k} >= {ratio_def[k]} ({ratio_stats[k][str(ratio_def[k])][0]}%)" for k in ratio_def))
