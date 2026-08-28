#!/usr/bin/env python3
"""
btc60_coinbase_validation.py — phase-6: rerun committee + timeboxes on
COINBASE candles (the bot's actual runtime data source).
======================================================================
Phases 1-5 ran on yfinance BTC-USD 5m.  The production bot consumes
Coinbase Advanced Trade public candles, whose prints (and real volume)
differ slightly.  This script:

  1. Pages the PUBLIC Coinbase candles endpoint (350 bars/request) to
     fetch ~46 days of BTC-USD 5m OHLCV.
  2. Runs the same combined_scalp engine over it.
  3. Re-scores the 5 committee members (±$100/30min first-touch),
     the pooled committee, and the 3h UTC timeboxes — with weekly folds.
  4. Reports Coinbase-vs-yfinance agreement and REAL volume rhythm.

Output: btc60_coinbase_validation.md (this folder)
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

import aiohttp
import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent

def _main_root(p: Path) -> Path:
    parts = p.parts
    for i, part in enumerate(parts[:-1]):
        if part.lower() == ".claude" and parts[i + 1].lower() == "worktrees":
            return Path(*parts[:i])
    return p

_REPO = _main_root(_HERE.parents[3])
_ST = _REPO / "stock-trade"
sys.path.insert(0, str(_ST))
_spec = importlib.util.spec_from_file_location("t38", _ST / "38trades_signals.py")
t38 = importlib.util.module_from_spec(_spec)
sys.modules["t38"] = t38
_spec.loader.exec_module(t38)

from combined_scalp import CombinedScalpEngine, EngineConfig, DataConfig  # noqa: E402

sys.path.insert(0, str(_HERE))
from backtest_signals_btc60 import (   # noqa: E402
    outcomes_100, entries_of, K_CONF, ENGINE_SIGS)
from btc60_validate_ensemble import wilson_lb  # noqa: E402

DAYS = 46
GRAN_S = 300
PAGE = 350                      # Coinbase max candles per request
URL = ("https://api.coinbase.com/api/v3/brokerage/market/products/"
       "BTC-USD/candles")
BOX_H = 3


async def fetch_all(days: int) -> pd.DataFrame:
    end = int(time.time())
    start = end - days * 86400
    frames = []
    async with aiohttp.ClientSession() as s:
        t0 = start
        while t0 < end:
            t1 = min(t0 + PAGE * GRAN_S, end)
            params = {"start": str(t0), "end": str(t1),
                      "granularity": "FIVE_MINUTE"}
            for attempt in range(3):
                try:
                    async with s.get(URL, params=params,
                                     timeout=aiohttp.ClientTimeout(total=15)) as r:
                        if r.status != 200:
                            body = await r.text()
                            raise RuntimeError(f"HTTP {r.status}: {body[:120]}")
                        data = await r.json()
                    candles = data.get("candles", [])
                    if candles:
                        frames.append(pd.DataFrame(candles))
                    break
                except Exception as e:
                    if attempt == 2:
                        print(f"  page {t0} failed: {e}")
                    await asyncio.sleep(1 + attempt)
            t0 = t1
            await asyncio.sleep(0.15)          # stay under public rate limit
    if not frames:
        raise SystemExit("no candles fetched")
    df = pd.concat(frames, ignore_index=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["start"] = df["start"].astype(int)
    df = (df.drop_duplicates("start").sort_values("start")
            .reset_index(drop=True))
    idx = pd.to_datetime(df["start"], unit="s", utc=True)
    out = pd.DataFrame({"Open": df["open"].values, "High": df["high"].values,
                        "Low": df["low"].values, "Close": df["close"].values,
                        "Volume": df["volume"].values},
                       index=pd.DatetimeIndex(idx, name="Datetime"))
    # drop the still-forming last bar
    if out.index[-1] + pd.Timedelta(seconds=GRAN_S) > pd.Timestamp.now(tz="UTC"):
        out = out.iloc[:-1]
    return out


def main() -> None:
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

    print(f"Paging Coinbase 5m candles for {DAYS} days…")
    raw = asyncio.run(fetch_all(DAYS))
    print(f"  candles: {len(raw)}  {raw.index[0]} → {raw.index[-1]}")

    cfg = EngineConfig(data=DataConfig(
        interval="5m", include_premarket=True, include_postmarket=True,
        rth_only_signals=False, clean_extended_hours=True,
        drop_noisy_candles=True, noise_rth_pct=2.5, noise_eh_pct=2.0))
    cfg.sr.lookback_hours = 24.0
    cfg.sr.recalc_minutes = 30
    res = CombinedScalpEngine(cfg).run(raw)
    d = res.df
    days = (d.index[-1] - d.index[0]) / pd.Timedelta(days=1)
    print(f"  engine bars: {len(d)} ({days:.0f}d)")

    (reach_l, ft_l, _), (reach_s, ft_s, _) = outcomes_100(d)
    ft = {"LONG": ft_l, "SHORT": ft_s}

    o, h, l, c = (d[x].to_numpy() for x in ("Open", "High", "Low", "Close"))
    v = d["Volume"].to_numpy(float)
    adx = d["adx"].to_numpy()
    pdi, mdi = d["plus_di"].to_numpy(), d["minus_di"].to_numpy()
    poc = d["poc"].to_numpy()
    cs = pd.Series(c)
    prev_c = np.r_[np.nan, c[:-1]]
    net3 = cs.diff(3).to_numpy()
    ma, sd = cs.rolling(20).mean(), cs.rolling(20).std()
    upper, lower = (ma + 2 * sd).to_numpy(), (ma - 2 * sd).to_numpy()
    w_pct = (4 * sd / ma).rolling(288, min_periods=60).rank(pct=True).to_numpy()
    mom_up = d["mom_up"].to_numpy().astype(bool)
    adx20 = np.nan_to_num(adx) > 20
    adx275 = np.nan_to_num(adx) > 27.5
    adx30 = np.nan_to_num(adx) > 30

    def roll(colL, colS):
        fl = pd.Series(d[colL].to_numpy().astype(bool)).rolling(
            K_CONF, min_periods=1).max().to_numpy().astype(bool)
        fs = pd.Series(d[colS].to_numpy().astype(bool)).rolling(
            K_CONF, min_periods=1).max().to_numpy().astype(bool)
        return fl, fs

    adxL, _ = roll(*ENGINE_SIGS["adx_di_cross"])

    COMMITTEE = {
        ("SHORT", "S1 sqz_break+di_dom"):
            (w_pct < .2) & (c < lower) & (mdi > pdi),
        ("LONG", "S2 poc_cross+adx30"):
            (prev_c <= poc) & (c > poc) & adx30,
        ("LONG", "S3 adx_di_cross+mom+adx20"):
            adxL & mom_up & adx20,
        ("SHORT", "S4 mom3_60+poc_cross"):
            (net3 <= -60) & (prev_c >= poc) & (c < poc),
        ("SHORT", "S5 poc_cross+adx27.5"):
            (prev_c >= poc) & (c < poc) & adx275,
    }

    hour = d.index.hour.to_numpy()
    box = (hour // BOX_H).astype(int)
    age_h = ((d.index[-1] - d.index) / pd.Timedelta(hours=1)).to_numpy()
    fold_id = (age_h // 168).astype(int)

    rep = [
        f"# Coinbase-candle validation — committee + timeboxes, {days:.0f} days",
        f"- candles {len(d)}, {d.index[0]} → {d.index[-1]} (source: Coinbase "
        f"public /market/products/BTC-USD/candles, paged {PAGE}/req)",
        "- same engine, same committee definitions as phases 2-5 (yfinance)\n",
        "## 1. Committee members on Coinbase data",
        "member | dir | n | acc% | wilsonLB | /day",
    ]

    member_stats = {}
    for (direction, name), mask in COMMITTEE.items():
        mask = np.asarray(mask, bool) & ~np.isnan(prev_c)
        idx = entries_of(mask)
        r = ft[direction][idx]
        res_m = np.isin(r, ("win", "loss"))
        wins, tot = int((r[res_m] == "win").sum()), int(res_m.sum())
        acc = wins / tot * 100 if tot else np.nan
        member_stats[name] = (wins, tot)
        rep.append(f"{name:28s} | {direction:5s} | {tot:3d} | {acc:5.1f} | "
                   f"{wilson_lb(wins, tot):5.1f} | {idx.size/days:.2f}")

    # pooled + timeboxes
    pooled = {b: [0, 0] for b in range(24 // BOX_H)}
    per_fold: dict[int, list[int]] = {}
    for (direction, name), mask in COMMITTEE.items():
        mask = np.asarray(mask, bool) & ~np.isnan(prev_c)
        idx = entries_of(mask)
        r = ft[direction][idx]
        for b in range(24 // BOX_H):
            ii = idx[box[idx] == b]
            rr = ft[direction][ii]; rs = np.isin(rr, ("win", "loss"))
            pooled[b][0] += int((rr[rs] == "win").sum())
            pooled[b][1] += int(rs.sum())
        for f in np.unique(fold_id[idx]):
            ii = idx[fold_id[idx] == f]
            rr = ft[direction][ii]; rs = np.isin(rr, ("win", "loss"))
            pf = per_fold.setdefault(int(f), [0, 0])
            pf[0] += int((rr[rs] == "win").sum()); pf[1] += int(rs.sum())

    rep.append("\n## 2. Pooled committee per 3h UTC timebox")
    rep.append("box(UTC) | n | acc% | wilsonLB | yfinance verdict")
    YF = {0: "BAD", 1: "good", 2: "good", 3: "good~", 4: "good",
          5: "BAD", 6: "good", 7: "good"}
    for b, (w, t) in sorted(pooled.items()):
        if t == 0: continue
        rep.append(f"{b*BOX_H:02d}-{b*BOX_H+BOX_H:02d} | {t:3d} | "
                   f"{w/t*100:5.1f} | {wilson_lb(w, t):5.1f} | {YF[b]}")

    good = [1, 2, 3, 4, 6, 7]
    w_all = sum(w for w, t in pooled.values()); t_all = sum(t for _, t in pooled.values())
    w_g = sum(pooled[b][0] for b in good); t_g = sum(pooled[b][1] for b in good)
    w_b, t_b = w_all - w_g, t_all - t_g
    for label, w, t in (("ALL hours", w_all, t_all),
                        ("GOOD boxes (yfinance def)", w_g, t_g),
                        ("BAD boxes", w_b, t_b)):
        acc = w / t * 100 if t else np.nan
        ev = acc / 100 * 20 - (1 - acc / 100) * 16.5
        rep.append(f"- **{label}**: n={t}, acc {acc:.1f}% "
                   f"(LB {wilson_lb(w, t):.1f}%), EV/50c ≈ {ev:+.1f}c")

    rep.append("\n## 3. Weekly folds (pooled committee, all hours)")
    rep.append(" ".join(f"w{f}:{a}/{b}" for f, (a, b) in sorted(per_fold.items())))

    # ---- 3b. TRIMMED committee: only members that survive on Coinbase ------
    TRIM = {k: v for k, v in COMMITTEE.items()
            if k[1].startswith(("S1", "S2", "S3"))}
    pooled_t = {b: [0, 0] for b in range(24 // BOX_H)}
    fold_t: dict[int, list[int]] = {}
    fires = 0
    for (direction, name), mask in TRIM.items():
        mask = np.asarray(mask, bool) & ~np.isnan(prev_c)
        idx = entries_of(mask)
        fires += idx.size
        for b in range(24 // BOX_H):
            ii = idx[box[idx] == b]
            rr = ft[direction][ii]; rs = np.isin(rr, ("win", "loss"))
            pooled_t[b][0] += int((rr[rs] == "win").sum())
            pooled_t[b][1] += int(rs.sum())
        for f in np.unique(fold_id[idx]):
            ii = idx[fold_id[idx] == f]
            rr = ft[direction][ii]; rs = np.isin(rr, ("win", "loss"))
            pf = fold_t.setdefault(int(f), [0, 0])
            pf[0] += int((rr[rs] == "win").sum()); pf[1] += int(rs.sum())

    rep.append("\n## 3b. TRIMMED committee (S1+S2+S3 only) per timebox")
    rep.append("box(UTC) | n | acc% | wilsonLB")
    for b, (w, t) in sorted(pooled_t.items()):
        if t == 0: continue
        rep.append(f"{b*BOX_H:02d}-{b*BOX_H+BOX_H:02d} | {t:3d} | "
                   f"{w/t*100:5.1f} | {wilson_lb(w, t):5.1f}")
    # coinbase-native good boxes: acc >= 55 with n >= 20
    good_cb = [b for b, (w, t) in pooled_t.items() if t >= 20 and w / t >= .55]
    w_all_t = sum(w for w, t in pooled_t.values())
    t_all_t = sum(t for _, t in pooled_t.values())
    w_gt = sum(pooled_t[b][0] for b in good_cb)
    t_gt = sum(pooled_t[b][1] for b in good_cb)
    for label, w, t in (("TRIMMED all hours", w_all_t, t_all_t),
                        (f"TRIMMED good boxes {sorted(good_cb)}", w_gt, t_gt)):
        acc = w / t * 100 if t else np.nan
        ev = acc / 100 * 20 - (1 - acc / 100) * 16.5
        rep.append(f"- **{label}**: n={t}, acc {acc:.1f}% "
                   f"(LB {wilson_lb(w, t):.1f}%), EV/50c ≈ {ev:+.1f}c, "
                   f"{fires/days:.1f} fires/day (all-hours)")
    rep.append("- TRIMMED weekly folds: "
               + " ".join(f"w{f}:{a}/{b}" for f, (a, b) in sorted(fold_t.items())))

    rep.append("\n## 4. REAL volume rhythm (Coinbase, median per UTC hour)")
    rep.append("hour | med volume (BTC) | med 30-min range $")
    rng30 = (pd.Series(h).rolling(6).max() - pd.Series(l).rolling(6).min()).to_numpy()
    for hh in range(24):
        m = hour == hh
        rep.append(f"{hh:02d}   | {np.median(v[m]):8.2f} | "
                   f"{np.nanmedian(rng30[m]):6.0f}")

    out = _HERE / "btc60_coinbase_validation.md"
    out.write_text("\n".join(rep), encoding="utf-8")
    print(f"report → {out}")
    for line in rep[4:12] + rep[-40:-28]:
        print(line)


if __name__ == "__main__":
    main()
