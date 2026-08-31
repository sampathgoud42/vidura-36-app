"""Ingest bot-written trade CSVs into the unified SQLite trade ledger.

Each bot family writes its own CSV shape; this module maps them into the
``trades`` table.  Files remain bot-owned (read-only here) — ingest upserts
on a deterministic external_id so re-running is idempotent, and sports rows
that flip OPEN -> CLOSED in place update the stored row.

Caveat inherited from forensics (2026-07-16): legacy sports CSV
``realized_pnl`` before 07/16 is overstated ("phantom"); true P&L comes from
the Kalshi fills+settlements API.  Rows are stored as recorded with the full
original row preserved in ``raw``.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import paths
from app.core.config import get_settings
from app.models import Trade, User

logger = logging.getLogger(__name__)

_CST = ZoneInfo("America/Chicago")


def _parse_ts(value: str, fmts: tuple[str, ...], tz=_CST) -> datetime | None:
    value = (value or "").strip().replace(" CST", "").replace(" CDT", "")
    for fmt in fmts:
        try:
            # Stored naive-UTC to match the rest of the ledger.
            aware = datetime.strptime(value, fmt).replace(tzinfo=tz)
            return aware.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def _f(value, default=None) -> float | None:
    try:
        return float(str(value).replace("$", "").strip())
    except (TypeError, ValueError):
        return default


def _i(value, default=0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _read_rows(path: Path) -> list[dict]:
    """Tolerant DictReader: ragged extra columns land under '_extra'."""
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh, restkey="_extra")
            return [row for row in reader if any((v or "").strip() for v in row.values() if isinstance(v, str))]
    except OSError as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return []


def _dry(row: dict) -> bool | None:
    """The row's dry_run flag: True=paper, False=live, None=not recorded."""
    raw = (row.get("dry_run") or "").strip().upper()
    if raw in ("TRUE", "1", "YES"):
        return True
    if raw in ("FALSE", "0", "NO"):
        return False
    return None


def _clean_raw(row: dict) -> dict:
    return {str(k): (v if isinstance(v, (str, int, float, bool, list)) else str(v)) for k, v in row.items() if k}


# --- per-family row mappers -----------------------------------------------

