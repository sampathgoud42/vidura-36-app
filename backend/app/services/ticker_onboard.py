"""Onboard a new ticker into a Super-Signals category.

A category is a folder of per-ticker research workers plus one entry each in
``super_research.config``. Everything a worker needs is already ticker-agnostic
— ``features.py`` and ``signals.py`` are byte-identical across every existing
ticker, and ``data.py`` reads the symbol from its folder's ``config.py`` — so
onboarding is: copy a donor folder from the same category, retarget its
``config.py``, register the ticker, then let the engines discover the playbook.

The donor matters. TP/SL, session windows and timezone differ per category
(ETFs run ±0.25%, stocks ±0.40%, India runs on IST), and copying a sibling
inherits exactly the right ones instead of inventing new defaults.

A brand-new ticker starts with an EMPTY A-book. The A-book is hand-curated
from a written backtest report; there is no honest way to synthesise one. Its
playbook therefore comes entirely from the B-book that ``iterate.py`` derives
from 60 days of real bars, run here as a background job — the same engine grid
(30m/1h/2h/4h × 5m/15m/30m) every other ticker uses.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services import super_research as svc

logger = logging.getLogger(__name__)

# Files a worker folder needs. The research/backtest scripts come too: the
# background job runs iterate.py, and a human may later re-run research.py.
TEMPLATE_FILES = (
    "data.py", "features.py", "signals.py", "backtest.py",
    "research.py", "iterate.py",
)

# yfinance symbols: letters, digits, and the . - ^ = separators used by
# suffixed listings (NIFTYBEES.NS, BTC-USD, ^GSPC). Anything else is either a
# typo or an attempt to steer the path below.
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-^=]{0,15}$")


class OnboardError(ValueError):
    """The request cannot produce a working ticker folder."""


def _slug(symbol: str) -> str:
    """spy / btc_usd / niftybees_ns — the folder + config id."""
    return re.sub(r"[^a-z0-9]+", "_", symbol.lower()).strip("_")


def _folder_for(category_key: str, donor_path: str, slug: str) -> str:
    """Mirror the donor's location, which is what tells India apart.

    India's workers live OUTSIDE super_research (``../NIFTY_research``) while
    every other category is a sibling folder, so the new ticker follows its
    category rather than a hardcoded rule.
    """
    prefix = "../" if donor_path.startswith("../") else ""
    stem = slug.upper() if prefix else slug
    return f"{prefix}{stem}_research"


def _retarget_config(text: str, donor_symbol: str, symbol: str) -> str:
    """Point the donor's config.py at the new symbol, leaving rules alone.

    Only the TICKER assignment and prose mentions change: TP_PCT, the session
    windows and the research grid are the category's calibration and must be
    inherited verbatim, not re-guessed per ticker.
    """
    out = re.sub(
        r'^TICKER\s*=\s*["\'][^"\']*["\']',
        f'TICKER = "{symbol}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if f'TICKER = "{symbol}"' not in out:
        raise OnboardError(f"donor config.py has no TICKER assignment to retarget")
    return out.replace(donor_symbol, symbol)


def _bot_shim(slug: str, symbol: str, category_key: str) -> str:
    return f'''#!/usr/bin/env python
"""
{slug}_intraday_bot.py — live {symbol} Super-Signal watcher (multi-engine).

Onboarded through the desk, so it starts with an EMPTY A-book: that list is
hand-curated from a written backtest report and cannot be invented. The live
playbook is the B-book in results/ensemble.csv, built by iterate.py from real
bars, scored across the same 30m/1h/2h/4h x 5m/15m/30m engine grid as every
other {category_key} ticker.

Usage:
    python {slug}_intraday_bot.py                 # live loop, poll 60s
    python {slug}_intraday_bot.py --once          # one scan of the latest bar
    python {slug}_intraday_bot.py --backfill-today
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))    # super_research/ -> engine_common
sys.path.insert(0, str(HERE))

import config as C             # noqa: E402
import data                    # noqa: E402
import features                # noqa: E402
import signals                 # noqa: E402
import engine_common           # noqa: E402

# A-book is earned, not scaffolded — see the module docstring.
A_BOOK: list[dict] = []

if __name__ == "__main__":
    engine_common.run_worker(HERE, "{slug}", C, data, features, signals, A_BOOK)
'''


def _bootstrap(slug: str) -> str:
    return f'''#!/usr/bin/env python
