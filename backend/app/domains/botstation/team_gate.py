"""The TEAM gate: approved trade rules, enforced at the moment money is spent.

Rules are proposed and backtested by ``TEAM/team.py review``, and only the
ones the operator has approved (``TEAM/team.py approve P-xxxx``) reach the
active ruleset this module reads -- ``TEAM/rules/active.json``, or wherever
``TEAM_RULES_PATH`` points. The file is re-read when it changes, so an
approval takes effect on the next order without a restart.

``evaluate`` is the ONE definition of what a rule does. The backtester imports
it too, so a backtest of a rule and the live gate cannot disagree about it.

Failure policy: if the ruleset cannot be read, the gate lets the trade through
and logs a warning. Before TEAM existed, every bot traded with no rules at all.
A broken rules file puts it back in that state; it never stops a bot that was
working before.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[4]
DEFAULT_RULES = _REPO / "TEAM" / "rules" / "active.json"
GATE_LOG = _REPO / "TEAM" / "rules" / "gate_log.jsonl"
TZ = "America/Chicago"

RULE_TYPES = ("suspend", "block_price_band", "price_range", "block_hours",
              "max_legs", "max_stake_usd")


@dataclass
class Verdict:
    allowed: bool = True
    stake_usd: float | None = None          # set when a rule capped the stake
    reasons: list[str] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    version: int = 0

    @property
    def detail(self) -> str:
        return "; ".join(self.reasons)


def _hour_ct(when: datetime) -> int:
    from zoneinfo import ZoneInfo
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(ZoneInfo(TZ)).hour


def evaluate(rules: list[dict], *, bot: str, price_c: float | None,
             stake_usd: float | None = None, legs: int | None = None,
             when: datetime | None = None, version: int = 0) -> Verdict:
    """Apply every rule scoped to ``bot``. Pure -- no I/O."""
    v = Verdict(stake_usd=stake_usd, version=version)
    for r in rules:
        if r.get("bot") != bot:
            continue
        kind, p, rid = r.get("type"), r.get("params") or {}, r.get("id", "?")
        hit = None
        if kind == "suspend":
            hit = "bot suspended"
        elif kind == "block_price_band" and price_c is not None:
            if p["min_c"] <= price_c < p["max_c"]:
                hit = f"price {price_c:g}c in blocked band {p['min_c']}-{p['max_c']}c"
        elif kind == "price_range" and price_c is not None:
            if not (p["min_c"] <= price_c <= p["max_c"]):
                hit = f"price {price_c:g}c outside {p['min_c']}-{p['max_c']}c"
        elif kind == "block_hours" and when is not None:
            h = _hour_ct(when)
            if h in p["hours"]:
                hit = f"hour {h}:00 CT is blocked"
        elif kind == "max_legs" and legs is not None:
            if legs > p["n"]:
                hit = f"{legs} legs > max {p['n']}"
        elif kind == "max_stake_usd" and v.stake_usd is not None:
            if v.stake_usd > p["usd"]:
                v.reasons.append(f"stake capped ${v.stake_usd:.2f} -> ${p['usd']:.2f}")
                v.rule_ids.append(rid)
                v.stake_usd = float(p["usd"])
            continue
        if hit:
            v.allowed = False
            v.reasons.append(f"TEAM rule {rid}: {hit}")
            v.rule_ids.append(rid)
    return v


_cache: dict[str, Any] = {"mtime": None, "path": None, "data": None}
_lock = threading.Lock()


def _rules_path() -> Path:
    return Path(os.environ.get("TEAM_RULES_PATH") or DEFAULT_RULES)


def load_active() -> dict:
    """The approved ruleset, re-read only when the file changes."""
    path = _rules_path()
    with _lock:
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            return {"version": 0, "rules": []}
        if _cache["path"] != path or _cache["mtime"] != mtime:
            _cache.update(path=path, mtime=mtime,
                          data=json.loads(path.read_text(encoding="utf-8")))
        return _cache["data"]


def _log(entry: dict) -> None:
    try:
        GATE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with GATE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


def check(bot: str, *, price_c: float | None, stake_usd: float | None = None,
          legs: int | None = None, ticker: str = "", dry_run: bool = False) -> Verdict:
    """Gate one entry. Logs every decision that a rule touched."""
    try:
        active = load_active()
        v = evaluate(active.get("rules") or [], bot=bot, price_c=price_c,
                     stake_usd=stake_usd, legs=legs,
                     when=datetime.now(timezone.utc),
                     version=int(active.get("version") or 0))
    except Exception as exc:                            # noqa: BLE001
        logger.warning("TEAM gate unreadable, trading without rules: %s", exc)
        return Verdict(stake_usd=stake_usd)
    if v.rule_ids:
        _log({"ts": datetime.now(timezone.utc).isoformat(), "bot": bot,
              "ticker": ticker, "price_c": price_c, "stake_usd": stake_usd,
              "legs": legs, "allowed": v.allowed, "capped_to": v.stake_usd,
              "rules": v.rule_ids, "reasons": v.reasons,
              "ruleset_version": v.version, "dry_run": dry_run})
        logger.info("TEAM gate %s %s: %s", bot,
                    "allowed" if v.allowed else "BLOCKED", v.detail)
    return v
