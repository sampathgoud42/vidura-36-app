"""
btc15_signal.py — btc-15 quarter-hour breakout report.

Fetches 1-minute BTC-USD candles from Coinbase Advanced Trade (reuses
cb_btc_signal's JWT helper; falls back to the public market-data endpoint
when no credentials are set) for the past N days (default 30), then for
every quarter-hour mark T (:00 / :15 / :30 / :45) measures:

    minus window = [T-2m, T)   ->  btc_15minus2_min / btc_15minus2_max
    plus  window = [T, T+5m)   ->  btc15plus5_min   / btc15plus5_max

    up_move   = btc15plus5_max - btc_15minus2_min    (LONG  potential)
    down_move = btc15plus5_min - btc_15minus2_max    (SHORT potential, < 0)

    best_move / direction = larger-magnitude candidate:
        up_move >= |down_move|  ->  LONG,  best_move = +up_move
        otherwise               ->  SHORT, best_move =  down_move

Usage:
    python btc15_signal.py [--days 30] [--tz America/Chicago] [--product BTC-USD]

Outputs (written next to this script):
    btc15_signal_report.csv  — date, hour, 15minute, btc_15minus2_min,
                               btc_15minus2_max, btc15plus5_min,
                               btc15plus5_max, best_move, direction
    btc15_signal_hourly.csv  — aggregate stats per hour-of-day (0..23)
"""

import argparse
import asyncio
import os
import sys
import time

import aiohttp
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from cb_btc_signal import API_HOST, _build_cb_jwt  # noqa: E402  (existing coinbase module)

GRANULARITY   = "ONE_MINUTE"
CHUNK_CANDLES = 300          # Coinbase caps 350 candles/request — stay under
MAX_RETRIES   = 5
CONCURRENCY   = 3            # public endpoint allows ~10 req/s; stay polite


async def _fetch_chunk(session, sem, product_id, start, end):
    """Fetch one <=300-candle window; returns the raw candle dict list."""
    auth_path  = f"/api/v3/brokerage/products/{product_id}/candles"
    public_url = f"https://{API_HOST}/api/v3/brokerage/market/products/{product_id}/candles"
    params = {"start": str(start), "end": str(end), "granularity": GRANULARITY}
    for attempt in range(1, MAX_RETRIES + 1):
        token = _build_cb_jwt("GET", auth_path)      # fresh JWT each try (120s expiry)
        if token:
            url, headers = f"https://{API_HOST}{auth_path}", {"Authorization": f"Bearer {token}"}
        else:
            url, headers = public_url, {}
        try:
            async with sem:
                async with session.get(url, params=params, headers=headers) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("candles", [])
                    body = await r.text()
                    print(f"[btc15_signal] chunk {start}-{end} HTTP {r.status} "
                          f"(try {attempt}): {body[:120]}")
        except Exception as e:
            print(f"[btc15_signal] chunk {start}-{end} error (try {attempt}): {e}")
        await asyncio.sleep(2.5 * attempt)
    return []


async def fetch_1m_candles(product_id: str, lookback_min: int) -> pd.DataFrame:
    """Paginated 1-minute candle download covering the past ``lookback_min`` minutes."""
    end_ts   = int(time.time()) // 60 * 60
    start_ts = end_ts - lookback_min * 60
    step     = CHUNK_CANDLES * 60
    ranges   = [(s, min(s + step - 60, end_ts)) for s in range(start_ts, end_ts, step)]
    print(f"[btc15_signal] fetching {lookback_min}m of 1m candles "
          f"({len(ranges)} request(s) of <= {CHUNK_CANDLES} candles)...")

    sem     = asyncio.Semaphore(CONCURRENCY)
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        chunks = await asyncio.gather(
            *[_fetch_chunk(session, sem, product_id, s, e) for s, e in ranges])

    rows = [c for chunk in chunks for c in chunk]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["start"] = df["start"].astype(int)
    df = df.drop_duplicates("start").sort_values("start").reset_index(drop=True)

    expected = (end_ts - start_ts) // 60
    print(f"[btc15_signal] got {len(df)} candles "
          f"({len(df) / expected * 100:.1f}% of {expected} expected minutes)")
    return df


