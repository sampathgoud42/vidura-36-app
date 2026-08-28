#!/usr/bin/env python3
"""
btc60_research_signal_bot.py — btc_research signal provider for the Kalshi
BTC-60 bot (owner request 2026-07-13).
===========================================================================
Runs the super_research/btc_research playbook LIVE and hands each fresh
signal to bot_kalshi_btc60_burst.py through a small JSON file:

    playbook : A_BOOK (hardcoded top setups) + every ensemble composite in
               btc_research/results/ensemble.csv.
    data     : yfinance BTC-USD 5m (same source the research was built on),
               newest CLOSED bar only, evaluated every --poll seconds.
    features : btc_research.features / signals — identical code path to the
               backtest (VWAP, pivots, POC, ADI, MACD blocks, noise gate).
    output   : btc60_research_signal.json   (latest signal — the handoff)
               btc60_research_signals.csv   (append-only history)

AUTO-UPDATE (owner request 2026-07-15): every UPDATE_EVERY_H hours (24h by
default) the provider re-runs the btc_research pipeline (research.py +
iterate.py) to regenerate results/ensemble.csv from the latest 60-day
yfinance window (its cache auto-refreshes when >12h old), then hot-reloads
the playbook — so the live signal set self-refreshes daily without a restart.

The Kalshi bot consumes ONLY this handoff (its old S1/S2/S3 committee is
removed); it applies its own execution gates (minute-of-hour, 30-70c strike
band, bankroll, one-position) and trades the picked strike.

Run:
    python btc60_research_signal_bot.py                # live loop, poll 60s
    python btc60_research_signal_bot.py --once         # single scan (test)
    python btc60_research_signal_bot.py --update-now   # regen playbook now,then loop
    python btc60_research_signal_bot.py --update-every 24   # override cadence (h)
"""
from __future__ import annotations

import argparse
import atexit
import csv
import json
import os
import subprocess
import sys
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_HERE = Path(__file__).resolve().parent            # .../kalshi/btc/btc60

def _main_root(p: Path) -> Path:
    parts = p.parts
    for i, part in enumerate(parts[:-1]):
        if part.lower() == ".claude" and parts[i + 1].lower() == "worktrees":
            return Path(*parts[:i])
    return p

_RESEARCH = _main_root(_HERE.parents[3]) / "super_research" / "btc_research"
sys.path.insert(0, str(_RESEARCH))

import config as C                                  # noqa: E402
import features                                     # noqa: E402
import signals                                      # noqa: E402
import btc_intraday_bot as research_bot             # noqa: E402  A_BOOK, load_b_book, fetch_bars

TZ = ZoneInfo(C.TZ)                                 # America/Chicago
HANDOFF = _HERE / "btc60_research_signal.json"
CSV_PATH = _HERE / "btc60_research_signals.csv"
STATE_PATH = _HERE / "btc60_research_signal_state.json"
LOG_PATH = _HERE / f"btc60_research_signal_{datetime.now():%Y%m%d}.log"
LOCK_PATH = _HERE / "btc60_research_signal.lock"

UPDATE_EVERY_H = 24                                 # regen the playbook this often
_ENSEMBLE_CSV = _RESEARCH / "results" / "ensemble.csv"
_REGEN_SCRIPTS = ("research.py", "iterate.py")      # run in order in _RESEARCH
_REGEN_TIMEOUT_S = 1800                             # 30 min cap per script

CSV_COLS = ["logged_at_cst", "bar_time_cst", "direction", "signal", "window",
            "confluence", "acc_tp_before_sl_pct", "acc_strict_pct",
            "bt_trades", "signal_price", "target_price", "stop_price"]


def log(msg: str) -> None:
    line = f"[research-sig {datetime.now(TZ):%H:%M:%S} CST] {msg}"
    print(line, flush=True)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def jload(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5).stdout
            return str(pid) in out
        except Exception:
            return True
    try:
        os.kill(pid, 0); return True
    except ProcessLookupError:
        return False
    except Exception:
        return True


