"""engine_common.py — the shared multi-engine core behind every *_research worker.

All twelve equity research folders hunt the same 0.30% symmetric TP/SL; the
folders differ only in ticker + their hand-picked A_BOOK. This module is the
single copy of the live-scan machinery — each worker just calls:

    engine_common.run_worker(HERE, "spy", C, data, features, signals, A_BOOK)

Two engine dimensions per ticker:

  * HORIZON — TP/SL must resolve within 30m / 1h / 2h / 4h (same entry
    windows, same TP-before-14:35-CST truncation). 2/3/4 horizons agreeing on
    the same moment grades the ledger row HOT / SUPER HOT / SUPER++ HOT.
  * TIMEFRAME (candle size) — the SAME playbook rules run on 5m, 15m and 30m
    candles resampled from the one 5m feed (indicator windows scale with the
    bar, standard multi-timeframe practice); `tf` column per row, `tfs` union
    on the ledger.

Race targets come from each folder's config (TP_PCT/SL_PCT — ±0.25% for the
ETF book, ±0.40% for single stocks). EVERY (timeframe, horizon) pair is
re-scored daily at those targets against the research bar cache
(results/engine_scores.json; the fingerprint covers targets + grid, so
changing either re-scores everything): a config is live on a pair only while
it clears the research floor there (tp-before-sl >= 85%, evidence floor
sqrt-scaled by candle size); > 95% with >= 4 decided classifies it A.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time as _time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HORIZON_MIN = {"30m": 30, "1h": 60, "2h": 120, "4h": 240}   # tag -> minutes
TIMEFRAMES = {"5m": 5, "15m": 15, "30m": 30}                # tag -> candle minutes
BASE_TF, BASE_ENGINE = "5m", "4h"    # legacy signal-id anchor (dedup continuity)

# per-pair research floor (mirrors iterate.py's ensemble seed bar) + the
# A-book rule the workers already apply on the researched pair. The QUALITY
# floor (tp-before-sl %) is identical everywhere; the EVIDENCE floor scales
# with candle size — a 30m frame has 6x fewer bars than 5m over the same 60
# sessions, so demanding the same absolute trade count would starve the
# higher-timeframe engines (sqrt scaling, hard minimums below).
MIN_TPSL = 81.0               # tp-before-sl % a config needs to stay live
MIN_TRADES = 6                # backtest entries needed at a 5m pair
MIN_DECIDED = 3               # wins+stops needed (all-scratch stats are noise)
A_TPSL = 95.0                 # tp-before-sl > this = A-book on that pair
A_MIN_DECIDED = 4             # scored pairs also need this many decided for A


def _floors(tf: str) -> tuple[int, int]:
    import math
    r = TIMEFRAMES[tf] // TIMEFRAMES[BASE_TF]          # 1, 3, 6
    return (max(3, math.ceil(MIN_TRADES / math.sqrt(r))),
            max(2, math.ceil(MIN_DECIDED / math.sqrt(r))) if r > 1 else MIN_DECIDED)

CSV_COLS = ["logged_at_cst", "book", "engine", "tf", "signal", "direction",
            "confluence", "window", "noise_k", "vol_mult", "acc_strict_pct",
            "acc_tp_before_sl_pct", "bt_trades", "bar_time_cst",
            "signal_price", "entry_ref", "target_price", "stop_price",
            "stop_deadline_cst", "target_deadline_cst", "vwap", "y_poc",
            "pivot", "atr", "volume", "vol_vs_med20"]

_LABEL = re.compile(r"^(LONG|SHORT):(.+?)\|nk([\d.]+)\|vm([\d.]+)\|(\w+)$")


def cfg_label(cfg: dict) -> str:
    return f'{cfg["direction"]}:{"+".join(cfg["combo"])}|nk{cfg["nk"]}|vm{cfg["vm"]}|{cfg["window"]}'


def load_b_book(ensemble_csv: Path) -> list[dict]:
    if not ensemble_csv.exists():
        return []
    try:
        _df = pd.read_csv(ensemble_csv)
    except Exception:
        return []            # empty / malformed ensemble -> no B-book
    out = []
    for _, r in _df.iterrows():
        m = _LABEL.match(str(r["config"]))
        if not m:
            continue
        out.append({"book": "B", "direction": m.group(1),
                    "combo": m.group(2).split("+"),
                    "window": m.group(5), "nk": float(m.group(3)), "vm": float(m.group(4)),
                    "acc_strict": float(r.get("win_rate", 0)),
                    "acc_tpsl": float(r.get("tp_before_sl", 0)),
                    "bt_trades": int(r.get("trades", 0))})
    return out


def fetch_bars(C, tz) -> pd.DataFrame:
    import yfinance as yf
    raw = yf.download(C.TICKER, interval="5m", period="5d", prepost=True,
                      progress=False, auto_adjust=False)
    if raw is None or raw.empty:
        raise RuntimeError("no data from yfinance")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.index = raw.index.tz_convert(C.TZ)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].dropna()
    # drop the still-forming candle
    if len(df) and df.index[-1] + pd.Timedelta(minutes=5) > pd.Timestamp.now(tz=tz):
        df = df.iloc[:-1]
    return df


def resample_bars(bars: pd.DataFrame, minutes: int, tz) -> pd.DataFrame:
    """5m -> 15m/30m candles on clock bins (08:30 CST open is a boundary of
    both). Only fully-elapsed candles are kept, so live scans never act on a
    half-built bar."""
    if minutes == TIMEFRAMES[BASE_TF]:
        return bars
    r = bars.resample(f"{minutes}min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min",
         "Close": "last", "Volume": "sum"}).dropna(subset=["Open"])
    now = pd.Timestamp.now(tz=tz)
    return r[r.index + pd.Timedelta(minutes=minutes) <= now]


def jload(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


# ── per-pair outcome sim (backtest.py's precompute_outcomes, parametrized) ────
def _outcomes(d: pd.DataFrame, direction: str, tp_bars: int, sl_bars: int,
              tp_pct: float, sl_pct: float, deadline) -> pd.DataFrame:
    o = d["Open"].to_numpy(float)
    h = d["High"].to_numpy(float)
    l = d["Low"].to_numpy(float)
    dates = d["date"].to_numpy()
    times = d.index
    n = len(d)
    sgn = 1.0 if direction == "LONG" else -1.0

    result = np.full(n, "", dtype=object)

    for i in range(n - 1):
        e = i + 1
        if dates[e] != dates[i] or not (times[e].time() < deadline):
            continue
        entry = o[e]
        if not np.isfinite(entry) or entry <= 0:
            continue
        tp = entry * (1 + sgn * tp_pct / 100)
        sl = entry * (1 - sgn * sl_pct / 100)
        res = "scratch"
        last_j = e - 1
        for j in range(e, min(e + tp_bars, n)):
            if dates[j] != dates[e] or not (times[j].time() < deadline):
                break
            last_j = j
            k = j - e + 1
            hit_tp = h[j] >= tp if sgn > 0 else l[j] <= tp
            hit_sl = (l[j] <= sl if sgn > 0 else h[j] >= sl) and k <= sl_bars
            if hit_sl:                    # same-bar TP+SL counts as a stop
                res = "stop"
                break
            if hit_tp:
                res = "target"
                break
        if res == "scratch" and last_j < e:
            continue
        result[i] = res

    return pd.DataFrame({"result": result}, index=d.index)


def _frame(C, bars_5m, tf, tz, features, signals):
    """features + blocks + window masks for one timeframe."""
    d = features.build(resample_bars(bars_5m, TIMEFRAMES[tf], tz))
    blk = signals.blocks(d)
    tod = pd.Series([x.time() for x in d.index], index=d.index)
    win_masks = {name: ((tod >= a) & (tod < b)).fillna(False)
                 for name, (a, b) in C.WINDOWS.items()}
    return d, blk, win_masks


def score_pairs(here: Path, C, data, features, signals, playbook: list[dict], log) -> dict:
    """Per-config accuracy at every (timeframe, horizon) pair except the
    researched (5m, 4h) over the research bar cache. Cached one day in
    results/engine_scores.json (keyed to the playbook)."""
    scores_path = here / "results" / "engine_scores.json"
    tz = ZoneInfo(C.TZ)
    # fingerprint covers the race targets and horizon grid too, so changing
    # TP/SL percentages or the engine set auto-invalidates every cache
    fp = hashlib.md5(json.dumps({
        "labels": sorted(cfg_label(c) for c in playbook),
        "tp": C.TP_PCT, "sl": C.SL_PCT,
        "horizons": sorted(HORIZON_MIN), "tfs": sorted(TIMEFRAMES),
    }).encode()).hexdigest()
    today = f"{datetime.now(tz):%Y-%m-%d}"
    cached = jload(scores_path, None)
    if (cached and cached.get("v") == 4 and cached.get("fingerprint") == fp
            and cached.get("scored_on") == today):
        return cached.get("scores", {})
    try:
        bars = data.load_bars()
        deadline = getattr(C, "TP_DEADLINE", C.RTH_CLOSE)
        scores: dict[str, dict] = {}
        for tf, tf_min in TIMEFRAMES.items():
            d, blk, win_masks = _frame(C, bars, tf, tz, features, signals)
            gates: dict[tuple, pd.Series] = {}
            outs: dict[tuple, pd.DataFrame] = {}
            for cfg in playbook:
                key_g = (cfg["nk"], cfg["vm"])
                if key_g not in gates:
                    gates[key_g] = signals.noise_gate(d, *key_g)
                m = gates[key_g] & win_masks[cfg["window"]]
                for b in cfg["combo"]:
                    m &= blk[cfg["direction"]][b]
                for tag, h_min in HORIZON_MIN.items():
                    nb = max(1, h_min // tf_min)
                    ko = (cfg["direction"], nb)
                    if ko not in outs:
                        outs[ko] = _outcomes(d, cfg["direction"], nb, nb,
                                             C.TP_PCT, C.SL_PCT, deadline)
                    sel = outs[ko][m.to_numpy() & (outs[ko]["result"] != "").to_numpy()]
                    n = len(sel)
                    wins = int((sel["result"] == "target").sum())
                    stops = int((sel["result"] == "stop").sum())
                    scores.setdefault(cfg_label(cfg), {}).setdefault(tf, {})[tag] = {
                        "trades": n, "wins": wins, "stops": stops,
                        "acc_strict": round(wins / n * 100, 1) if n else 0.0,
                        "acc_tpsl": round(wins / max(wins + stops, 1) * 100, 1),
                    }
        scores_path.parent.mkdir(exist_ok=True)
        scores_path.write_text(json.dumps({
            "v": 4, "scored_on": today, "fingerprint": fp,
            "bars_end": f"{bars.index[-1]}", "scores": scores}, indent=1),
            encoding="utf-8")
        log(f"engine scores refreshed: {len(playbook)} configs x "
            f"{len(TIMEFRAMES)} timeframes x {len(HORIZON_MIN)} horizons "
            f"(results/{scores_path.name})")
        return scores
    except Exception as e:
        log(f"engine scoring failed ({type(e).__name__}: {e}) — "
            + ("using stale scores" if cached else f"running {BASE_TF}/{BASE_ENGINE} only"))
        return (cached or {}).get("scores", {})


def build_engine_playbooks(playbook: list[dict], scores: dict) -> dict[tuple, list[dict]]:
    """EVERY pair is scored at the configured race targets (TP_PCT/SL_PCT) —
    a config stays live on a pair only while it clears the research floor
    there, re-classed A/B from its recomputed accuracy. (The hardcoded A_BOOK
    accs are only the candidate pool's provenance; since the race targets are
    per-category now, nothing inherits the old ±0.30% numbers.)"""
    books: dict[tuple, list[dict]] = {}
    for tf in TIMEFRAMES:
        for tag in HORIZON_MIN:
            min_tr, min_dec = _floors(tf)
            pb = []
            for cfg in playbook:
                st = ((scores.get(cfg_label(cfg)) or {}).get(tf) or {}).get(tag)
                if not st:
                    continue
                dec = st["wins"] + st["stops"]
                if st["trades"] < min_tr or dec < min_dec or st["acc_tpsl"] < MIN_TPSL:
                    continue
                book = "A" if (st["acc_tpsl"] > A_TPSL and dec >= A_MIN_DECIDED) else "B"
                pb.append({**cfg, "acc_strict": st["acc_strict"], "acc_tpsl": st["acc_tpsl"],
                           "bt_trades": st["trades"], "book": book})
            books[(tf, tag)] = pb
    return books


def migrate_csv(csv_path: Path) -> None:
    """One-time: rewrite a pre-engine/pre-tf worker CSV to the new header;
    rows predating a column carry the researched defaults (engine 4h, tf 5m)."""
    if not csv_path.exists():
        return
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            rdr = csv.DictReader(f)
            if rdr.fieldnames == CSV_COLS:
                return
            rows = list(rdr)
    except Exception:
        return
    for r in rows:
        r.setdefault("engine", BASE_ENGINE)
        r.setdefault("tf", BASE_TF)
        r.pop(None, None)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(rows)


def emit(csv_path: Path, row: dict) -> None:
    new = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        if new:
            w.writeheader()
        w.writerow(row)


def scan(engine_books: dict[tuple, list[dict]], state: dict, backfill: bool, *,
         C, features, signals, csv_path: Path, state_path: Path, tz, log) -> int:
    bars_5m = fetch_bars(C, tz)
    today = datetime.now(tz).date()
    emitted = set(state.get("emitted", []))

    def _dl(ts):
        """Same-day TP deadline (desk rule: TP before 14:35 CST)."""
        dd = getattr(C, "TP_DEADLINE", C.RTH_CLOSE)
        return ts.replace(hour=dd.hour, minute=dd.minute, second=0)

    n_new = 0
    for tf, tf_min in TIMEFRAMES.items():
        d, blk, win_masks = _frame(C, bars_5m, tf, tz, features, signals)
        if not len(d):
            continue
        is_today = pd.Series([x.date() == today for x in d.index], index=d.index)
        gates: dict[tuple, pd.Series] = {}
        for tag, h_min in HORIZON_MIN.items():
            playbook = engine_books.get((tf, tag), [])
            nb = max(1, h_min // tf_min)
            # collect every (config, bar) hit first, then collapse overlapping
            # playbook variants: ONE row per (bar, direction, book) per pair,
            # best-accuracy config named, `confluence` = configs on that bar
            hits: dict[tuple, list[dict]] = {}
            for cfg in playbook:
                key_g = (cfg["nk"], cfg["vm"])
                if key_g not in gates:
                    gates[key_g] = signals.noise_gate(d, *key_g)
                m = gates[key_g] & win_masks[cfg["window"]] & is_today
                for b in cfg["combo"]:
                    m &= blk[cfg["direction"]][b]
                for ts in d.index[m]:
                    if not backfill and ts != d.index[-1]:
                        continue                   # live mode: only the newest bar
                    hits.setdefault((ts, cfg["direction"], cfg["book"]), []).append(cfg)

            for (ts, direction, book), cfgs in sorted(hits.items()):
                # the researched pair keeps the pre-engine id formats so
                # already-logged signals never re-emit across upgrades
                if tf == BASE_TF:
                    sig_id = (f"{ts:%Y-%m-%d %H:%M}|{book}|{direction}" if tag == BASE_ENGINE
                              else f"{ts:%Y-%m-%d %H:%M}|{tag}|{book}|{direction}")
                else:
                    sig_id = f"{ts:%Y-%m-%d %H:%M}|{tf}|{tag}|{book}|{direction}"
                if sig_id in emitted:
                    continue
                emitted.add(sig_id)
                cfg = max(cfgs, key=lambda x: (x["acc_tpsl"], x["acc_strict"], x["bt_trades"]))
                r = d.loc[ts]
                price = float(r["Close"])
                sgn = 1 if direction == "LONG" else -1
                row = {
                    "logged_at_cst": f"{datetime.now(tz):%Y-%m-%d %H:%M:%S}",
                    "book": book,
                    "engine": tag,
                    "tf": tf,
                    "signal": "+".join(cfg["combo"]),
                    "direction": direction,
                    "confluence": len(cfgs),
                    "window": cfg["window"],
                    "noise_k": cfg["nk"], "vol_mult": cfg["vm"],
                    "acc_strict_pct": cfg["acc_strict"],
                    "acc_tp_before_sl_pct": cfg["acc_tpsl"],
                    "bt_trades": cfg["bt_trades"],
                    "bar_time_cst": f"{ts:%Y-%m-%d %H:%M}",
                    "signal_price": round(price, 2),
                    "entry_ref": round(price, 2),   # enter next bar open ≈ this close
                    "target_price": round(price * (1 + sgn * C.TP_PCT / 100), 2),
                    "stop_price": round(price * (1 - sgn * C.SL_PCT / 100), 2),
                    "stop_deadline_cst": f"{min(ts + pd.Timedelta(minutes=tf_min * (nb + 1)), _dl(ts)):%H:%M}",
                    "target_deadline_cst": f"{min(ts + pd.Timedelta(minutes=tf_min * (nb + 1)), _dl(ts)):%H:%M}",
                    "vwap": round(float(r["vwap"]), 2) if pd.notna(r["vwap"]) else "",
                    "y_poc": round(float(r["y_poc"]), 2) if pd.notna(r["y_poc"]) else "",
                    "pivot": round(float(r["pivot"]), 2) if pd.notna(r["pivot"]) else "",
                    "atr": round(float(r["atr"]), 3) if pd.notna(r["atr"]) else "",
                    "volume": int(r["Volume"]),
                    "vol_vs_med20": round(float(r["Volume"] / r["vol_med20"]), 2)
                                     if pd.notna(r["vol_med20"]) and r["vol_med20"] else "",
                }
                emit(csv_path, row)
                n_new += 1
                log(f"SIGNAL [{book}-book {tf}/{tag} x{len(cfgs)}] {direction} {'+'.join(cfg['combo'])} "
                    f"@ {ts:%H:%M} px {row['signal_price']} -> tgt {row['target_price']} "
                    f"(acc {cfg['acc_tpsl']:.0f}% tp-b-sl / {cfg['acc_strict']:.0f}% strict)")

    state["emitted"] = sorted(emitted)[-6000:]
    state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    return n_new


def run_worker(here: Path, tag_id: str, C, data, features, signals,
               a_book: list[dict]) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    tz = ZoneInfo(C.TZ)
    csv_path = here / f"{tag_id}_intraday_signals.csv"
    state_path = here / f"{tag_id}_bot_state.json"

    def log(m):
        print(f"[{tag_id}bot {datetime.now(tz):%H:%M:%S}] {m}", flush=True)

    ap = argparse.ArgumentParser(description=f"live {C.TICKER} Super-Signal watcher")
    ap.add_argument("--poll", type=int, default=60)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--backfill-today", action="store_true",
                    help="emit every signal today's completed bars fired (testing/catch-up)")
    a = ap.parse_args()

    playbook = [dict(c) for c in a_book] + load_b_book(here / "results" / "ensemble.csv")
    # classification rule: A-book = TP-before-SL > 95%, everything else B-book.
    for _cfg in playbook:
        _cfg["book"] = "A" if _cfg["acc_tpsl"] > A_TPSL else "B"
    scores = score_pairs(here, C, data, features, signals, playbook, log)
    engine_books = build_engine_playbooks(playbook, scores)
    sizes = " · ".join(
        f'{tf}:{"/".join(str(len(engine_books[(tf, tag)])) for tag in HORIZON_MIN)}'
        for tf in TIMEFRAMES)
    tz_abbr = datetime.now(tz).strftime("%Z") or C.TZ
    log(f"engines [configs per {'/'.join(HORIZON_MIN)}] {sizes} "
        f"(A rule >{A_TPSL:.0f}%, floor {MIN_TPSL:.0f}% tp-b-sl) "
        f"| window {C.ENTRY_OPEN:%H:%M}-{C.ENTRY_CLOSE:%H:%M} {tz_abbr} | csv={csv_path.name}")
    migrate_csv(csv_path)
    state = jload(state_path, {})

    kw = dict(C=C, features=features, signals=signals, csv_path=csv_path,
              state_path=state_path, tz=tz, log=log)
    if a.backfill_today or a.once:
        n = scan(engine_books, state, backfill=a.backfill_today, **kw)
        log(f"done — {n} new signal(s)")
        return

    while True:
        now = datetime.now(tz)
        if C.ENTRY_OPEN <= now.time() < C.ENTRY_CLOSE and now.weekday() < 5:
            try:
                scan(engine_books, state, backfill=False, **kw)
            except Exception as e:
                log(f"scan error: {type(e).__name__}: {e}")
        _time.sleep(a.poll)