def build_report(df: pd.DataFrame, tz: str, minus_w: int = 2, plus_w: int = 5) -> pd.DataFrame:
    """One row per quarter-hour mark with full minus(minus_w) + plus(plus_w) windows."""
    local = pd.to_datetime(df["start"], unit="s", utc=True).dt.tz_convert(tz)
    offset  = local.dt.minute % 15
    floor15 = local.dt.floor("15min")

    # offsets [15-minus_w, 14] = the minus_w minutes BEFORE the next mark;
    # offsets [0, plus_w-1]    = the plus_w minutes AFTER a mark
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
        print(f"[btc15_signal] ±{minus_w}m: skipped {len(rep) - len(full)} marks with "
              f"incomplete windows (candle gaps / data edges)")

    full["up_move"]   = full.plus_max - full.minus_min
    full["down_move"] = full.plus_min - full.minus_max
    long_wins = full.up_move >= (full.minus_max - full.plus_min)   # up >= |down|
    full["direction"] = np.where(long_wins, "LONG", "SHORT")
    full["best_move"] = np.where(long_wins, full.up_move, full.down_move)

    # close AT each mark = close of the 1m candle that ENDS there (start = T-1m),
    # i.e. the traded price at HH:MM:00 sharp; next15 = same read at T+15m.
    close_by_end = pd.Series(df["close"].values, index=local + pd.Timedelta(minutes=1))
    close_by_end = close_by_end[~close_by_end.index.duplicated(keep="last")]
    full["btc_current15"] = full.index.map(close_by_end)
    full["btc_next15"]    = (full.index + pd.Timedelta(minutes=15)).map(close_by_end)
    n_before = len(full)
    full = full.dropna(subset=["btc_current15"])      # close@T is mandatory
    if n_before - len(full):
        print(f"[btc15_signal] dropped {n_before - len(full)} marks lacking a close at T")
    full = full.sort_index()

    # the newest mark(s) have no close@T+15 yet — insert them as PENDING
    # (is_matched/momentum = NA, btc_next15 empty); they resolve on a later run
    resolved = full.btc_next15.notna()
    if (~resolved).sum():
        print(f"[btc15_signal] {(~resolved).sum()} pending mark(s) awaiting close@T+15m")
    up = resolved & (full.btc_next15 > full.btc_current15)
    dn = resolved & (full.btc_next15 < full.btc_current15)
    full["is_matched"] = np.where(~resolved, "NA",
                         np.where(((full.direction == "LONG") & up)
                                  | ((full.direction == "SHORT") & dn), "TRUE", "FALSE"))

    # momentum: does THIS window's drift (next15 vs current15) confirm the
    # PREVIOUS record's direction?  Previous record must be exactly one
    # quarter-hour earlier, otherwise NA (first row / gaps / pending).
    prev_dir = full["direction"].shift(1)
    adjacent = full.index.to_series().diff() == pd.Timedelta(minutes=15)
    mom_true = ((prev_dir == "LONG") & up) | ((prev_dir == "SHORT") & dn)
    full["momentum"] = np.where(~adjacent | prev_dir.isna() | ~resolved, "NA",
                                np.where(mom_true, "TRUE", "FALSE"))
    return full