def acquire_lock() -> None:
    if LOCK_PATH.is_file():
        raw = LOCK_PATH.read_text().strip()
        old = int(raw) if raw.isdigit() else None
        if old and _pid_alive(old):
            sys.exit(f"[LOCK] another signal provider is running (PID {old})")
        log(f"stale lock (PID {old}) — taking over")
    LOCK_PATH.write_text(str(os.getpid()))
    atexit.register(release_lock)


def release_lock() -> None:
    try:
        if LOCK_PATH.is_file() and LOCK_PATH.read_text().strip() == str(os.getpid()):
            LOCK_PATH.unlink()
    except Exception:
        pass


def load_playbook() -> list[dict]:
    """A_BOOK + the current ensemble.csv, book-labelled. Reads ensemble.csv
    fresh each call, so calling this after a regen hot-reloads the playbook."""
    pb = research_bot.A_BOOK + research_bot.load_b_book()
    for cfg in pb:
        cfg["book"] = "A" if cfg["acc_tpsl"] > 95.0 else "B"
    return pb


def regenerate_playbook() -> bool:
    """Re-run the btc_research pipeline (research.py then iterate.py) to
    rebuild results/ensemble.csv from the latest 60-day yfinance window (its
    disk cache auto-refreshes when >12h old). Blocking, a few minutes; called
    at most once per UPDATE_EVERY_H. Returns True iff BOTH scripts succeed AND
    ensemble.csv came out non-empty (else the old playbook is kept)."""
    for script in _REGEN_SCRIPTS:
        try:
            log(f"update: running {script} …")
            r = subprocess.run(
                [sys.executable, script], cwd=str(_RESEARCH),
                capture_output=True, text=True, timeout=_REGEN_TIMEOUT_S)
            if r.returncode != 0:
                tail = (r.stderr or r.stdout or "").strip()[-300:]
                log(f"update: {script} FAILED rc={r.returncode}: {tail}")
                return False
            log(f"update: {script} done")
        except Exception as e:
            log(f"update: {script} error: {type(e).__name__}: {e}")
            return False
    try:
        import pandas as _pd
        if not _ENSEMBLE_CSV.exists() or _pd.read_csv(_ENSEMBLE_CSV).empty:
            log("update: ensemble.csv missing/empty after regen — keeping old")
            return False
    except Exception as e:
        log(f"update: ensemble.csv check failed ({e}) — keeping old")
        return False
    return True


