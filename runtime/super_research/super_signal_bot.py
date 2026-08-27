#!/usr/bin/env python
"""super_signal_bot.py — one configurable super-signal supervisor per category.

Run three instances (one per category) instead of a bot per ticker:

    python super_signal_bot.py --category etf
    python super_signal_bot.py --category stock
    python super_signal_bot.py --category crypto

Each reads super_research.config, and every poll runs the scan worker of each
ENABLED ticker in its category (<path>/<id>_intraday_bot.py --once). The worker
loads that ticker's own playbook (A_BOOK + results/ensemble.csv) and watches the
latest completed 5m bar on four horizon engines (1h/2h/3h/4h — engine_common.py),
appending one row per qualifying engine to its own <id>_intraday_signals.csv.
Aggregation merges same-bar rows across engines into ONE ledger row and grades
the agreement: 2 engines = HOT, 3 = SUPER HOT, 4 = SUPER++ HOT (eng_hot column);
the repeat-within-20-min `hot` flag is unchanged. Toggle a ticker with
enabled:true/false in the config — the change is picked up the next cycle (no
restart). ETF/stock supervisors only scan during the US session (08:00–15:15
CST weekdays); crypto runs 24×7.

    --once            one scan pass of the enabled tickers
    --backfill-today  each worker emits everything today's bars fired
    --poll N          seconds between cycles (default 60)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time as _time
from datetime import datetime, date, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "super_research.config"
TZ = ZoneInfo("America/Chicago")
PY = sys.executable

RTH_OPEN, RTH_CLOSE = dtime(8, 0), dtime(15, 15)   # US session window (CST)
TZ_IST = ZoneInfo("Asia/Kolkata")
NSE_OPEN, NSE_CLOSE = dtime(9, 15), dtime(15, 30)  # India session window (IST)

# ── central signal ledgers (all A-book / all B-book, across every category) ──
A_CSV = HERE / "a_signals.csv"
B_CSV = HERE / "b_signals.csv"
LOCK = HERE / ".central.lock"
CENTRAL_COLS = ["logged_at_cst", "category", "ticker", "book", "direction",
                "signal", "confluence", "signal_price", "entry_ref",
                "target_price", "stop_price", "stop_deadline_cst",
                "target_deadline_cst", "acc_tp_before_sl_pct", "acc_strict_pct",
                "bar_time_cst", "repeats", "hot", "engines", "eng_hot",
                "tfs", "econ", "outcome", "outcome_at"]

# a signal that recurs > HOT_AFTER times within REPEAT_WINDOW_MIN is logged ONCE
# (its `repeats` count is bumped) and flagged `hot` for the desk (new sound + a
# wildly-bouncing SUPER SIGNAL splash that stays until the user dismisses it).
REPEAT_WINDOW_MIN = 20
HOT_AFTER = 2

# cross-engine grading: the equity workers watch the same playbook on four
# horizon engines (1h/2h/3h/4h) across three candle sizes (5m/15m/30m). The
# same (ticker, direction, wall-clock bar END) firing on N horizons (across
# both books and every timeframe) is merged into ONE ledger row per book and
# graded via eng_hot = "2"/"3"/"4" — HOT / SUPER HOT / SUPER++ HOT; the `tfs`
# column records which candle sizes confirmed. This is separate from the
# repeat-based `hot` flag above, which keeps driving the bouncing splash
# exactly as before.
ENG_RANK = {"30m": 1, "1h": 2, "2h": 3, "3h": 4, "4h": 5}   # 3h kept for old rows
TF_MIN = {"5m": 5, "15m": 15, "30m": 30}
TF_PREF = {"5m": 3, "15m": 2, "30m": 1}     # merged row fronted by finest candle

try:
    import econ_events                       # daily macro context (fail-soft)
except Exception:                            # pragma: no cover
    econ_events = None


def _engs(s):
    return {e for e in (s or "").split("+") if e}


def _bar_end(bar_dt, tf):
    if bar_dt is None:
        return None
    return bar_dt + timedelta(minutes=TF_MIN.get(tf, 5))


def _row_end(r):
    """Wall-clock end of a ledger row's bar (fronting row uses the finest
    confirmed candle; rows predating `tfs` are 5m)."""
    tfs = sorted(_engs(r.get("tfs")), key=lambda t: TF_MIN.get(t, 5))
    return _bar_end(_parse_bar(r.get("bar_time_cst", "")), tfs[0] if tfs else "5m")

# ── archival: every 7 days, roll all-but-the-recent-10 out of each ledger ─────
ARCHIVE_DIR = HERE / "archive"
ARCHIVE_STATE = HERE / ".archive_state.json"
KEEP_RECENT = 10
ARCHIVE_EVERY_DAYS = 7


def log(cat, m):
    print(f"[super-{cat} {datetime.now(TZ):%H:%M:%S}] {m}", flush=True)


def read_cfg():
    txt = CONFIG.read_text(encoding="utf-8")
    if txt and txt[0] == "﻿":
        txt = txt[1:]                                # tolerate a BOM
    return json.loads(txt)


def category(cat):
    c = read_cfg().get("categories", {}).get(cat, {})
    tickers = [t for t in c.get("tickers", []) if t.get("enabled")]
    return tickers, c.get("session", "rth")


def in_session(session):
    if session == "24x7":
        return True
    if session == "india":                     # NSE cash session, IST clock
        now = datetime.now(TZ_IST)
        return now.weekday() < 5 and NSE_OPEN <= now.time() < NSE_CLOSE
    now = datetime.now(TZ)
    return now.weekday() < 5 and RTH_OPEN <= now.time() < RTH_CLOSE


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0   # workers must NOT flash a console window: the
                                # supervisors run detached (console-less), so a
                                # child python.exe would otherwise open a new
                                # console every scan (one per ticker per cycle)


def scan_ticker(t, mode):
    folder = HERE / t["path"]
    bot = folder / f'{t["id"]}_intraday_bot.py'
    if not bot.exists():
        return f'{t["id"]}: NO WORKER ({bot.name})'
    try:
        r = subprocess.run([PY, bot.name, mode], cwd=folder,
                           capture_output=True, text=True, timeout=240,
                           creationflags=CREATE_NO_WINDOW)
        out = (r.stdout or "") + (r.stderr or "")
        sigs = [ln for ln in out.splitlines() if "SIGNAL" in ln]
        if r.returncode != 0:
            return f'{t["id"]}: worker rc={r.returncode}'
        return f'{t["id"]}: {len(sigs)} new' if sigs else f'{t["id"]}: ok'
    except Exception as e:
        return f'{t["id"]}: ERR {type(e).__name__}: {e}'


# ── central aggregation ──────────────────────────────────────────────────────
def _read_worker_rows(path):
    if not path.exists():
        return []
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _acquire_lock():
    # exclusive lock file shared by the 3 supervisors; steals a stale (>20s) lock
    for _ in range(120):
        try:
            fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return
        except FileExistsError:
            try:
                if _time.time() - LOCK.stat().st_mtime > 20:
                    LOCK.unlink(); continue
            except FileNotFoundError:
                continue
            _time.sleep(0.05)


def _release_lock():
    try:
        LOCK.unlink()
    except FileNotFoundError:
        pass


def _read_ledger_rows(path):
    if not path.exists():
        return []
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _write_ledger_rows(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CENTRAL_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _parse_bar(s):
    try:
        return datetime.strptime((s or "")[:16], "%Y-%m-%d %H:%M")
    except Exception:
        return None


def _sig_key(r):
    return f'{r.get("category")}|{r.get("ticker")}|{r.get("book")}|{r.get("direction")}|{r.get("signal")}'


def aggregate(cat, tickers):
    """Roll this category's NEW A/B signals into the central ledgers, tagged with
    category + the worker's CST timestamp. Multi-engine worker rows for the same
    bar are merged into ONE ledger row per book (fronted by the longest horizon,
    `engines` = every horizon that fired) and graded by cross-engine agreement:
    eng_hot 2/3/4 = HOT / SUPER HOT / SUPER++ HOT. A signal that recurs within
    REPEAT_WINDOW_MIN is still logged ONCE — its `repeats` count is bumped and,
    past HOT_AFTER, it is flagged `hot` (unchanged). Deduped per-category via a
    state file (the 3 categories own disjoint tickers; only the ledger write is
    lock-shared)."""
    state = HERE / f".agg_state_{cat}.json"
    try:
        seen = set(json.loads(state.read_text(encoding="utf-8")))
    except Exception:
        seen = set()
    econ_note = ""
    if econ_events is not None:
        try:
            ctx = econ_events.refresh_today(HERE)
            econ_note = ctx.get("note", "") if ctx.get("high_impact") else ""
        except Exception:
            pass
    fresh = {"A": {}, "B": {}}   # merge_key -> {row, rank, bar, bar_key}
    bar_engines = {}             # ticker|direction|bar-END -> horizons (both books, all tfs)
    bar_tfs = {}                 # ticker|direction|bar-END -> candle sizes confirmed
    for t in tickers:
        for row in _read_worker_rows(HERE / t["path"] / t["csv"]):
            book = (row.get("book") or "").strip()
            if book not in ("A", "B"):
                continue
            tk = (row.get("ticker") or t.get("label") or t["id"].upper())
            eng = (row.get("engine") or "").strip()
            tf = (row.get("tf") or "").strip() or ("5m" if eng else "")
            key = f'{cat}|{tk}|{row.get("bar_time_cst")}|{book}|{row.get("direction")}|{row.get("signal")}'
            if eng and eng != "4h":
                key += f"|{eng}"        # 4h keeps the pre-engine key format
            if tf and tf != "5m":
                key += f"|tf{tf}"       # 5m keeps the pre-timeframe key format
            if key in seen:
                continue
            seen.add(key)
            out = {c: row.get(c, "") for c in CENTRAL_COLS}
            out.update({"category": cat, "ticker": tk, "book": book, "repeats": "1", "hot": ""})
            bar_dt = _parse_bar(row.get("bar_time_cst", ""))
            end = _bar_end(bar_dt, tf or "5m")
            bk = f'{tk}|{row.get("direction")}|{end:%Y-%m-%d %H:%M}' if end else f'{tk}|{row.get("direction")}|?'
            if eng:
                bar_engines.setdefault(bk, set()).add(eng)
            if tf:
                bar_tfs.setdefault(bk, set()).add(tf)
            mk = f'{cat}|{tk}|{book}|{row.get("direction")}|{bk.rsplit("|", 1)[-1]}'
            slot = fresh[book].setdefault(mk, {"row": None, "rank": (-1, -1),
                                               "bar_key": bk, "bar": bar_dt})
            rank = (ENG_RANK.get(eng, 9), TF_PREF.get(tf, 0))
            if rank > slot["rank"]:      # longest horizon, then finest candle, fronts
                slot["row"], slot["rank"] = out, rank
                slot["bar"] = bar_dt
    if not (fresh["A"] or fresh["B"]):
        return
    n_new = n_hot = 0
    tiers = {2: 0, 3: 0, 4: 0}
    _acquire_lock()
    try:
        for book, path in (("A", A_CSV), ("B", B_CSV)):
            if not fresh[book]:
                continue
            rows = _read_ledger_rows(path)
            for r in rows:                                   # migrate older rows
                r.setdefault("repeats", "1"); r.setdefault("hot", "")
                r.setdefault("engines", ""); r.setdefault("eng_hot", "")
                r.setdefault("tfs", ""); r.setdefault("econ", "")
                r.setdefault("outcome", ""); r.setdefault("outcome_at", "")
            for slot in sorted(fresh[book].values(), key=lambda s: (s["bar"] is None, s["bar"])):
                out, bar_dt = slot["row"], slot["bar"]
                engs = bar_engines.get(slot["bar_key"], set())
                tfs = bar_tfs.get(slot["bar_key"], set())
                out["engines"] = "+".join(sorted(engs, key=lambda e: ENG_RANK.get(e, 9)))
                out["eng_hot"] = str(len(engs)) if len(engs) >= 2 else ""
                out["tfs"] = "+".join(sorted(tfs, key=lambda t_: TF_MIN.get(t_, 5)))
                out["econ"] = econ_note
                k = _sig_key(out)
                # same (ticker, book, direction, bar END) already in the ledger
                # (a batch from an earlier cycle, possibly another candle size
                # or config name) -> union engines + tfs, upgrade the grade
                end = _row_end(out)
                same = next((r for r in rows
                             if r.get("category") == out.get("category")
                             and r.get("ticker") == out.get("ticker")
                             and r.get("direction") == out.get("direction")
                             and _row_end(r) == end), None)
                if same is not None:
                    u = _engs(same.get("engines")) | engs
                    ut = _engs(same.get("tfs")) | tfs
                    same["engines"] = "+".join(sorted(u, key=lambda e: ENG_RANK.get(e, 9)))
                    same["eng_hot"] = str(len(u)) if len(u) >= 2 else ""
                    same["tfs"] = "+".join(sorted(ut, key=lambda t_: TF_MIN.get(t_, 5)))
                    continue
                cand, cand_bar = None, None                  # latest same-signal group in window
                for r in rows:
                    if _sig_key(r) != k:
                        continue
                    rb = _parse_bar(r.get("bar_time_cst", ""))
                    if rb is None or bar_dt is None:
                        continue
                    if 0 <= (bar_dt - rb).total_seconds() <= REPEAT_WINDOW_MIN * 60 and (cand_bar is None or rb > cand_bar):
                        cand, cand_bar = r, rb
                if cand is not None:                          # repeat within 20 min -> bump, log once
                    n = int(cand.get("repeats") or 1) + 1
                    cand["repeats"] = str(n)
                    cand["logged_at_cst"] = out.get("logged_at_cst", cand.get("logged_at_cst"))
                    if int(out.get("eng_hot") or 0) > int(cand.get("eng_hot") or 0):
                        cand["engines"], cand["eng_hot"] = out["engines"], out["eng_hot"]
                    ut = _engs(cand.get("tfs")) | tfs
                    cand["tfs"] = "+".join(sorted(ut, key=lambda t_: TF_MIN.get(t_, 5)))
                    if n > HOT_AFTER and cand.get("hot") != "1":
                        cand["hot"] = "1"; n_hot += 1
                    elif n > HOT_AFTER:
                        cand["hot"] = "1"
                else:
                    rows.append(out); n_new += 1
                    if len(engs) in tiers:
                        tiers[len(engs)] += 1
            _write_ledger_rows(path, rows)
        try:
            state.write_text(json.dumps(sorted(seen)[-20000:]), encoding="utf-8")
        except Exception:
            pass
        msg = f"aggregated {n_new} new -> a_signals.csv / b_signals.csv"
        grades = [f"{tiers[4]} SUPER++ HOT" if tiers[4] else "",
                  f"{tiers[3]} SUPER HOT" if tiers[3] else "",
                  f"{tiers[2]} HOT" if tiers[2] else ""]
        grades = [g for g in grades if g]
        if grades:
            msg += " · engine grades: " + " / ".join(grades)
        if n_hot:
            msg += f" · {n_hot} went HOT (repeat within {REPEAT_WINDOW_MIN}m)"
        log(cat, msg)
    finally:
        _release_lock()


# ── outcome resolution: ✔ target / ✘ stop / ⏱ timeout on ledger rows ─────────
# Every OUTCOME_EVERY_MIN minutes one supervisor (whichever gets there first —
# guarded by the shared lock + a claim file) walks the 5m bars after each
# unresolved signal and stamps `outcome`/`outcome_at`: research conventions —
# race starts at the first bar after the signal candle ENDS, same-bar
# TP+SL tie counts as a stop, the target deadline (bar date, CST) times it out.
OUTCOME_EVERY_MIN = 3
RESOLVE_STATE = HERE / ".resolve_state.json"
YF_MAP = {"SPX": "^GSPC", "BTC": "BTC-USD"}   # ledger label -> yfinance symbol


def _fetch_5m(symbol):
    # a hung quote fetch must never freeze the supervisor loop (it did once:
    # etf supervisor stalled from Thu 15:15 to Fri noon on a socket with no
    # timeout) — cap every socket op this process makes
    import socket
    socket.setdefaulttimeout(30)
    import yfinance as yf
    raw = yf.download(symbol, interval="5m", period="5d", prepost=True,
                      progress=False, auto_adjust=False)
    if raw is None or raw.empty:
        return None
    import pandas as pd
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.index = raw.index.tz_convert("America/Chicago").tz_localize(None)
    return raw[["Open", "High", "Low", "Close"]].dropna()


def _resolve_row(r, bars, now):
    """(outcome, at_str) once decidable, else None. All naive CST datetimes."""
    bar = _parse_bar(r.get("bar_time_cst", ""))
    if bar is None:
        return None
    try:
        tp, sl = float(r.get("target_price")), float(r.get("stop_price"))
    except (TypeError, ValueError):
        return None
    tfs = [t for t in _engs(r.get("tfs")) if t in TF_MIN]
    tf_min = min((TF_MIN[t] for t in tfs), default=5)
    start = bar + timedelta(minutes=tf_min)         # signal candle END
    try:
        hh, mm = map(int, (r.get("target_deadline_cst") or "").split(":"))
        dl = bar.replace(hour=hh, minute=mm)
    except Exception:
        dl = bar + timedelta(minutes=245)
    if dl <= bar:
        dl += timedelta(days=1)                     # crypto race over midnight
    longside = (r.get("direction") == "LONG")
    if bars is not None:
        walk = bars[(bars.index >= start) & (bars.index < dl)]
        for ts, b in walk.iterrows():
            hit_tp = b["High"] >= tp if longside else b["Low"] <= tp
            hit_sl = b["Low"] <= sl if longside else b["High"] >= sl
            if hit_sl:                              # same-bar tie counts as a stop
                return "stop", f"{ts:%H:%M}"
            if hit_tp:
                return "target", f"{ts:%H:%M}"
    if now >= dl:
        return "timeout", f"{dl:%H:%M}"
    return None                                     # still racing


def resolve_outcomes():
    now = datetime.now(TZ).replace(tzinfo=None)
    try:                                            # cheap out-of-lock gate
        last = json.loads(RESOLVE_STATE.read_text(encoding="utf-8"))["last"]
        if (now - datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds() < OUTCOME_EVERY_MIN * 60:
            return
    except Exception:
        pass
    _acquire_lock()
    try:
        try:                                        # re-check under the lock
            last = json.loads(RESOLVE_STATE.read_text(encoding="utf-8"))["last"]
            if (now - datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds() < OUTCOME_EVERY_MIN * 60:
                return
        except Exception:
            pass
        RESOLVE_STATE.write_text(json.dumps({"last": f"{now:%Y-%m-%d %H:%M:%S}"}), encoding="utf-8")
        ledgers = {p: _read_ledger_rows(p) for p in (A_CSV, B_CSV)}
        pending = {}
        for rows in ledgers.values():
            for r in rows:
                r.setdefault("outcome", ""); r.setdefault("outcome_at", "")
                if not r.get("outcome") and _parse_bar(r.get("bar_time_cst", "")):
                    pending.setdefault(r.get("ticker") or "", []).append(r)
        if not pending:
            return
        counts = {"target": 0, "stop": 0, "timeout": 0}
        changed = False
        for tk, rows in pending.items():
            bars = None
            try:
                bars = _fetch_5m(YF_MAP.get(tk, tk))
            except Exception:
                pass                                # timeout-only resolution below
            for r in rows:
                res = _resolve_row(r, bars, now)
                if res:
                    r["outcome"], r["outcome_at"] = res
                    counts[res[0]] += 1
                    changed = True
        if changed:
            for path, rows in ledgers.items():
                _write_ledger_rows(path, rows)
            print(f"[resolve {datetime.now(TZ):%H:%M:%S}] outcomes: "
                  f"{counts['target']} target / {counts['stop']} stop / "
                  f"{counts['timeout']} timeout", flush=True)
    finally:
        _release_lock()


def maybe_archive():
    """Every ARCHIVE_EVERY_DAYS days, move all but the most recent KEEP_RECENT
    signals of each ledger into super_research/archive/, so the live ledgers stay
    small while full history is preserved. Guarded by the shared lock + a state
    file, so only one supervisor rotates per window."""
    _acquire_lock()
    try:
        today = datetime.now(TZ).date()
        try:
            last = date.fromisoformat(json.loads(ARCHIVE_STATE.read_text(encoding="utf-8"))["last_archive"])
        except Exception:
            last = None
        if last is None:                       # first run — start the 7-day clock
            ARCHIVE_STATE.write_text(json.dumps({"last_archive": today.isoformat()}), encoding="utf-8")
            return
        if (today - last).days < ARCHIVE_EVERY_DAYS:
            return
        ARCHIVE_DIR.mkdir(exist_ok=True)
        moved = 0
        for name in ("a_signals.csv", "b_signals.csv"):
            src = HERE / name
            if not src.exists():
                continue
            try:
                with open(src, newline="", encoding="utf-8-sig") as f:
                    rows = list(csv.reader(f))
            except Exception:
                continue
            if len(rows) <= KEEP_RECENT + 1:   # header + <=10 data rows -> nothing to roll
                continue
            header, data = rows[0], rows[1:]
            ci = header.index("logged_at_cst") if "logged_at_cst" in header else 0
            data.sort(key=lambda r: r[ci] if ci < len(r) else "", reverse=True)  # newest first
            keep, archived = data[:KEEP_RECENT], data[KEEP_RECENT:]
            arch = ARCHIVE_DIR / name
            with open(arch, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if not arch.exists() or arch.stat().st_size == 0:
                    w.writerow(header)
                w.writerows(archived)
            with open(src, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(header)
                w.writerows(keep)
            moved += len(archived)
        ARCHIVE_STATE.write_text(json.dumps({"last_archive": today.isoformat()}), encoding="utf-8")
        if moved:
            print(f"[archive {datetime.now(TZ):%H:%M:%S}] rotated {moved} signals to archive/ "
                  f"(kept recent {KEEP_RECENT} per ledger)", flush=True)
    finally:
        _release_lock()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="super-signal category supervisor")
    ap.add_argument("--category", required=True, choices=["etf", "stock", "crypto", "india"])
    ap.add_argument("--poll", type=int, default=60)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--backfill-today", action="store_true")
    a = ap.parse_args()
    cat = a.category
    mode = "--backfill-today" if a.backfill_today else "--once"

    tickers, session = category(cat)
    log(cat, f"supervisor up · {len(tickers)} enabled · session={session} "
             f"· workers={[t['id'] for t in tickers]}")

    if a.once or a.backfill_today:
        for t in tickers:
            log(cat, scan_ticker(t, mode))
        aggregate(cat, tickers)
        resolve_outcomes()
        maybe_archive()
        log(cat, "done")
        return

    while True:
        tickers, session = category(cat)             # re-read config every cycle
        if in_session(session):
            for t in tickers:
                try:
                    log(cat, scan_ticker(t, "--once"))
                except Exception as e:
                    log(cat, f'{t["id"]}: loop err {type(e).__name__}: {e}')
        aggregate(cat, tickers)                       # roll new signals into the ledgers
        try:
            resolve_outcomes()                        # ✔/✘ marks (lock+claim guarded)
        except Exception as e:
            log(cat, f"resolve err {type(e).__name__}: {e}")
        maybe_archive()                               # weekly rotation to archive/ (no-op most cycles)
        _time.sleep(a.poll)


if __name__ == "__main__":
    main()