def build_pre3(df: pd.DataFrame, tz: str) -> pd.DataFrame:
    """Per-mark report from the LAST 3 one-minute candles BEFORE the mark T.

    minusK = the candle covering [T-Km, T-(K-1)m).  best_move is the largest
    chronological TWO-candle move across pairs (m3,m2), (m3,m1), (m2,m1):
        up   = max(later_max - earlier_min)      (LONG, +)
        down = min(later_min - earlier_max)      (SHORT, -)
    the larger magnitude wins.  All three candles close AT T, so this signal
    is fully decision-time at the mark itself (no post-mark data needed).
    btc_current15 = close of the T-1 candle (price at T, same convention).
    """
    local = pd.to_datetime(df["start"], unit="s", utc=True).dt.tz_convert(tz)
    offset  = local.dt.minute % 15
    mark_of = local.dt.floor("15min") + pd.Timedelta(minutes=15)
    per_k = {}
    for k, off in ((3, 12), (2, 13), (1, 14)):
        sel = df.loc[(offset == off).values, ["low", "high", "close"]].copy()
        sel.index = mark_of[(offset == off).values]
        per_k[k] = sel[~sel.index.duplicated(keep="last")]
    idx = per_k[3].index.intersection(per_k[2].index).intersection(per_k[1].index)
    if len(idx) == 0:
        return pd.DataFrame()
    out = pd.DataFrame(index=idx.sort_values())
    for k in (3, 2, 1):
        out[f"minus{k}_min"] = per_k[k].reindex(out.index)["low"]
        out[f"minus{k}_max"] = per_k[k].reindex(out.index)["high"]
    pairs = [(3, 2), (3, 1), (2, 1)]                    # (earlier, later), chronological
    up = pd.concat([out[f"minus{l}_max"] - out[f"minus{e}_min"] for e, l in pairs], axis=1).max(axis=1)
    dn = pd.concat([out[f"minus{l}_min"] - out[f"minus{e}_max"] for e, l in pairs], axis=1).min(axis=1)
    long_wins = up >= -dn
    out["best_move"] = np.where(long_wins, up, dn)
    out["direction"] = np.where(long_wins, "LONG", "SHORT")
    out["btc_current15"] = per_k[1].reindex(out.index)["close"]
    # outcome: close@T+15 vs close@T, same conventions as the main report
    close_by_end = pd.Series(df["close"].values, index=local + pd.Timedelta(minutes=1))
    close_by_end = close_by_end[~close_by_end.index.duplicated(keep="last")]
    out["btc_next15"] = (out.index + pd.Timedelta(minutes=15)).map(close_by_end)
    resolved = out.btc_next15.notna()
    o_up = resolved & (out.btc_next15 > out.btc_current15)
    o_dn = resolved & (out.btc_next15 < out.btc_current15)
    out["is_matched"] = np.where(~resolved, "NA",
                        np.where(((out.direction == "LONG") & o_up)
                                 | ((out.direction == "SHORT") & o_dn), "TRUE", "FALSE"))
    return out


def build_pre3_detail(rep: pd.DataFrame, created_stamp: str) -> pd.DataFrame:
    out = pd.DataFrame({
        "date":          rep.index.strftime("%m/%d/%Y"),
        "created_on":    created_stamp,
        "hour":          rep.index.hour,
        "15minute":      rep.index.strftime("%H:%M"),
        "minus3_min":    rep.minus3_min.round(2).values,
        "minus3_max":    rep.minus3_max.round(2).values,
        "minus2_min":    rep.minus2_min.round(2).values,
        "minus2_max":    rep.minus2_max.round(2).values,
        "minus1_min":    rep.minus1_min.round(2).values,
        "minus1_max":    rep.minus1_max.round(2).values,
        "best_move":     [f"{v:+.0f}" for v in rep.best_move],
        "direction":     rep.direction.values,
        "btc_current15": rep.btc_current15.round(2).values,
        "btc_next15":    rep.btc_next15.round(2).values,
        "is_matched":    rep.is_matched.values,
    })
    return out.astype(str).replace({"nan": "", "None": ""})


def build_detail(rep: pd.DataFrame, created_stamp: str) -> pd.DataFrame:
    """Detail CSV rows (all string-typed for stable upsert merging).

    ``created_on`` = when the row was FIRST inserted; merge_report preserves the
    original stamp for rows that already exist, so only brand-new marks carry
    this run's timestamp.
    """
    out = pd.DataFrame({
        "date":          rep.index.strftime("%m/%d/%Y"),
        "created_on":    created_stamp,
        "hour":          rep.index.hour,
        "15minute":      rep.index.strftime("%H:%M"),
        "minus_min":     rep.minus_min.round(2).values,
        "minus_max":     rep.minus_max.round(2).values,
        "plus_min":      rep.plus_min.round(2).values,
        "plus_max":      rep.plus_max.round(2).values,
        "best_move":     [f"{v:+.0f}" for v in rep.best_move],
        "direction":     rep.direction.values,
        "btc_current15": rep.btc_current15.round(2).values,
        "btc_next15":    rep.btc_next15.round(2).values,
        "is_matched":    rep.is_matched.values,
        "momentum":      rep.momentum.values,
    })
    out = out.astype(str)
    return out.replace({"nan": "", "None": ""})           # pending btc_next15 -> blank