def scan_once(playbook: list[dict], state: dict) -> int:
    """Evaluate the newest CLOSED bar against the whole playbook.  On a hit,
    write the handoff JSON + CSV row.  Returns #new signals."""
    bars = research_bot.fetch_bars()
    d = features.build(bars)
    blk = signals.blocks(d)
    ts_last = d.index[-1]
    tod = ts_last.time()
    win_ok = {name: (a <= tod < b) for name, (a, b) in C.WINDOWS.items()}

    emitted = set(state.get("emitted", []))
    gates: dict[tuple, bool] = {}
    hits: dict[str, list[dict]] = {}
    for cfg in playbook:
        if not win_ok.get(cfg["window"], False):
            continue
        gk = (cfg["nk"], cfg["vm"])
        if gk not in gates:
            gates[gk] = bool(signals.noise_gate(d, *gk).iloc[-1])
        if not gates[gk]:
            continue
        ok = all(bool(blk[cfg["direction"]][b].iloc[-1]) for b in cfg["combo"])
        if ok:
            hits.setdefault(cfg["direction"], []).append(cfg)

    n_new = 0
    for direction, cfgs in hits.items():
        sig_id = f"{ts_last:%Y-%m-%d %H:%M}|{direction}"
        if sig_id in emitted:
            continue
        emitted.add(sig_id)
        best = max(cfgs, key=lambda x: (x["acc_tpsl"], x["acc_strict"],
                                        x["bt_trades"]))
        price = float(d["Close"].iloc[-1])
        sgn = 1 if direction == "LONG" else -1
        payload = {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "bar_time_cst": f"{ts_last:%Y-%m-%d %H:%M}",
            "bar_epoch": int(ts_last.timestamp()),
            "direction": direction,
            "signal": "+".join(best["combo"]),
            "window": best["window"],
            "confluence": len(cfgs),
            "acc_tp_before_sl_pct": best["acc_tpsl"],
            "acc_strict_pct": best["acc_strict"],
            "bt_trades": best["bt_trades"],
            "signal_price": round(price, 2),
            "target_price": round(price + sgn * C.TP_POINTS, 2),
            "stop_price": round(price - sgn * C.SL_POINTS, 2),
        }
        HANDOFF.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        new = not CSV_PATH.exists()
        with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLS)
            if new:
                w.writeheader()
            w.writerow({
                "logged_at_cst": f"{datetime.now(TZ):%Y-%m-%d %H:%M:%S}",
                "bar_time_cst": payload["bar_time_cst"],
                "direction": direction, "signal": payload["signal"],
                "window": payload["window"], "confluence": len(cfgs),
                "acc_tp_before_sl_pct": best["acc_tpsl"],
                "acc_strict_pct": best["acc_strict"],
                "bt_trades": best["bt_trades"],
                "signal_price": payload["signal_price"],
                "target_price": payload["target_price"],
                "stop_price": payload["stop_price"]})
        n_new += 1
        log(f"SIGNAL {direction} x{len(cfgs)} {payload['signal']} "
            f"({best['window']}, acc {best['acc_tpsl']:.0f}%) @ "
            f"{ts_last:%H:%M} px {price:,.2f} -> handoff written")

    state["emitted"] = sorted(emitted)[-500:]
    STATE_PATH.write_text(json.dumps(state, indent=1), encoding="utf-8")
    return n_new


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="btc_research signal provider")
    ap.add_argument("--poll", type=int, default=60)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--update-now", action="store_true",
                    help="regenerate the playbook once at startup, then loop")
    ap.add_argument("--update-every", type=float, default=UPDATE_EVERY_H,
                    help="playbook auto-update cadence in hours (default 24)")
    a = ap.parse_args()

    playbook = load_playbook()
    log(f"playbook loaded: {len(playbook)} configs from {_RESEARCH.name} "
        f"(TP {C.TP_POINTS:.0f} / SL {C.SL_POINTS:.0f} pts) | "
        f"auto-update every {a.update_every:g}h | handoff -> {HANDOFF.name}")
    state = jload(STATE_PATH, {})

    if a.update_now:
        log("update-now: regenerating research playbook at startup…")
        if regenerate_playbook():
            playbook = load_playbook()
            log(f"update-now: playbook refreshed -> {len(playbook)} configs")
        else:
            log("update-now: regen failed — keeping the current playbook")

    if a.once:
        n = scan_once(playbook, state)
        log(f"done — {n} new signal(s)")
        return

    acquire_lock()          # long-running loop only: never run two providers

    update_secs = a.update_every * 3600
    # Base the schedule on the current ensemble.csv age so a launch with a
    # stale playbook refreshes on the first tick; a fresh one waits the full
    # cadence. --update-now already refreshed above, so reset the clock.
    last_update = (_time.time() if a.update_now
                   else (_ENSEMBLE_CSV.stat().st_mtime
                         if _ENSEMBLE_CSV.exists() else 0.0))

    while True:
        # 24h auto-update: regenerate the research playbook + hot-reload it
        if _time.time() - last_update >= update_secs:
            log(f"update: {a.update_every:g}h elapsed — regenerating research "
                f"playbook (research.py + iterate.py)…")
            if regenerate_playbook():
                playbook = load_playbook()
                log(f"update: playbook refreshed -> {len(playbook)} configs")
            else:
                log("update: regen failed — keeping the previous playbook")
            last_update = _time.time()

        try:
            scan_once(playbook, state)
        except Exception as e:
            log(f"scan error: {type(e).__name__}: {e}")
        _time.sleep(a.poll)


if __name__ == "__main__":
    main()
