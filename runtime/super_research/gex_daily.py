#!/usr/bin/env python
"""gex_daily.py — daily gamma-exposure snapshot for SPY + QQQ from flashAlpha.

Scheduled 09:00 CST daily (FlashAlphaGEX_Daily). The flashAlpha Free plan
allows FIVE requests per day, so this job makes exactly one summary call per
ticker and nothing else. Each payload is archived to gex/<as_of-date>.json and
the merged latest view is written to gex_daily.json, which /api/super/state
serves to the desk banner.

Extracted per ticker: net GEX + dealer regime, gamma flip, call wall and put
wall (the API's aggregate highest-GEX strikes; for SPY/QQQ the gamma surface
is dominated by expirations inside the next couple of business days, so these
walls are in practice the +-2-business-day walls — strike/expiry-level
granularity needs the paid plan and slots in via TRY_STRIKES below), plus the
macro vol block (VIX/VVIX/SKEW/MOVE, term structure, fear&greed).

Quota errors keep the previous good data and stamp `stale: true`.

Usage:  python gex_daily.py           # fetch + write (2 API calls)
        python gex_daily.py --show    # print current gex_daily.json, no calls
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
TZ = ZoneInfo("America/Chicago")
TICKERS = ["spy", "qqq"]
OUT = HERE / "gex_daily.json"
ARCHIVE = HERE / "gex"
ENV = HERE / "flashalpha.env"
BASE = "https://lab.flashalpha.com/v1/stock/{t}/summary"
TRY_STRIKES = False    # flip only on a paid plan: per-strike endpoint probing


def log(m):
    print(f"[gex {datetime.now(TZ):%Y-%m-%d %H:%M:%S}] {m}", flush=True)


def api_key() -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("FLASHALPHA_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("FLASHALPHA_API_KEY missing from flashalpha.env")


def fetch(t: str, key: str) -> dict:
    req = urllib.request.Request(BASE.format(t=t), headers={"X-Api-Key": key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def extract(p: dict) -> dict:
    ex = p.get("exposure") or {}
    px = (p.get("price") or {}).get("last")
    return {
        "as_of": p.get("as_of"),
        "price": round(px, 2) if isinstance(px, (int, float)) else px,
        "net_gex": ex.get("net_gex"),
        "regime": ex.get("regime"),
        "gamma_flip": round(ex["gamma_flip"], 2) if isinstance(ex.get("gamma_flip"), (int, float)) else None,
        # aggregate highest-GEX strikes; SPY/QQQ gamma concentrates in the next
        # ~2 business days of expiries, so these serve as the near-dated walls
        "call_wall": ex.get("call_wall"),
        "put_wall": ex.get("put_wall"),
        "gamma_note": (ex.get("interpretation") or {}).get("gamma"),
        "atm_iv": (p.get("volatility") or {}).get("atm_iv"),
        "pc_ratio_volume": (p.get("options_flow") or {}).get("pc_ratio_volume"),
    }


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if "--show" in sys.argv:
        print(OUT.read_text(encoding="utf-8") if OUT.exists() else "{}")
        return
    key = api_key()
    prev = {}
    try:
        prev = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        pass
    out = {"fetched_at": f"{datetime.now(TZ):%Y-%m-%d %H:%M:%S}", "stale": False,
           "tickers": dict(prev.get("tickers") or {}), "macro": prev.get("macro")}
    ARCHIVE.mkdir(exist_ok=True)
    errors = 0
    for t in TICKERS:
        try:
            p = fetch(t, key)
            if p.get("status") == "ERROR":
                raise RuntimeError(p.get("error") or "API error")
            day = (p.get("as_of") or out["fetched_at"])[:10]
            (ARCHIVE / f"{day}_{t}.json").write_text(json.dumps(p, indent=1), encoding="utf-8")
            out["tickers"][t.upper()] = extract(p)
            if p.get("macro"):
                m = p["macro"]
                out["macro"] = {
                    "vix": (m.get("vix") or {}).get("value"),
                    "vix_chg_pct": (m.get("vix") or {}).get("change_pct"),
                    "vvix": (m.get("vvix") or {}).get("value"),
                    "skew": (m.get("skew") or {}).get("value"),
                    "move": (m.get("move") or {}).get("value"),
                    "term": (m.get("vix_term_structure") or {}).get("structure"),
                    "fear_greed": (m.get("fear_and_greed") or {}).get("score"),
                }
            log(f"{t.upper()}: net_gex {out['tickers'][t.upper()]['net_gex']} "
                f"({out['tickers'][t.upper()]['regime']}) flip {out['tickers'][t.upper()]['gamma_flip']} "
                f"walls {out['tickers'][t.upper()]['call_wall']}/{out['tickers'][t.upper()]['put_wall']}")
        except Exception as e:
            errors += 1
            log(f"{t.upper()}: fetch failed ({e}) — keeping previous data")
    out["stale"] = errors > 0
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    log(f"written {OUT.name} (stale={out['stale']})")


if __name__ == "__main__":
    main()
