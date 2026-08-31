"""Read and change the TP/SL race targets the signal engines are scored at.

Every ticker folder carries its own ``config.py`` with ``TP_PCT`` / ``SL_PCT``
— the percentage move a signal must make before it makes the opposite move.
It is the single number that decides what counts as a win, so every engine
score, every playbook filter and every emitted target/stop price is derived
from it (``engine_common.scan`` builds target_price/stop_price straight off
``C.TP_PCT`` / ``C.SL_PCT``).

Categories are calibrated as a group — ETFs run ±0.25%, stocks ±0.40%, because
a 0.25% move means something different on SPY than on TSLA — so this reads and
writes a category at a time, which is also how the desk presents it.

Changing it is safe with respect to the scoring cache: ``score_pairs`` keys
``results/engine_scores.json`` on a fingerprint that includes tp/sl, so the
next run re-scores at the new targets rather than serving numbers earned at
the old ones. What does NOT reset is the candidate set: ``results/ensemble.csv``
was selected by ``iterate.py`` at the previous target. Those candidates are
re-validated at the new target before going live (``build_engine_playbooks``
drops anything that no longer clears the floor), but discovering candidates
that only work at the NEW target needs a regenerate. Callers are told so.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services import super_research as svc

logger = logging.getLogger(__name__)

# A race target below this is inside the spread on most of these names, and
# above it the "intraday" horizon stops being reachable within 4 hours.
MIN_PCT, MAX_PCT = 0.05, 5.0

_ASSIGN = {
    "TP_PCT": re.compile(r"^TP_PCT\s*=\s*[0-9.]+.*$", re.MULTILINE),
    "SL_PCT": re.compile(r"^SL_PCT\s*=\s*[0-9.]+.*$", re.MULTILINE),
}
_READ = {
    "TP_PCT": re.compile(r"^TP_PCT\s*=\s*([0-9.]+)", re.MULTILINE),
    "SL_PCT": re.compile(r"^SL_PCT\s*=\s*([0-9.]+)", re.MULTILINE),
}


class PctError(ValueError):
    """The requested target cannot be applied."""


def _config_for(ticker: dict) -> Path:
    return (Path(get_settings().super_dir) / ticker["path"] / "config.py").resolve()


def _read_one(path: Path) -> dict | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    out = {}
    for key, rx in _READ.items():
        m = rx.search(text)
        if m is None:
            return None
        out[key.lower()] = float(m.group(1))
    return out


def read_all() -> dict:
    """Per-category race targets, plus the per-ticker values behind them.

    ``mixed`` is reported rather than averaged away: a category whose tickers
    disagree is a real state (someone edited one folder by hand), and showing
    a single tidy number for it would hide that.
    """
    cfg = svc.read_config()
    cats: dict[str, dict] = {}
    for key, cat in (cfg.get("categories") or {}).items():
        per: dict[str, dict] = {}
        for t in cat.get("tickers") or []:
            got = _read_one(_config_for(t))
            if got:
                per[t["id"]] = got
        tps = {v["tp_pct"] for v in per.values()}
        sls = {v["sl_pct"] for v in per.values()}
        cats[key] = {
            "label": cat.get("label", key),
            "tp_pct": next(iter(tps)) if len(tps) == 1 else None,
            "sl_pct": next(iter(sls)) if len(sls) == 1 else None,
            "mixed": len(tps) > 1 or len(sls) > 1,
            "tickers": per,
        }
    return {"categories": cats}


def write_category(db: Session, category: str, tp_pct: float,
                   sl_pct: float | None = None) -> dict:
    """Retarget every ticker in one category. Returns what changed.

    Writes each folder's ``config.py`` and refreshes the category's ``rules``
    display string, because that string is what the desk shows and it would
    otherwise keep advertising the old percentage.
    """
    category = (category or "").strip().lower()
    sl_pct = tp_pct if sl_pct is None else sl_pct
    for name, value in (("TP", tp_pct), ("SL", sl_pct)):
        if not isinstance(value, (int, float)) or not (MIN_PCT <= float(value) <= MAX_PCT):
            raise PctError(f"{name} {value} is outside {MIN_PCT}–{MAX_PCT}%")
    tp_pct, sl_pct = round(float(tp_pct), 3), round(float(sl_pct), 3)

    cfg = svc.read_config()
    cat = (cfg.get("categories") or {}).get(category)
    if cat is None:
        raise PctError(f"unknown category '{category}'")

    changed, missing = [], []
    for t in cat.get("tickers") or []:
        path = _config_for(t)
        if not path.is_file():
            missing.append(t["id"])
            continue
        text = path.read_text(encoding="utf-8")
        new = _ASSIGN["TP_PCT"].sub(
            f"TP_PCT = {tp_pct:g}                # +{tp_pct:.2f}% target", text, count=1)
        new = _ASSIGN["SL_PCT"].sub(
            f"SL_PCT = {sl_pct:g}                # {sl_pct:.2f}% adverse stop", new, count=1)
        if new == text:
            missing.append(t["id"])       # no assignment matched — do not guess
            continue
        path.write_text(new, encoding="utf-8")
        changed.append(t["id"])

    if not changed:
        raise PctError(
            f"no config.py in '{category}' had TP_PCT/SL_PCT to rewrite ({', '.join(missing) or 'none found'})"
        )

    _retarget_rules(cat, tp_pct, sl_pct)
    svc.config_path().write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    svc._upsert_singleton(db, "super_config", cfg, "api:setEnginePct")
    db.commit()
    svc.invalidate_caches()

    logger.info("engine target for %s -> tp %s / sl %s (%s)",
                category, tp_pct, sl_pct, ", ".join(changed))
    return {
        "category": category,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "updated": changed,
        "skipped": missing,
        # said plainly because it is the difference between "scored at the new
        # target" (automatic) and "discovered at the new target" (not)
        "note": (
            "Engine scores re-compute at the new target on the next scan — that cache "
            "is fingerprinted on tp/sl. The B-book candidates were still discovered at "
            "the old target and are only re-validated, not re-found; run REGENERATE "
            "ENGINES to search for setups that suit the new one."
        ),
    }


# --- A/B admission gates ---------------------------------------------------
#
# These decide whether a scored config produces a signal at all, and which
# book it lands in. Unlike TP/SL they are module-level globals in
# engine_common.py — ONE pair of numbers shared by every ticker in every
# category — so they are read and written desk-wide rather than per category.
# Presenting them per-category would imply an independence the engine does
# not have.

_GATES = {
    "b_tpsl": (
        re.compile(r"^MIN_TPSL\s*=\s*[0-9.]+.*$", re.MULTILINE),
        re.compile(r"^MIN_TPSL\s*=\s*([0-9.]+)", re.MULTILINE),
        "MIN_TPSL = {v:<19}# tp-before-sl % a config needs to stay live",
    ),
    "a_tpsl": (
        re.compile(r"^A_TPSL\s*=\s*[0-9.]+.*$", re.MULTILINE),
        re.compile(r"^A_TPSL\s*=\s*([0-9.]+)", re.MULTILINE),
        "A_TPSL = {v:<21}# tp-before-sl > this = A-book on that pair",
    ),
}


def _engine_common() -> Path:
    return (Path(get_settings().super_dir) / "engine_common.py").resolve()


def read_gates() -> dict:
    """The desk-wide A-book / B-book admission thresholds."""
    path = _engine_common()
    if not path.is_file():
        raise PctError(f"engine_common.py not found at {path}")
    text = path.read_text(encoding="utf-8")
    out = {}
    for key, (_sub, rx, _fmt) in _GATES.items():
        m = rx.search(text)
        if m is None:
            raise PctError(f"engine_common.py has no {key.upper()} assignment")
        out[key] = float(m.group(1))
    out["scope"] = "all categories"
    return out


def write_gates(a_tpsl: float, b_tpsl: float) -> dict:
    """Set the A-book and B-book tp-before-sl floors.

    ``b_tpsl`` is the floor to stay live at all; ``a_tpsl`` promotes to
    A-book. A below B is rejected rather than clamped: it would make every
    live config an A-book signal, which is not a stricter setting than the
    user asked for but a silently much looser one.
    """
    for name, value in (("A", a_tpsl), ("B", b_tpsl)):
        if not isinstance(value, (int, float)) or not (50.0 <= float(value) <= 100.0):
            raise PctError(f"{name} gate {value} is outside 50–100%")
    a_tpsl, b_tpsl = round(float(a_tpsl), 2), round(float(b_tpsl), 2)
    if a_tpsl < b_tpsl:
        raise PctError(
            f"A gate {a_tpsl}% is below the B floor {b_tpsl}% — that would make every "
            "live signal an A-book signal"
        )

    path = _engine_common()
    text = original = path.read_text(encoding="utf-8")
    for key, value in (("a_tpsl", a_tpsl), ("b_tpsl", b_tpsl)):
        sub, _rx, fmt = _GATES[key]
        # one decimal, matching the file's own style: %g would write 88
        # where the module had 85.0, quietly changing a float literal to an int
        text = sub.sub(fmt.format(v=f"{value:.1f}"), text, count=1)
    if text == original:
        raise PctError("no A_TPSL/MIN_TPSL assignment matched — engine_common.py changed shape")
    path.write_text(text, encoding="utf-8")

    logger.info("engine gates -> A %s / B %s", a_tpsl, b_tpsl)
    return {
        "a_tpsl": a_tpsl,
        "b_tpsl": b_tpsl,
        # unlike TP/SL this needs no re-scoring: the gates are applied to the
        # cached scores every scan, they are not baked into them
        "note": (
            "Applied on the next scan. These gates filter the already-computed engine "
            "scores, so nothing has to be re-scored — but a regenerate re-emits today's "
            "signals under the new gates instead of waiting for the next bar."
        ),
    }


def _retarget_rules(cat: dict, tp_pct: float, sl_pct: float) -> None:
    """Keep the human-readable rules line honest about the new numbers."""
    tp_rx = re.compile(r"TP ±[0-9.]+%")
    sl_rx = re.compile(r"SL [0-9.]+%")
    for t in cat.get("tickers") or []:
        rules = t.get("rules") or ""
        if not rules:
            continue
        rules = tp_rx.sub(f"TP ±{tp_pct:.2f}%", rules)
        rules = sl_rx.sub(f"SL {sl_pct:.2f}%", rules)
        t["rules"] = rules