"""One-shot bootstrap for the freshly onboarded {slug} worker.

Builds the B-book from real bars, then emits everything today already fired so
the ticker shows up on the desk immediately instead of after the next session.
Runs detached; its output is _onboard.out beside this file.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def step(name, args):
    print(f"\\n=== {{name}} ===", flush=True)
    r = subprocess.run([sys.executable, *args], cwd=str(HERE))
    print(f"=== {{name}} exit {{r.returncode}} ===", flush=True)
    return r.returncode


# iterate.py downloads ~60 days of 5m bars and greedily unions the composites
# that clear its win-rate bar; that IS the playbook, so a failure here leaves
# the ticker registered but silent rather than emitting untested signals.
if step("iterate", ["iterate.py"]) == 0:
    step("backfill", ["{slug}_intraday_bot.py", "--backfill-today"])
else:
    print("iterate failed — no B-book, worker will stay quiet", flush=True)
'''


def _python() -> str:
    exe = str(get_settings().super_python)
    return exe if Path(exe).is_file() else sys.executable


def add_ticker(
    db: Session,
    category: str,
    symbol: str,
    label: str | None = None,
) -> dict:
    """Scaffold, register and bootstrap one ticker. Returns its config entry."""
    settings = get_settings()
    symbol = (symbol or "").strip().upper()
    category = (category or "").strip().lower()

    if not _SYMBOL.match(symbol):
        raise OnboardError(
            f"'{symbol}' is not a usable symbol — letters, digits and . - ^ = only"
        )

    cfg = svc.read_config()
    cats = cfg.get("categories") or {}
    cat = cats.get(category)
    if cat is None:
        raise OnboardError(
            f"unknown category '{category}' — have {', '.join(sorted(cats))}"
        )

    slug = _slug(symbol)
    for key, other in cats.items():
        for t in other.get("tickers") or []:
            if t.get("id") == slug:
                raise OnboardError(f"{symbol} is already in the {key} category")

    donors = cat.get("tickers") or []
    if not donors:
        raise OnboardError(
            f"category '{category}' has no existing ticker to copy its calibration from"
        )
    donor = donors[0]
    super_dir = Path(settings.super_dir)
    donor_dir = (super_dir / donor["path"]).resolve()
    if not donor_dir.is_dir():
        raise OnboardError(f"donor folder missing: {donor_dir}")

    rel = _folder_for(category, donor["path"], slug)
    dest = (super_dir / rel).resolve()
    # The slug is regex-constrained above, but resolve() is what actually
    # proves where the folder lands. It must be the donor's own sibling —
    # which is also why India (whose donors sit a level up, outside
    # super_research) is allowed without widening the rule for everyone.
    if dest.parent != donor_dir.parent:
        raise OnboardError(f"refusing to scaffold outside {donor_dir.parent}: {dest}")
    if dest.exists():
        raise OnboardError(f"folder already exists: {dest}")

    # ── scaffold ────────────────────────────────────────────────────────────
    dest.mkdir(parents=True)
    try:
        for name in TEMPLATE_FILES:
            src = donor_dir / name
            if src.is_file():
                shutil.copy2(src, dest / name)

        donor_cfg = donor_dir / "config.py"
        if not donor_cfg.is_file():
            raise OnboardError(f"donor has no config.py: {donor_cfg}")
        donor_symbol = _donor_symbol(donor_cfg)
        (dest / "config.py").write_text(
            _retarget_config(donor_cfg.read_text(encoding="utf-8"), donor_symbol, symbol),
            encoding="utf-8",
        )
        (dest / f"{slug}_intraday_bot.py").write_text(
            _bot_shim(slug, symbol, category), encoding="utf-8"
        )
        (dest / "_bootstrap.py").write_text(_bootstrap(slug), encoding="utf-8")
        (dest / "cache").mkdir(exist_ok=True)
        (dest / "results").mkdir(exist_ok=True)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)   # never leave a half folder
        raise

    # ── register ────────────────────────────────────────────────────────────
    entry = {
        "id": slug,
        "label": label or symbol,
        "path": rel,
        "csv": f"{slug}_intraday_signals.csv",
        "img": donor.get("img", "live-spy.webp"),
        "rules": donor.get("rules", ""),
        "enabled": True,
    }
    cat.setdefault("tickers", []).append(entry)
    _persist(db, cfg)

    # ── bootstrap ───────────────────────────────────────────────────────────
    entry["job"] = _launch_bootstrap(dest)
    logger.info("onboarded %s into %s at %s", symbol, category, dest)
    return {"ticker": entry, "category": category, "folder": str(dest)}


def _donor_symbol(donor_cfg: Path) -> str:
    m = re.search(
        r'^TICKER\s*=\s*["\']([^"\']+)["\']',
        donor_cfg.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if not m:
        raise OnboardError(f"donor config.py has no TICKER assignment: {donor_cfg}")
    return m.group(1)


def _persist(db: Session, cfg: dict) -> None:
    """Write the registry to the file AND the DB mirror, in that order.

    The supervisors read the file, the API serves the mirror; writing the file
    first means a failure there aborts before the desk starts advertising a
    ticker no supervisor will actually scan.
    """
    svc.config_path().write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    svc._upsert_singleton(db, "super_config", cfg, "api:addTicker")
    db.commit()
    svc.invalidate_caches()


def _launch_bootstrap(dest: Path) -> dict:
    """Detached: iterate.py pulls 60 days of bars, so this outlives the request."""
    out = dest / "_onboard.out"
    creationflags = 0
    if os.name == "nt":
        creationflags = 0x00000008 | subprocess.CREATE_NEW_PROCESS_GROUP  # DETACHED
    try:
        with open(out, "a", encoding="utf-8", errors="replace") as log_handle:
            proc = subprocess.Popen(
                [_python(), "_bootstrap.py"],
                cwd=str(dest),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                close_fds=True,
                creationflags=creationflags,
            )
    except OSError as exc:
        logger.warning("bootstrap launch failed for %s: %s", dest.name, exc)
        return {"pid": None, "log": str(out), "error": str(exc)}
    return {"pid": proc.pid, "log": str(out)}


def bootstrap_status(ticker_id: str) -> dict:
    """Progress of the background bootstrap: has the B-book landed yet?"""
    cfg = svc.read_config()
    for key, cat in (cfg.get("categories") or {}).items():
        for t in cat.get("tickers") or []:
            if t.get("id") == ticker_id:
                folder = (Path(get_settings().super_dir) / t["path"]).resolve()
                ensemble = folder / "results" / "ensemble.csv"
                log = folder / "_onboard.out"
                tail = ""
                if log.is_file():
                    tail = "\n".join(
                        log.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
                    )
                return {
                    "id": ticker_id,
                    "category": key,
                    "folder": str(folder),
                    "b_book_ready": ensemble.is_file() and ensemble.stat().st_size > 20,
                    "signals_csv": (folder / t["csv"]).is_file(),
                    "log_tail": tail,
                }
    raise OnboardError(f"unknown ticker '{ticker_id}'")