def _map_btc15_v2(row: dict, version: str) -> dict | None:
    ticker = (row.get("ticker") or "").strip()
    if not ticker:
        return None
    opened = _parse_ts(row.get("timestamp", ""), ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"))
    pnl = _f(row.get("pnl"))
    status = "settled"
    if pnl is not None:
        status = "won" if pnl > 0 else ("lost" if pnl < 0 else "settled")
    return {
        "bot_key": "btc15",
        "bot_version": version,
        "external_id": f"btc15:{version}:{row.get('timestamp', '')}:{ticker}",
        "ticker": ticker,
        "side": (row.get("direction") or "").strip().lower() or None,
        "action": "buy",
        "contracts": _i(row.get("contracts")),
        "price_cents": _f(row.get("entry_price")),
        "pnl_usd": pnl,
        "status": status,
        # 'mode' above is the ENTRY STYLE (BUY/FLIP-BUY), never paper-vs-live.
        # The bot now records dry_run per row; rows written before that column
        # existed stay None (unknown) and are classified from the run that
        # produced them by _backfill_btc15_modes().
        "is_mock": _dry(row) is not False,
        "is_live": (None if _dry(row) is None else not _dry(row)),
        "opened_at": opened,
        "closed_at": opened,
        "raw": _clean_raw(row),
    }


def _map_btc15_v5(row: dict, bot_key: str = "btc15") -> dict | None:
    ticker = (row.get("ticker") or "").strip()
    if not ticker:
        return None
    action = (row.get("action") or "buy").strip().lower()
    opened = _parse_ts(row.get("timestamp_ct", ""), ("%m/%d/%Y %H:%M:%S",))
    ver = "v5" if bot_key == "btc15" else "v1"
    return {
        "bot_key": bot_key,
        "bot_version": ver,
        "external_id": f"{bot_key}:{ver}:{row.get('timestamp_ct', '')}:{ticker}:{action}",
        "ticker": ticker,
        "side": (row.get("side") or "").strip().lower() or None,
        "action": action if action in ("buy", "sell") else "buy",
        "contracts": _i(row.get("contracts")),
        "price_cents": _f(row.get("price_cents")),
        "status": "closed" if action == "sell" else "open",
        "is_mock": (row.get("dry_run") or "").strip().upper() in ("TRUE", "1", "YES"),
        "is_live": (row.get("dry_run") or "").strip().upper() not in ("TRUE", "1", "YES"),
        "opened_at": opened,
        "raw": _clean_raw(row),
    }


def _map_btc60(row: dict, version: str, *, is_paper: bool) -> dict | None:
    ticker = (row.get("ticker") or "").strip()
    if not ticker:
        return None
    opened = _parse_ts(
        row.get("timestamp", ""),
        ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"),
        tz=timezone.utc,
    )
    pnl = _f(row.get("pnl_dollars"))
    status = "settled"
    if pnl is not None:
        status = "won" if pnl > 0 else ("lost" if pnl < 0 else "settled")
    entry = _f(row.get("entry_cents"))
    contracts = _i(row.get("contracts"))
    return {
        "bot_key": "btc60",
        "bot_version": version,
        "external_id": f"btc60:{version}:{row.get('timestamp', '')}:{ticker}",
        "ticker": ticker,
        "side": (row.get("side") or "").strip().lower() or None,
        "action": "buy",
        "contracts": contracts,
        "price_cents": entry,
        "cost_usd": round(entry * contracts / 100, 2) if entry is not None else None,
        "pnl_usd": pnl,
        "status": status,
        "is_mock": is_paper,
        "is_live": not is_paper,
        "opened_at": opened,
        "closed_at": opened,
        "raw": _clean_raw(row),
    }


def _map_sports(row: dict, *, is_paper: bool, source: str, bot_key: str = "sports") -> dict | None:
    ticker = (row.get("ticker") or "").strip()
    ts_epoch = (row.get("ts_epoch") or "").strip()
    if not ticker or not ts_epoch:
        return None
    opened = None
    epoch = _f(ts_epoch)
    if epoch:
        opened = datetime.fromtimestamp(epoch, tz=timezone.utc).replace(tzinfo=None)
    status_raw = (row.get("status") or "").strip().upper()
    pnl = _f(row.get("realized_pnl"))
    if status_raw == "OPEN":
        status = "open"
    elif pnl is not None and pnl != 0:
        status = "won" if pnl > 0 else "lost"
    else:
        status = "closed"
    closed = (
        _parse_ts(
            row.get("ts_close", ""),
            ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"),
        )
        if status != "open"
        else None
    )
    fill = _f(row.get("fill_price")) or _f(row.get("buy_price"))
    contracts = _i(row.get("contracts"))
    return {
        "bot_key": bot_key,
        "bot_version": source,
        # ts_epoch is the bots' row key, but real ledgers contain duplicate
        # ts_epoch values for distinct trades, so ticker joins the key and
        # sync_trades adds an occurrence suffix for exact repeats. The key
        # must NOT include the source tag: the same ledger can be visible
        # under two filenames (trade_history.csv vs trade_history_sports.csv).
        # It IS keyed by bot, though — the parlay bot writes the same row
        # shape from a separate ledger, and one key space would let the two
        # collide on a shared timestamp.
        "external_id": f"{bot_key}:{ts_epoch}:{ticker}",
        "ticker": ticker,
        "market_title": (row.get("name") or row.get("player") or row.get("team") or "").strip() or None,
        "side": "yes",  # sports bots only ever buy YES
        "action": "buy",
        "contracts": contracts,
        "price_cents": fill,
        "cost_usd": round(fill * contracts / 100, 2) if fill is not None else None,
        "pnl_usd": pnl,
        "status": status,
        "is_mock": is_paper,
        "is_live": not is_paper,
        "opened_at": opened,
        "closed_at": closed,
        "raw": _clean_raw(row),
    }


# --- file discovery + upsert ----------------------------------------------

def _candidate_files(user: User, bot_key: str) -> list[tuple[Path, str]]:
    """Return (file, parser_tag) pairs that may exist for this user/bot."""
    root = paths.normalize_root(user.user_root_folder)
    trade_dir = root / "trade_history"
    out: list[tuple[Path, str]] = []
    if bot_key == "btc15":
        for ver in ("v2", "v3", "v4"):
            out.append((trade_dir / f"{ver}_trade_history.csv", f"btc15_{ver}"))
        out.append((root / f"v2_trade_history.csv", "btc15_v2"))
        out.append((trade_dir / "bot_btc_15_2_trades.csv", "btc15_v5"))
        out.append((root / "bot_btc_15_2_trades.csv", "btc15_v5"))
    elif bot_key == "btc60":
        # btc60 writes next to its script (shared across users by design).
        btc60_dir = get_settings().source_repo / "prediction-trade/kalshi/btc/btc60"
        for ver in ("fable5", "burst"):
            out.append((btc60_dir / f"btc60_{ver}_trade_history_paper.csv", f"btc60_{ver}_paper"))
            out.append((btc60_dir / f"btc60_{ver}_trade_history.csv", f"btc60_{ver}_live"))
    elif bot_key == "sports":
        out.append((trade_dir / "trade_history_main.csv", "sports_main_live"))
        out.append((trade_dir / "paper_trades_main.csv", "sports_main_paper"))
        out.append((trade_dir / "trade_history_sports.csv", "sports_v1_live"))
        out.append((trade_dir / "trade_history.csv", "sports_v1_live"))
        out.append((trade_dir / "trade_history_baseball.csv", "sports_v2_live"))
    elif bot_key == "parley":
        # Same row shape as the sports bots (it writes through their engine),
        # from its own pair of ledgers — paper and live never share a file.
        out.append((trade_dir / "trade_history_parley.csv", "parley_v1_live"))
        out.append((trade_dir / "paper_parley.csv", "parley_v1_paper"))
    elif bot_key == "gold15":
        out.append((trade_dir / "bot_gold15_trades.csv", "gold15_v1"))
        out.append((root / "bot_gold15_trades.csv", "gold15_v1"))
    elif bot_key == "silver15":
        out.append((trade_dir / "bot_silver15_trades.csv", "silver15_v1"))
        out.append((root / "bot_silver15_trades.csv", "silver15_v1"))
    elif bot_key == "oil15":
        out.append((trade_dir / "bot_oil15_trades.csv", "oil15_v1"))
        out.append((root / "bot_oil15_trades.csv", "oil15_v1"))
    return [(p, tag) for p, tag in out if p.is_file()]


def _map_row(tag: str, row: dict) -> dict | None:
    if tag.startswith("btc15_v5"):
        return _map_btc15_v5(row)
    if tag.startswith("btc15_"):
        return _map_btc15_v2(row, tag.split("_")[1])
    if tag.startswith("btc60_"):
        _, version, mode = tag.split("_")
        return _map_btc60(row, version, is_paper=(mode == "paper"))
    if tag.startswith("sports_"):
        _, source, mode = tag.split("_")
        return _map_sports(row, is_paper=(mode == "paper"), source=source)
    if tag.startswith("parley_"):
        _, source, mode = tag.split("_")
        return _map_sports(row, is_paper=(mode == "paper"), source=source,
                           bot_key="parley")
    if tag.startswith("gold15_"):
        return _map_btc15_v5(row, bot_key="gold15")
    if tag.startswith("silver15_"):
        return _map_btc15_v5(row, bot_key="silver15")
    if tag.startswith("oil15_"):
        return _map_btc15_v5(row, bot_key="oil15")
    return None


def _classify_btc15_modes(db: Session) -> int:
    """Run-window mode classification, at SYNC time rather than only at boot.

    btc15 v2/v3/v4 write paper and live rows to one CSV with no dry_run
    field, so they ingest with is_live NULL — and the LIVE ledger view hides
    NULL by design. The boot backfill classified them from bot_run windows,
    but rows ingested while the API stays up sat unclassified until the next
    restart: a whole day of live trades invisible in the default view.
    """
    from app.core.database import _backfill_btc15_modes

    fixed = _backfill_btc15_modes(db.connection())
    if fixed:
        db.commit()
        logger.info("classified %s btc15 row(s) from their run windows", fixed)
    return fixed


def sync_trades(db: Session, user: User, bot_key: str) -> dict:
    """Idempotent CSV -> SQLite sync. Returns counts per file."""
    report: dict[str, dict] = {}
    inserted = updated = 0
    for path, tag in _candidate_files(user, bot_key):
        rows = _read_rows(path)
        file_ins = file_upd = 0
        # Pre-merge rows sharing an external_id: the legacy close-fallback
        # appends a sparse duplicate CLOSED row (pnl 0.0) for a trade it
        # could not match — same trade, artifact row. Meaningful-value-wins.
        merged: dict[str, dict] = {}
        for row in rows:
            mapped = _map_row(tag, row)
            if mapped is None:
                continue
            key = mapped["external_id"]
            kept = merged.get(key)
            if kept is None:
                merged[key] = mapped
                continue
            for field, value in mapped.items():
                if value is None:
                    continue
                if field == "pnl_usd" and value == 0 and kept.get("pnl_usd"):
                    continue  # sparse row must not zero out a real P&L
                if field == "status" and value in ("closed", "open") and kept.get("status") in ("won", "lost"):
                    continue  # never downgrade a settled outcome
                kept[field] = value
        for mapped in merged.values():
            existing = db.scalar(
                select(Trade).where(
                    Trade.user_id == user.user_id,
                    Trade.external_id == mapped["external_id"],
                )
            )
            if existing is None:
                if mapped.get("opened_at") is None:
                    mapped.pop("opened_at", None)
                db.add(Trade(user_id=user.user_id, **mapped))
                file_ins += 1
            else:
                # Sports CSVs update rows in place (OPEN -> CLOSED). Never
                # downgrade a settled row back to open — a stale copy of the
                # same ledger under another filename must not erase P&L.
                if mapped.get("status") == "open" and existing.status != "open":
                    continue
                # Exchange-priced rows are locked: reconcile stamped them from
                # fills+settlements (fee-true), and the bot's own CSV estimate
                # must not claw the figure back on the next auto-sync.
                existing_raw = existing.raw if isinstance(existing.raw, dict) else {}
                locked = bool(existing_raw.get("reconciled") or existing_raw.get("fee_checked"))
                changed = False
                for field in ("status", "pnl_usd", "closed_at", "price_cents", "cost_usd", "raw"):
                    new = mapped.get(field)
                    if new is None or getattr(existing, field) == new:
                        continue
                    if locked and field in ("status", "pnl_usd", "raw"):
                        continue
                    # Same sparse-row guards as the in-file merge above.
                    if field == "pnl_usd" and new == 0 and existing.pnl_usd:
                        continue
                    if field == "status" and new in ("closed", "open") and existing.status in ("won", "lost"):
                        continue
                    setattr(existing, field, new)
                    changed = True
                if changed:
                    file_upd += 1
        db.commit()
        inserted += file_ins
        updated += file_upd
        report[str(path)] = {"rows": len(rows), "inserted": file_ins, "updated": file_upd}
    if bot_key == "btc15":
        _classify_btc15_modes(db)
    return {"bot_key": bot_key, "inserted": inserted, "updated": updated, "files": report}


# --- automatic sync --------------------------------------------------------
# The bots own their trade CSVs; the DB is a mirror. Until this existed the
# mirror was only refreshed by POST /sync-trades — i.e. when a human clicked
# "Sync from bot CSVs" — so a live position could be open for hours while the
# desk showed an empty Active Bets panel (observed 2026-07-29 with a resting
# tennis position). Read endpoints now refresh first.
#
# The CSVs are a few KB, so a sync is cheap, but the UI polls every few
# seconds: a TTL keeps that from re-parsing on every request, and a lock
# keeps two concurrent readers from double-inserting.

_AUTO_TTL_S = 10.0
_last_sync: dict[tuple[str, str], float] = {}
_auto_lock = Lock()


def is_user_scoped(user: User, bot_key: str) -> bool:
    """True when every CSV for this bot lives inside the user's own folder.

    btc60 writes its history next to its script, shared across users by
    design. Mirroring that automatically would attribute one shared ledger to
    whichever user happened to open the page — so it stays opt-in via the
    explicit sync endpoint.
    """
    root = paths.normalize_root(user.user_root_folder).resolve()
    for path, _tag in _candidate_files(user, bot_key):
        try:
            path.resolve().relative_to(root)
        except ValueError:
            return False
    return True


def auto_sync(db: Session, user: User, bot_key: str, *, ttl: float = _AUTO_TTL_S) -> bool:
    """Refresh this user/bot's trades from CSV if the last pass is stale.

    Returns True if a sync ran. Never raises: a read endpoint must still
    answer from the DB when the CSVs are missing, locked or malformed.
    """
    if not get_settings().trades_auto_sync:
        return False
    if not is_user_scoped(user, bot_key):
        return False
    key = (user.user_id, bot_key)
    now = monotonic()
    with _auto_lock:
        if now - _last_sync.get(key, 0.0) < ttl:
            return False
        _last_sync[key] = now  # claim the slot before the slow part
    try:
        sync_trades(db, user, bot_key)
        return True
    except Exception as exc:
        logger.warning("auto-sync failed for %s/%s: %s", user.username, bot_key, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return False
