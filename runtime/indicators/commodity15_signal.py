"""
commodity15_signal.py — quarter-hour breakout report for Gold (GC=F) and Silver (SI=F).

Fetches 1-minute candles from Yahoo Finance, then for every quarter-hour
mark T (:00 / :15 / :30 / :45) measures:

    minus window = [T-2m, T)   ->  minus_min / minus_max
    plus  window = [T, T+5m)   ->  plus_min  / plus_max

    up_move   = plus_max - minus_min    (LONG  potential)
    down_move = plus_min - minus_max    (SHORT potential, < 0)

    best_move / direction = larger-magnitude candidate:
        up_move >= |down_move|  ->  LONG,  best_move = +up_move
        otherwise               ->  SHORT, best_move =  down_move

Usage:
    python commodity15_signal.py [--days 5] [--tz America/Chicago]

Outputs (written next to this script):
    gold15_signal_report.csv   — per-mark breakout for GC=F
    silver15_signal_report.csv — per-mark breakout for SI=F
    gold15_signal_hourly.csv   — aggregate stats per hour-of-day
    silver15_signal_hourly.csv — aggregate stats per hour-of-day
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd
import yfinance as yf

_HERE = os.path.dirname(os.path.abspath(__file__))

COMMODITIES = {
    "gold15":   {"ticker": "GC=F", "label": "Gold Futures"},
    "silver15": {"ticker": "SI=F", "label": "Silver Futures"},
    "oil15":    {"ticker": "CL=F", "label": "WTI Crude Oil Futures"},
}


def fetch_1m_candles(symbol: str, days: int) -> pd.DataFrame:
    period = f"{days}d" if days <= 7 else "7d"
    print(f"[commodity15] fetching {period} of 1m candles for {symbol} ...")
    t = yf.Ticker(symbol)
    df = t.history(period=period, interval="1m")
    if df.empty:
        print(f"[commodity15] no candles for {symbol}")
        return pd.DataFrame()
    df = df.reset_index()
    col_dt = "Datetime" if "Datetime" in df.columns else "Date"
    df = df.rename(columns={col_dt: "datetime", "Open": "open", "High": "high",
                            "Low": "low", "Close": "close", "Volume": "volume"})
    df = df[["datetime", "open", "high", "low", "close"]].copy()
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)
    print(f"[commodity15] got {len(df)} candles for {symbol}")
    return df


def build_report(df: pd.DataFrame, tz: str, minus_w: int = 2, plus_w: int = 5) -> pd.DataFrame:
    local = df["datetime"].dt.tz_convert(tz)
    offset = local.dt.minute % 15
    floor15 = local.dt.floor("15min")

    m_mask = offset >= (15 - minus_w)
    p_mask = offset <= (plus_w - 1)
    minus = df.loc[m_mask].copy()
    minus["mark"] = (floor15 + pd.Timedelta(minutes=15))[m_mask]
    plus = df.loc[p_mask].copy()
    plus["mark"] = floor15[p_mask]

    gm = minus.groupby("mark").agg(minus_min=("low", "min"), minus_max=("high", "max"),
                                   n_minus=("low", "size"))
    gp = plus.groupby("mark").agg(plus_min=("low", "min"), plus_max=("high", "max"),
                                  n_plus=("low", "size"))
    rep = gm.join(gp, how="inner")
    full = rep[(rep.n_minus == minus_w) & (rep.n_plus == plus_w)].copy()
    if len(rep) - len(full):
        print(f"[commodity15] skipped {len(rep) - len(full)} marks with incomplete windows")

    full["up_move"] = full.plus_max - full.minus_min
    full["down_move"] = full.plus_min - full.minus_max
    long_wins = full.up_move >= (full.minus_max - full.plus_min)
    full["direction"] = np.where(long_wins, "LONG", "SHORT")
    full["best_move"] = np.where(long_wins, full.up_move, full.down_move)

    close_by_end = pd.Series(df["close"].values,
                             index=local + pd.Timedelta(minutes=1))
    close_by_end = close_by_end[~close_by_end.index.duplicated(keep="last")]
    full["price_current15"] = full.index.map(close_by_end)
    full["price_next15"] = (full.index + pd.Timedelta(minutes=15)).map(close_by_end)
    n_before = len(full)
    full = full.dropna(subset=["price_current15"])
    if n_before - len(full):
        print(f"[commodity15] dropped {n_before - len(full)} marks lacking a close at T")
    full = full.sort_index()

    resolved = full.price_next15.notna()
    if (~resolved).sum():
        print(f"[commodity15] {(~resolved).sum()} pending mark(s) awaiting close@T+15m")
    up = resolved & (full.price_next15 > full.price_current15)
    dn = resolved & (full.price_next15 < full.price_current15)
    full["is_matched"] = np.where(~resolved, "NA",
                         np.where(((full.direction == "LONG") & up)
                                  | ((full.direction == "SHORT") & dn), "TRUE", "FALSE"))

    prev_dir = full["direction"].shift(1)
    adjacent = full.index.to_series().diff() == pd.Timedelta(minutes=15)
    mom_true = ((prev_dir == "LONG") & up) | ((prev_dir == "SHORT") & dn)
    full["momentum"] = np.where(~adjacent | prev_dir.isna() | ~resolved, "NA",
                                np.where(mom_true, "TRUE", "FALSE"))
    return full


def build_detail(rep: pd.DataFrame, created_stamp: str) -> pd.DataFrame:
    out = pd.DataFrame({
        "date":             rep.index.strftime("%m/%d/%Y"),
        "created_on":       created_stamp,
        "hour":             rep.index.hour,
        "15minute":         rep.index.strftime("%H:%M"),
        "minus_min":        rep.minus_min.round(4).values,
        "minus_max":        rep.minus_max.round(4).values,
        "plus_min":         rep.plus_min.round(4).values,
        "plus_max":         rep.plus_max.round(4).values,
        "best_move":        [f"{v:+.4f}" for v in rep.best_move],
        "direction":        rep.direction.values,
        "price_current15":  rep.price_current15.round(4).values,
        "price_next15":     rep.price_next15.round(4).values,
        "is_matched":       rep.is_matched.values,
        "momentum":         rep.momentum.values,
    })
    out = out.astype(str)
    return out.replace({"nan": "", "None": ""})


def merge_report(path: str, new: pd.DataFrame, keep_days: int) -> pd.DataFrame:
    if os.path.exists(path):
        old = pd.read_csv(path, dtype=str, keep_default_na=False)
        if "created_on" not in old.columns:
            old["created_on"] = old["date"] + " " + old["15minute"] + ":00"
        okey = old["date"] + "|" + old["15minute"]
        nkey = new["date"] + "|" + new["15minute"]
        first_seen = dict(zip(okey, old["created_on"]))
        new = new.copy()
        new["created_on"] = [first_seen.get(k, c) for k, c in zip(nkey, new["created_on"])]
        _na = ("NA", "", "nan")
        for col in ("is_matched", "momentum", "price_next15"):
            if col not in new.columns or col not in old.columns:
                continue
            old_vals = dict(zip(okey, old[col]))
            new[col] = [ov if (str(nv) in _na and ov is not None and str(ov) not in _na) else nv
                        for nv, ov in ((nv, old_vals.get(k)) for k, nv in zip(nkey, new[col]))]
        old = old[~okey.isin(set(nkey))]
        merged = pd.concat([old, new], ignore_index=True)[list(new.columns)]
    else:
        merged = new.copy()
    dt = pd.to_datetime(merged["date"] + " " + merged["15minute"],
                        format="%m/%d/%Y %H:%M")
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=keep_days)
    keep = dt >= cutoff
    merged = merged[keep].iloc[dt[keep].argsort()].reset_index(drop=True)
    return merged


def build_hourly(det: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame({
        "hour":       det["hour"].astype(int),
        "abs_move":   det["best_move"].astype(str).str.replace("+", "", regex=False)
                                      .astype(float).abs(),
        "direction":  det["direction"].astype(str),
        "is_matched": det["is_matched"].astype(str).str.upper(),
        "momentum":   det["momentum"].astype(str).str.upper(),
    })
    agg = d.groupby("hour").agg(
        samples        =("abs_move", "size"),
        longs          =("direction", lambda s: int((s == "LONG").sum())),
        shorts         =("direction", lambda s: int((s == "SHORT").sum())),
        avg_abs_move   =("abs_move", "mean"),
        median_abs_move=("abs_move", "median"),
        max_abs_move   =("abs_move", "max"),
        matched        =("is_matched", lambda s: int((s == "TRUE").sum())),
        resolved       =("is_matched", lambda s: int(s.isin(["TRUE", "FALSE"]).sum())),
        mom_true       =("momentum", lambda s: int((s == "TRUE").sum())),
        mom_n          =("momentum", lambda s: int((s != "NA").sum())),
    ).round(4)
    agg["long_pct"]     = (agg.longs / agg.samples * 100).round(1)
    agg["match_pct"]    = (agg.matched / agg.resolved.clip(lower=1) * 100).round(1)
    agg["momentum_pct"] = (agg.mom_true / agg.mom_n.clip(lower=1) * 100).round(1)
    return agg


def main():
    ap = argparse.ArgumentParser(description="commodity 15-min quarter-hour breakout report")
    ap.add_argument("--days", type=int, default=5,
                    help="lookback days (max 7 for 1m Yahoo Finance data)")
    ap.add_argument("--hours", type=float, default=None,
                    help="lookback hours (overrides --days for short refreshes)")
    ap.add_argument("--tz", default="America/Chicago", help="report timezone")
    ap.add_argument("--keep-days", type=int, default=30,
                    help="retention window for the merged report CSV")
    ap.add_argument("--symbols", default=None,
                    help="comma-separated keys to run (default: all). e.g. gold15,silver15")
    args = ap.parse_args()

    targets = COMMODITIES
    if args.symbols:
        keys = [k.strip() for k in args.symbols.split(",")]
        targets = {k: v for k, v in COMMODITIES.items() if k in keys}
    if not targets:
        print("[commodity15] no valid symbols — aborting")
        sys.exit(1)

    days = min(args.days, 7)
    run_stamp = pd.Timestamp.now(tz=args.tz).strftime("%m/%d/%Y %H:%M:%S")

    for key, cfg in targets.items():
        symbol = cfg["ticker"]
        label = cfg["label"]
        print(f"\n{'='*60}")
        print(f"[commodity15] {label} ({symbol}) — {key}")
        print(f"{'='*60}")

        df = fetch_1m_candles(symbol, days)
        if df.empty:
            continue

        if args.hours is not None:
            cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=args.hours, minutes=20)
            df = df[df["datetime"] >= cutoff].reset_index(drop=True)
            print(f"[commodity15] trimmed to last {args.hours}h+20m: {len(df)} candles")

        rep = build_report(df, args.tz)
        if rep.empty:
            print(f"[commodity15] {key}: no complete marks — skipped")
            continue

        out = build_detail(rep, run_stamp)
        report_path = os.path.join(_HERE, f"{key}_signal_report.csv")
        merged = merge_report(report_path, out, args.keep_days)
        merged.to_csv(report_path, index=False)

        hourly = build_hourly(merged)
        hourly.to_csv(os.path.join(_HERE, f"{key}_signal_hourly.csv"))

        resolved = merged.is_matched.astype(str).str.upper().isin(["TRUE", "FALSE"])
        match_pct = ((merged.is_matched.astype(str).str.upper() == "TRUE").sum()
                     / max(1, resolved.sum()) * 100)
        mom = merged.momentum.astype(str).str.upper()
        mom_n = (mom != "NA").sum()
        mom_pct = (mom == "TRUE").sum() / max(1, mom_n) * 100

        print(f"[commodity15] {key}: upserted {len(out)} rows, "
              f"file now {len(merged)} rows, match {match_pct:.1f}%, momentum {mom_pct:.1f}%")
        print(f"[commodity15] -> {report_path}")

        top = hourly.sort_values("avg_abs_move", ascending=False).head(5)
        print(f"\nTop 5 hours by avg |best_move| ({args.tz}):")
        print(top[["samples", "longs", "shorts", "avg_abs_move",
                   "match_pct", "momentum_pct"]].to_string())


if __name__ == "__main__":
    main()
