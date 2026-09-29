"""EMA screener: the Best Bets screen, in a terminal.

    .venv\\Scripts\\python tools\\ema_screener.py                 both tables
    .venv\\Scripts\\python tools\\ema_screener.py --all           every symbol, not only setups
    .venv\\Scripts\\python tools\\ema_screener.py --symbols NVDA,COIN,PLTR
    .venv\\Scripts\\python tools\\ema_screener.py --sandbox       the sandbox host
    .venv\\Scripts\\python tools\\ema_screener.py --json          machine-readable

Needs nothing from the desk -- no server, no sign-in, no database -- only a
Tradier token: set TRADIER_ACCESS_TOKEN, or put it in CONFIG below. The
screening itself is the desk's own module (app.domains.trading.market.
ema_screen), so this terminal and the Best Bets sheet can never disagree about
a ticker.

How the 4-hour bars are made
  Tradier has no 4-hour bar. /markets/timesales serves tick, 1min, 5min and
  15min; /markets/history is daily and coarser. So this asks for 15-minute
  bars with session_filter=open (the regular session: Tradier keeps 40 days of
  15-minute bars that way, 18 with extended hours) and pandas folds them into
  4-hour bars anchored on the 09:30 open -- 09:30-13:30 and 13:30-16:00, the
  session-anchored 4H chart charting platforms draw for US stocks. 40 days is
  ~55 of those bars; the first 20 only warm the 21 EMA up.

Limits and gaps
  /markets calls are capped at 120 a minute in production and 60 on the
  sandbox. Requests are spaced to stay under that, the X-Ratelimit-Available /
  X-Ratelimit-Expiry headers are obeyed when the allowance runs out, and a 429
  or a 5xx is retried with backoff. A symbol with no data, or too little to
  warm the EMA, is reported as such rather than dropped, and a 4-hour bar
  built from fewer 15-minute bars than its window holds is counted ("thin").

Exit codes: 0 done, 2 configuration (no token), 3 the token was refused.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

import requests

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

# ---------------------------------------------------------------------------
# CONFIG -- edit here, or override on the command line.
# ---------------------------------------------------------------------------
CONFIG = {
    "api": {
        # Production data. The sandbox (https://sandbox.tradier.com/v1, or
        # --sandbox) is delayed 15 minutes and allows 60 requests a minute.
        "base_url": "https://api.tradier.com/v1",
        "headers": {
            "Authorization": "Bearer "
                             + os.environ.get("TRADIER_ACCESS_TOKEN", "<ACCESS_TOKEN>"),
            "Accept": "application/json",
        },
        "timeout_s": 20,
        "max_retries": 4,
        # Seconds between requests: 0.55 is ~109 a minute, under the 120 cap.
        "min_interval_s": 0.55,
    },
    "symbols": [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX",
        "PLTR", "COIN", "SMCI", "MU", "UBER", "MSTR", "HOOD", "SOFI", "RIVN", "AFRM",
        "UPST", "RKLB", "IONQ", "QBTS", "RGTI", "SOUN", "HIMS", "CVNA", "APP", "SHOP",
        "SNOW", "NET", "CRWD", "DKNG", "MRNA", "ENPH", "FSLR", "SMR", "OKLO", "ASTS",
    ],
    "history": {
        "interval": "15min",       # the coarsest bar Tradier serves intraday
        "days": 40,                # all Tradier keeps of it for the regular session
        "session": "regular",      # "extended": 04:00-20:00, 18 days of history
    },
    "strategy": {
        "ema_span": 21,            # EMA period, in 4-hour bars
        "deep_pct": 20.0,          # A: a low more than this far under the EMA
        "near_pct": 20.0,          # B: now less than this far above it
        "cross_within": 3,         # B: crossed on one of the last N candles
        "velocity_bars": 5,        # closes the rate of change is fitted over
    },
    "fundamentals": True,          # market cap + industry from Yahoo (yfinance)
}

SANDBOX_URL = "https://sandbox.tradier.com/v1"


class TokenRefused(RuntimeError):
    """401/403: nothing else will work until the token is fixed."""


class Tradier:
    """A Tradier market-data client that paces itself under the rate limit."""

    def __init__(self, api: dict):
        self.base = api["base_url"].rstrip("/")
        self.timeout = api["timeout_s"]
        self.retries = api["max_retries"]
        self.spacing = api["min_interval_s"]
        self.session = requests.Session()
        self.session.headers.update(api["headers"])
        self._last = 0.0
        self._blocked_until = 0.0

    def _pace(self) -> None:
        wait = max(self._blocked_until - time.time(),
                   self._last + self.spacing - time.time())
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def _note_limits(self, headers) -> None:
        """Out of allowance: wait for the window Tradier says it resets at."""
        try:
            available = int(headers.get("X-Ratelimit-Available", "-1"))
            expiry_ms = int(headers.get("X-Ratelimit-Expiry", "0"))
        except ValueError:
            return
        if available == 0 and expiry_ms:
            self._blocked_until = max(self._blocked_until, expiry_ms / 1000.0)

    def get(self, path: str, params: dict) -> dict:
        last_error = "no attempt made"
        for attempt in range(self.retries + 1):
            self._pace()
            try:
                r = self.session.get(f"{self.base}{path}", params=params,
                                     timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}"
                time.sleep(min(30.0, 2.0 ** attempt))
                continue
            self._note_limits(r.headers)
            if r.status_code in (401, 403):
                raise TokenRefused(f"Tradier refused the token (HTTP {r.status_code})")
            if r.status_code == 429 or r.status_code >= 500:
                last_error = f"HTTP {r.status_code}"
                if self._blocked_until <= time.time():
                    self._blocked_until = time.time() + min(60.0, 2.0 ** (attempt + 1))
                continue
            if r.status_code >= 400:
                # 400s are the request's fault; retrying sends the same mistake
                raise ValueError(f"HTTP {r.status_code}: {r.text[:160]}")
            try:
                return r.json() or {}
            except ValueError:
                raise ValueError("Tradier sent a body that is not JSON") from None
        raise ConnectionError(f"gave up after {self.retries + 1} attempts ({last_error})")

    def timesales(self, symbol: str, *, interval: str, start: str,
                  session_filter: str) -> list[dict]:
        """15-minute bars, whatever shape Tradier chose: `series` is null when
        there are none, and a single bar arrives as a bare object."""
        body = self.get("/markets/timesales", {
            "symbol": symbol, "interval": interval, "start": start,
            "session_filter": session_filter})
        series = body.get("series")
        data = series.get("data") if isinstance(series, dict) else None
        if data is None:
            return []
        return data if isinstance(data, list) else [data]


# ---- presentation -----------------------------------------------------------

def _money(v) -> str:
    if v is None:
        return "—"
    return f"{v:,.4f}" if abs(v) < 1 else f"{v:,.2f}"


def _signed(v, suffix: str = "") -> str:
    return "—" if v is None else f"{v:+,.2f}{suffix}"


def _cap(v) -> str:
    if not v:
        return "—"
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if v >= size:
            return f"${v / size:,.2f}{unit}"
    return f"${v:,.0f}"


def _days(row) -> str:
    if row.get("days_to_catch") is None:
        return "not closing"
    return f"{row['days_to_catch']:.1f} d / {row['hours_to_catch']:.0f} h"


def table(title: str, columns: list[tuple[str, str, object]], rows: list[dict]) -> str:
    """A plain-ASCII table: `columns` is (heading, align, value-of-row)."""
    cells = [[str(fn(r)) for _, _, fn in columns] for r in rows]
    widths = [max([len(h)] + [len(c[i]) for c in cells]) for i, (h, _, _) in enumerate(columns)]

    def line(values, aligns):
        return "| " + " | ".join(v.rjust(w) if a == ">" else v.ljust(w)
                                 for v, w, a in zip(values, widths, aligns)) + " |"

    rule = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    out = [title, rule, line([h for h, _, _ in columns], ["<"] * len(columns)), rule]
    out += [line(c, [a for _, a, _ in columns]) for c in cells]
    if not cells:
        out.append("| " + "nothing qualifies".ljust(sum(widths) + 3 * len(widths) - 3) + " |")
    out.append(rule)
    return "\n".join(out)


COMMON = [
    ("Ticker", "<", lambda r: r["symbol"]),
    ("Price", ">", lambda r: _money(r.get("price"))),
    ("21 EMA", ">", lambda r: _money(r.get("ema"))),
    ("+/- EMA", ">", lambda r: _signed(r.get("gap"))),
    ("Distance %", ">", lambda r: _signed(r.get("distance_pct"), "%")),
]
TAIL = [
    ("Mkt cap", ">", lambda r: _cap(r.get("market_cap"))),
    ("Industry", "<", lambda r: (r.get("industry") or "—")[:28]),
]
TABLE_A = COMMON + [
    ("Deepest %", ">", lambda r: _signed(r.get("deepest_pct"), "%")),
    ("Velocity/bar", ">", lambda r: _signed(r.get("velocity"))),
    ("Est. days to catch", ">", _days),
] + TAIL
TABLE_B = COMMON + [
    ("Crossed", ">", lambda r: f"{r['cross_age']} candle{'s' if r['cross_age'] != 1 else ''} ago"),
] + TAIL
TABLE_ALL = [("Setup", "<", lambda r: r.get("setup") or "")] + COMMON + [
    ("Deepest %", ">", lambda r: _signed(r.get("deepest_pct"), "%")),
    ("Crossed", ">", lambda r: "—" if r.get("cross_age") is None else f"{r['cross_age']} ago"),
    ("Thin", ">", lambda r: r.get("thin_bars", 0)),
] + TAIL


# ---- the run ----------------------------------------------------------------

def run(config: dict, *, log=print) -> dict:
    from app.domains.trading.market import ema_screen, fundamentals

    strategy = config["strategy"]
    history = config["history"]
    rules = ema_screen.Rules(span=strategy["ema_span"], deep_pct=strategy["deep_pct"],
                             near_pct=strategy["near_pct"],
                             cross_within=strategy["cross_within"],
                             velocity_bars=strategy["velocity_bars"],
                             session=history["session"])
    client = Tradier(config["api"])
    as_of = ema_screen.now_eastern()
    # Tradier documents `start` as YYYY-MM-DD HH:MM
    start = (as_of - timedelta(days=history["days"])).strftime("%Y-%m-%d 00:00")
    session_filter = "open" if rules.session == "regular" else "all"

    rows = []
    symbols = list(dict.fromkeys(s.strip().upper() for s in config["symbols"] if s.strip()))
    for i, symbol in enumerate(symbols, 1):
        log(f"  [{i:>3}/{len(symbols)}] {symbol:<6}", end="\r")
        try:
            bars = client.timesales(symbol, interval=history["interval"], start=start,
                                    session_filter=session_filter)
            row = ema_screen.screen(symbol, bars, rules, as_of=as_of)
        except TokenRefused:
            raise
        except (ConnectionError, ValueError) as exc:
            row = {"symbol": symbol, "setup": None, "available": False, "bars": 0,
                   "reason": str(exc)}
        rows.append(row)
    log(" " * 40, end="\r")

    readable = [r["symbol"] for r in rows if r.get("available")]
    facts = fundamentals.lookup(readable) if config.get("fundamentals") and readable else {}
    for row in rows:
        known = facts.get(row["symbol"]) or {}
        row["market_cap"] = fundamentals.market_cap(known, row.get("price"))
        row["industry"] = known.get("industry")
    return {"rows": rows, "rules": rules.public(), "as_of": as_of.isoformat(timespec="minutes"),
            "start": start, "tables": ema_screen.by_setup(rows)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="4-hour 21 EMA screener on Tradier data")
    parser.add_argument("--symbols", help="comma-separated, replaces CONFIG['symbols']")
    parser.add_argument("--sandbox", action="store_true", help=f"use {SANDBOX_URL}")
    parser.add_argument("--all", action="store_true", help="also list symbols in neither setup")
    parser.add_argument("--json", action="store_true", help="print JSON instead of tables")
    parser.add_argument("--no-fundamentals", action="store_true", help="skip Yahoo")
    args = parser.parse_args(argv)

    config = json.loads(json.dumps(CONFIG))          # a copy the flags can edit
    if args.symbols:
        config["symbols"] = [s for s in args.symbols.split(",") if s.strip()]
    if args.sandbox:
        config["api"]["base_url"] = SANDBOX_URL
        config["api"]["min_interval_s"] = max(config["api"]["min_interval_s"], 1.05)
    if args.no_fundamentals:
        config["fundamentals"] = False
    if "<ACCESS_TOKEN>" in config["api"]["headers"]["Authorization"]:
        print("No Tradier token: set TRADIER_ACCESS_TOKEN or edit CONFIG in this file.",
              file=sys.stderr)
        return 2

    quiet = (lambda *a, **k: None) if args.json else (
        lambda *a, **k: print(*a, **k, file=sys.stderr, flush=True))
    try:
        result = run(config, log=quiet)
    except TokenRefused as exc:
        print(str(exc), file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    rules = result["rules"]
    print(f"\n4-hour bars from Tradier 15-minute bars, {config['history']['session']} session, "
          f"anchored 09:30 ET · {config['history']['days']} days from {result['start']} · "
          f"as of {result['as_of']} ET")
    print(f"{rules['span']} EMA · A: low > {rules['deep_pct']:g}% under it, turning up · "
          f"B: crossed within {rules['cross_within']} candles, < {rules['near_pct']:g}% above\n")
    print(table("Strategy A — deep retracement, turning back up (soonest catch first)",
                TABLE_A, result["tables"]["A"]))
    print()
    print(table("Strategy B — fresh cross above the EMA (freshest first)",
                TABLE_B, result["tables"]["B"]))
    readable = [r for r in result["rows"] if r.get("available")]
    if args.all:
        print()
        print(table("Every symbol", TABLE_ALL,
                    sorted(readable, key=lambda r: r["distance_pct"])))
    missing = [r for r in result["rows"] if not r.get("available")]
    if missing:
        print(f"\nNot screened ({len(missing)}):")
        for r in missing:
            print(f"  {r['symbol']:<6} {r.get('reason')}")
    thin = [r for r in readable if r.get("thin_bars")]
    if thin:
        print("\nBuilt from thin 4-hour bars (missing 15-minute data): "
              + ", ".join(f"{r['symbol']} ({r['thin_bars']})" for r in thin))
    print("\nDays to catch assume the last 5 bars' pace holds and count the EMA "
          "moving toward the price; they are a projection, not a forecast.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
