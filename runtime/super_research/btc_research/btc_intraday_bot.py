#!/usr/bin/env python
"""
btc_intraday_bot.py — live BTC Super-Signal watcher (spy bot mirrored).

Watches completed 5-minute BTC-USD candles during the research entry window
(9:00 AM – 2:00 PM CST) for the playbook discovered by research.py/iterate.py:

  * A-book — the hand-picked "never-stopped" precision setups (REPORT.md
    FINAL VERDICT), hardcoded below with their backtest accuracy.
  * B-book — every ensemble composite from results/ensemble.csv (if present),
    parsed dynamically so a re-run of iterate.py refreshes the live playbook.

Every fresh signal appends one fully-detailed row to btc_intraday_signals.csv
(CST timestamps): book, combo, direction, backtest accuracies, signal-bar
price, entry reference, target/stop prices, deadlines, and market context
(VWAP / prior-day POC / pivot / ATR / volume vs median).

Usage:
    python btc_intraday_bot.py                 # live loop, poll 60s
    python btc_intraday_bot.py --poll 120
    python btc_intraday_bot.py --once          # one scan of the latest bar
    python btc_intraday_bot.py --backfill-today  # emit everything today fired
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time as _time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import config as C            # noqa: E402
import features               # noqa: E402
import signals                # noqa: E402

TZ = ZoneInfo(C.TZ)
CSV_PATH = HERE / "btc_intraday_signals.csv"
STATE_PATH = HERE / "btc_bot_state.json"
ENSEMBLE_CSV = HERE / "results" / "ensemble.csv"

CSV_COLS = ["logged_at_cst", "book", "signal", "direction", "confluence",
            "window", "noise_k", "vol_mult", "acc_strict_pct",
            "acc_tp_before_sl_pct", "bt_trades", "bar_time_cst",
            "signal_price", "entry_ref", "target_price", "stop_price",
            "stop_deadline_cst", "target_deadline_cst", "vwap", "y_poc",
            "pivot", "atr", "volume", "vol_vs_med20"]

# ── the playbook ──────────────────────────────────────────────────────────────
# Top precision setups from the 61-session 24×7 backtest (TP 80 / SL 50, entries
# all day). Book label is (re)assigned at load time by the TP-before-SL > 95%
# rule; under the tighter 50-pt stop across the full day NOTHING clears 95%, so
# these all land in the B-book. The edge concentrates in the overnight
# (asia_0_8) window and is two-sided.
A_BOOK = [
    {"book": "A", "direction": "LONG", "combo": ["above_vwap", "above_pivot", "macd_x_up_neg", "strong_close"],
     "window": "asia_0_8", "nk": 1.2, "vm": 1.2,
     "acc_strict": 88.9, "acc_tpsl": 88.9, "bt_trades": 9},
    {"book": "A", "direction": "LONG", "combo": ["above_vwap", "macd_x_up_neg", "hist_turn_up"],
     "window": "full_day", "nk": 0.9, "vm": 0.8,
     "acc_strict": 87.5, "acc_tpsl": 87.5, "bt_trades": 8},
    {"book": "A", "direction": "SHORT", "combo": ["adi_dn", "delta_dump", "macd_x_dn_pos", "hist_turn_dn"],
     "window": "asia_0_8", "nk": 0.9, "vm": 1.2,
     "acc_strict": 85.7, "acc_tpsl": 85.7, "bt_trades": 7},
]

_LABEL = re.compile(r"^(LONG|SHORT):(.+?)\|nk([\d.]+)\|vm([\d.]+)\|(\w+)$")


def load_b_book() -> list[dict]:
    if not ENSEMBLE_CSV.exists():
        return []
    out = []
    for _, r in pd.read_csv(ENSEMBLE_CSV).iterrows():
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


def log(m):
    print(f"[btcbot {datetime.now(TZ):%H:%M:%S}] {m}", flush=True)


def fetch_bars() -> pd.DataFrame:
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
    if len(df) and df.index[-1] + pd.Timedelta(minutes=5) > pd.Timestamp.now(tz=TZ):
        df = df.iloc[:-1]
    return df


def jload(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def emit(row: dict) -> None:
    new = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        if new:
            w.writeheader()
        w.writerow(row)


def scan(playbook: list[dict], state: dict, backfill: bool) -> int:
    bars = fetch_bars()
    d = features.build(bars)
    blk = signals.blocks(d)
    tod = pd.Series([x.time() for x in d.index], index=d.index)
    today = datetime.now(TZ).date()
    is_today = pd.Series([x.date() == today for x in d.index], index=d.index)

    win_masks = {name: ((tod >= a) & (tod < b)).fillna(False)
                 for name, (a, b) in C.WINDOWS.items()}
    gates: dict[tuple, pd.Series] = {}

    emitted = set(state.get("emitted", []))

    # collect every (config, bar) hit first, then collapse overlapping playbook
    # variants: ONE row per (bar, direction, book), best-accuracy config named,
    # `confluence` = how many playbook configs fired on that bar
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
                continue                       # live mode: only the newest bar
            hits.setdefault((ts, cfg["direction"], cfg["book"]), []).append(cfg)

    n_new = 0
    for (ts, direction, book), cfgs in sorted(hits.items()):
        sig_id = f"{ts:%Y-%m-%d %H:%M}|{book}|{direction}"
        if sig_id in emitted:
            continue
        emitted.add(sig_id)
        cfg = max(cfgs, key=lambda x: (x["acc_tpsl"], x["acc_strict"], x["bt_trades"]))
        r = d.loc[ts]
        price = float(r["Close"])
        sgn = 1 if direction == "LONG" else -1
        row = {
            "logged_at_cst": f"{datetime.now(TZ):%Y-%m-%d %H:%M:%S}",
            "book": book,
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
            "stop_deadline_cst": f"{ts + pd.Timedelta(minutes=5 * (C.SL_BARS + 1)):%H:%M}",
            "target_deadline_cst": f"{ts + pd.Timedelta(minutes=5 * (C.TP_BARS + 1)):%H:%M}",
            "vwap": round(float(r["vwap"]), 2) if pd.notna(r["vwap"]) else "",
            "y_poc": round(float(r["y_poc"]), 2) if pd.notna(r["y_poc"]) else "",
            "pivot": round(float(r["pivot"]), 2) if pd.notna(r["pivot"]) else "",
            "atr": round(float(r["atr"]), 3) if pd.notna(r["atr"]) else "",
            "volume": int(r["Volume"]),
            "vol_vs_med20": round(float(r["Volume"] / r["vol_med20"]), 2)
                             if pd.notna(r["vol_med20"]) and r["vol_med20"] else "",
        }
        emit(row)
        n_new += 1
        log(f"SIGNAL [{book}-book x{len(cfgs)}] {direction} {'+'.join(cfg['combo'])} "
            f"@ {ts:%H:%M} px {row['signal_price']} -> tgt {row['target_price']} "
            f"(acc {cfg['acc_tpsl']:.0f}% tp-b-sl / {cfg['acc_strict']:.0f}% strict)")

    state["emitted"] = sorted(emitted)[-500:]
    STATE_PATH.write_text(json.dumps(state, indent=1), encoding="utf-8")
    return n_new


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="live BTC Super-Signal watcher")
    ap.add_argument("--poll", type=int, default=60)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--backfill-today", action="store_true",
                    help="emit every signal today's completed bars fired (testing/catch-up)")
    a = ap.parse_args()

    playbook = A_BOOK + load_b_book()
    # classification rule: A-book = TP-before-SL > 95%, everything else B-book.
    for _cfg in playbook:
        _cfg["book"] = "A" if _cfg["acc_tpsl"] > 95.0 else "B"
    _na = sum(1 for _cfg in playbook if _cfg["book"] == "A")
    log(f"playbook: {_na} A-book + {len(playbook) - _na} B-book configs (rule: TP-before-SL>95%=A) "
        f"| window {C.ENTRY_OPEN:%H:%M}-{C.ENTRY_CLOSE:%H:%M} CST | csv={CSV_PATH.name}")
    state = jload(STATE_PATH, {})

    if a.backfill_today or a.once:
        n = scan(playbook, state, backfill=a.backfill_today)
        log(f"done — {n} new signal(s)")
        return

    # BTC is 24×7 — scan every poll, all day, every day (incl. weekends)
    while True:
        try:
            scan(playbook, state, backfill=False)
        except Exception as e:
            log(f"scan error: {type(e).__name__}: {e}")
        _time.sleep(a.poll)


if __name__ == "__main__":
    main()