def merge_report(path: str, new: pd.DataFrame, keep_days: int) -> pd.DataFrame:
    """UPSERT ``new`` rows into the existing CSV by (date, 15minute).

    A short-lookback refresh (e.g. the bot's 24h run) only replaces/inserts the
    marks it fetched — history outside the window is preserved, then everything
    is chronologically sorted and trimmed to ``keep_days``.
    """
    if os.path.exists(path):
        old = pd.read_csv(path, dtype=str, keep_default_na=False)
        if "created_on" not in old.columns:        # legacy rows: backfill with mark time
            old["created_on"] = old["date"] + " " + old["15minute"] + ":00"
        okey = old["date"] + "|" + old["15minute"]
        nkey = new["date"] + "|" + new["15minute"]
        first_seen = dict(zip(okey, old["created_on"]))
        new = new.copy()
        new["created_on"] = [first_seen.get(k, c) for k, c in zip(nkey, new["created_on"])]
        # a short-window refresh must never DEGRADE already-resolved fields: keep
        # the old value when the new row says NA/blank but the old was resolved
        # (e.g. the fetch window's oldest mark has no in-window prev for momentum).
        _na = ("NA", "", "nan")
        for col in ("is_matched", "momentum", "btc_next15"):
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
    """Hour-of-day aggregate recomputed from the full MERGED detail frame."""
    d = pd.DataFrame({
        "hour":       det["hour"].astype(int),
        "abs_move":   det["best_move"].astype(str).str.replace("+", "", regex=False)
                                      .astype(float).abs(),
        "up_move":    det["plus_max"].astype(float) - det["minus_min"].astype(float),
        "down_move":  det["plus_min"].astype(float) - det["minus_max"].astype(float),
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
        p90_abs_move   =("abs_move", lambda s: s.quantile(0.9)),
        max_abs_move   =("abs_move", "max"),
        avg_up_move    =("up_move", "mean"),
        avg_down_move  =("down_move", "mean"),
        matched        =("is_matched", lambda s: int((s == "TRUE").sum())),
        resolved       =("is_matched", lambda s: int(s.isin(["TRUE", "FALSE"]).sum())),
        mom_true       =("momentum", lambda s: int((s == "TRUE").sum())),
        mom_n          =("momentum", lambda s: int((s != "NA").sum())),
    ).round(1)
    agg["long_pct"]     = (agg.longs / agg.samples * 100).round(1)
    agg["match_pct"]    = (agg.matched / agg.resolved.clip(lower=1) * 100).round(1)
    agg["momentum_pct"] = (agg.mom_true / agg.mom_n.clip(lower=1) * 100).round(1)
    return agg


def _parse_engines(spec: str):
    """'1,2,5:1' -> [('w1', 1, 1, '±1m'), ('w2', 2, 2, '±2m'), ('custom51', 5, 1, '-5/+1m')]"""
    out = []
    for tok in str(spec).split(","):
        tok = tok.strip()
        if not tok:
            continue
        if ":" in tok:
            m, p = (int(x) for x in tok.split(":", 1))
            out.append((f"custom{m}{p}", m, p, f"-{m}/+{p}m"))
        else:
            w = int(tok)
            out.append((f"w{w}", w, w, f"±{w}m"))
    return out


def main():
    ap = argparse.ArgumentParser(description="btc-15 quarter-hour breakout report")
    ap.add_argument("--days", type=int, default=None, help="lookback days (full backfills)")
    ap.add_argument("--hours", type=float, default=None,
                    help="lookback hours (default: 1h; a 20m context pad is added)")
    ap.add_argument("--tz", default="America/Chicago", help="report timezone")
    ap.add_argument("--product", default="BTC-USD")
    ap.add_argument("--engines", default="2",
                    help="comma-separated engines: 'W' = symmetric ±W min; "
                         "'M:P' = asymmetric minus-M/plus-P min (named customMP)")
    ap.add_argument("--keep-days", type=int, default=90,
                    help="retention window for the merged report CSV (default 90)")
    args = ap.parse_args()
    engine_list = _parse_engines(args.engines)

    if args.days is not None and args.hours is None:
        lookback_min = args.days * 1440
    else:
        hours = args.hours if args.hours is not None else 1.0
        lookback_min = int(hours * 60) + 20        # +20m so edge marks keep prev context
    df = asyncio.run(fetch_1m_candles(args.product, lookback_min))
    if df.empty:
        print("[btc15_signal] no candles fetched — aborting")
        sys.exit(1)

    run_stamp = pd.Timestamp.now(tz=args.tz).strftime("%m/%d/%Y %H:%M:%S")
    results = {}
    for key, m, p, lab in engine_list:
        rep = build_report(df, args.tz, minus_w=m, plus_w=p)
        if rep.empty:
            print(f"[btc15_signal] engine {lab} produced no rows — skipped")
            continue
        out = build_detail(rep, run_stamp)
        report_path = os.path.join(_HERE, f"btc15_signal_report_{key}.csv")
        merged = merge_report(report_path, out, args.keep_days)   # UPSERT, not overwrite
        merged.to_csv(report_path, index=False)
        agg = build_hourly(merged)
        agg.to_csv(os.path.join(_HERE, f"btc15_signal_hourly_{key}.csv"))
        resolved = merged.is_matched.astype(str).str.upper().isin(["TRUE", "FALSE"])
        match_pct = ((merged.is_matched.astype(str).str.upper() == "TRUE").sum()
                     / max(1, resolved.sum()) * 100)
        mom = merged.momentum.astype(str).str.upper()
        mom_n = (mom != "NA").sum()
        mom_pct = (mom == "TRUE").sum() / max(1, mom_n) * 100
        results[key] = (match_pct, merged, agg, lab)
        print(f"[btc15_signal] engine {lab} ({key}): upserted {len(out)} rows, "
              f"file now {len(merged)} rows, match {match_pct:.1f}%, momentum {mom_pct:.1f}%")
    if not results:
        print("[btc15_signal] no engine produced rows — aborting")
        sys.exit(1)

    # ---- pre-mark momentum report (last 3 one-minute candles before T) ----
    pre3 = build_pre3(df, args.tz)
    if not pre3.empty:
        p3_out = build_pre3_detail(pre3, run_stamp)
        p3_path = os.path.join(_HERE, "btc15_pre3_report.csv")
        p3_merged = merge_report(p3_path, p3_out, args.keep_days)
        p3_merged.to_csv(p3_path, index=False)
        print(f"[btc15_signal] pre3 report: upserted {len(p3_out)} rows, "
              f"file now {len(p3_merged)} rows -> btc15_pre3_report.csv")

    # best engine (highest overall next-15 match %) also lands in the legacy filenames
    best = max(results, key=lambda k: results[k][0])
    bm, bout, bagg, blab = results[best]
    bout.to_csv(os.path.join(_HERE, "btc15_signal_report.csv"), index=False)
    bagg.to_csv(os.path.join(_HERE, "btc15_signal_hourly.csv"))
    print(f"[btc15_signal] BEST engine {blab} ({bm:.1f}% match) -> btc15_signal_report.csv")

    top = bagg.sort_values("avg_abs_move", ascending=False).head(5)
    print(f"\nTop 5 hours by avg |best_move| ({blab} engine, {args.tz}):")
    print(top[["samples", "longs", "shorts", "avg_abs_move",
               "median_abs_move", "max_abs_move", "match_pct", "momentum_pct"]].to_string())


if __name__ == "__main__":
    main()
