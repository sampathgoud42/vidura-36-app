"""Reconcile the trade ledger against the exchange — two passes.

PASS 1 — settle stale OPEN rows.  A bot can miss its own close: it crashes
mid-exit, the market settles while it is between cycles, or a fire-sell fills
after the process is gone. The row then sits at ``open`` forever, its cost
counted and its P&L absent — and the CSV close-fallback may later invent a
sparse CLOSED row for it.

    stale open row  ->  is the ticker still an ACTIVE Kalshi position?
                        yes -> leave it alone, the bot is simply still in it
                        no  -> it resolved; take the true P&L from
                               fills + settlements and close the row

PASS 2 — fee-true-up of CLOSED rows.  Most bots book an ESTIMATE at close:
btc15 v4 charges the entry fee but takes the exit gross at the planned limit
price; btc60 books entry/exit cents with no fee at all.  Fees therefore
inflate profits and shrink losses on the ledger.  Every closed live row not
yet priced from the exchange is recomputed from fills + settlements — which
net fees out on both legs — and corrected when the booked figure differs.
Rows that already match (the sports bot books fee-true P&L itself) are
stamped ``raw['fee_checked']`` so they are never re-queried.

"True P&L" matters here. The bots' own ``realized_pnl`` estimates are the
figures a 2026-07-16 forensic pass found overstated by roughly $8k; fills and
settlements are what the account really did.

FILL SEMANTICS (decoded 2026-08-05 by joining fills to their orders): Kalshi
records every fill as the token the account ACQUIRED. A "sell yes" order is
held as NO bought at 1-price — the fill comes back ``side=no`` with the
complementary price — and vice versa. So every fill, buy or sell, is a cash
OUTFLOW of ``count x side_price + fee``, and each matched yes/no pair the
account accumulates auto-redeems for $1:

    pnl = -sum(count x fill_side_price + fee)
          + 1.00 x min(yes_acquired, no_acquired)      # pair redemptions
          + settlement revenue/100                      # whatever settled

That formula needs the market's WHOLE fill history (the pair count is a
conservation argument), so it applies when exactly one ledger row owns the
ticker. For shared tickers, the legacy windowed arithmetic
(sell -> +count x yes_price - fee, buy -> -count x yes_price - fee) is
provably equivalent per-leg — but ONLY for yes-held rows; validated on the
554-trade sports forensics, which is all yes. For a no-held row it inverts
the trade (that inversion shipped in every bot's TRUEPNL too), so shared-
ticker no rows are skipped rather than mis-booked.

Both passes stamp ``raw['reconciled']`` (or ``raw['fee_checked']``) and
``ingest.sync_trades`` refuses to overwrite stamped rows from CSVs — without
that lock the next 10s auto-sync would revert every correction to the bot's
own estimate.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Trade, User
from app.services import credentials, kalshi_client

logger = logging.getLogger(__name__)

# Every family whose rows live on the Kalshi account.
BOT_KEYS = ("btc15", "btc60", "btcperp", "sports", "parley", "gold15", "silver15", "oil15")

# A position younger than this is not suspicious — the bot is probably just
# holding it. The window is the whole point of the check: it separates "still
# running" from "nobody is coming back for this".
DEFAULT_STALE_HOURS = 24

# Fast reconcile: check open rows after this many minutes, retry every pass,
# and give up after MAX hours — marking the row "not_found".
FAST_STALE_MINUTES = 30
FAST_GIVE_UP_HOURS = 24

# Fee-true-up window: matches the widest P&L window the Bot Station renders
# (60D), so every figure on screen is exchange-priced.
TRUE_UP_DAYS = 60
# Per-run ceiling on rows needing exchange lookups (one fills call each).
# Stamped rows never re-query, so the backlog drains across a few syncs
# instead of blowing the sync button's 180s client timeout on the first one.
TRUE_UP_CAP = 150
# Booked vs exchange P&L closer than this is "the same number" (float dust).
_PNL_TOL = 0.005
# A ticker whose newest fill is younger than this is not finalized: the round
# may still be in flight and the pass's snapshots predate the fill.
RECENT_FILL_S = 600

# One reconcile pass per user at a time — the hourly loop and the sync button
# would otherwise double every exchange call and race each other's stamps.
_user_locks: dict[str, threading.Lock] = {}
_user_locks_guard = threading.Lock()


def _lock_for(user_id: str) -> threading.Lock:
    with _user_locks_guard:
        return _user_locks.setdefault(user_id, threading.Lock())


class ReconcileError(RuntimeError):
    """The exchange could not be reached, so nothing was decided."""


def stale_open(db: Session, user: User, *, hours: int = DEFAULT_STALE_HOURS) -> list[Trade]:
    """Live rows still ``open`` after ``hours``, newest first.

    Paper rows are excluded on purpose: they never reached the exchange, so
    Kalshi has no fills to price them with and "not an active position" would
    be true of every single one — reconciling them would zero the lot.
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    stmt = (
        select(Trade)
        .where(
            Trade.user_id == user.user_id,
            Trade.bot_key.in_(BOT_KEYS),
            Trade.status == "open",
            Trade.is_live.is_(True),
            Trade.opened_at < cutoff,
        )
        .order_by(Trade.opened_at.desc())
    )
    return list(db.scalars(stmt).all())


class FillsFlow:
    """Exact realized cash from ALL of a ticker's fills (see module doc).

    Each fill is an acquisition — cash out ``count x side_price + fee`` priced
    on the FILL's own side — and matched yes/no pairs auto-redeem for $1.
    The ledger row's side is irrelevant. Only valid over the market's whole
    fill history: the pair count is a conservation argument.

    ``open_qty`` is the unmatched remainder ``|yes - no|``: contracts that did
    NOT round-trip and must be explained by a settlement record. ``newest_ts``
    lets callers refuse to finalize a market that traded moments ago.
    """

    __slots__ = ("cash", "fees", "seen", "open_qty", "newest_ts")

    def __init__(self, client, ticker: str):
        cash = fees = yes_cnt = no_cnt = 0.0
        seen, newest = 0, 0.0
        for fx in client.fills(ticker=ticker, limit=1000):
            if ticker not in (fx.get("ticker"), fx.get("market_ticker")):
                continue
            cnt = float(fx.get("count_fp") or fx.get("count") or 0)
            s = (fx.get("side") or "yes").lower()
            px = float(fx.get("no_price_dollars" if s == "no" else "yes_price_dollars") or 0)
            fee = float(fx.get("fee_cost") or 0)
            cash -= cnt * px + fee
            fees += fee
            if s == "no":
                no_cnt += cnt
            else:
                yes_cnt += cnt
            seen += 1
            newest = max(newest, float(fx.get("ts") or 0))
        cash += min(yes_cnt, no_cnt)      # $1 auto-redemption per matched pair
        self.cash = round(cash, 2)
        self.fees = round(fees, 2)
        self.seen = seen
        self.open_qty = round(abs(yes_cnt - no_cnt), 4)
        self.newest_ts = newest


def _settlement_revenue(client, ticker: str, settlements: list[dict]) -> tuple[float, int]:
    rev, seen = 0.0, 0
    for s in settlements:
        if ticker in (s.get("ticker"), s.get("market_ticker"), s.get("event_ticker")):
            rev += float(s.get("revenue") or 0) / 100.0
            seen += 1
    return round(rev, 2), seen


def _stamped(t: Trade) -> bool:
    """Already priced (or checked) from the exchange — never re-query."""
    raw = t.raw if isinstance(t.raw, dict) else {}
    return bool(raw.get("reconciled") or raw.get("fee_checked"))


def closed_unverified(db: Session, user: User, *, days: int = TRUE_UP_DAYS) -> list[Trade]:
    """Closed live rows in the window whose P&L was never exchange-priced.

    Newest first, so a capped run trues up what the Bot Station is actually
    showing before it reaches into history.
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    stmt = (
        select(Trade)
        .where(
            Trade.user_id == user.user_id,
            Trade.bot_key.in_(BOT_KEYS),
            Trade.status.in_(("won", "lost", "closed", "settled")),
            Trade.is_live.is_(True),
            Trade.opened_at >= cutoff,
        )
        .order_by(Trade.opened_at.desc())
    )
    return [t for t in db.scalars(stmt).all() if not _stamped(t)]


def _live_ticker_counts(db: Session) -> dict[str, int]:
    """How many live ledger rows — ACROSS ALL USERS AND BOT KEYS — share each
    ticker.

    Fills are per Kalshi ACCOUNT, and shared credentials mean several users
    (or a manual trade) can produce fills on one market. The conservation
    formula is only safe when exactly one ledger row anywhere owns the
    ticker; everything else is attributed by subtraction or skipped.
    """
    stmt = select(Trade.ticker).where(Trade.is_live.is_(True))
    counts: dict[str, int] = {}
    for ticker in db.scalars(stmt).all():
        counts[ticker] = counts.get(ticker, 0) + 1
    return counts


def _ticker_rows(db: Session, ticker: str) -> list[Trade]:
    """Every live ledger row on this ticker, any user, any bot."""
    return list(db.scalars(
        select(Trade).where(Trade.is_live.is_(True), Trade.ticker == ticker)
    ).all())


def reconcile(
    db: Session,
    user: User,
    *,
    hours: int = DEFAULT_STALE_HOURS,
    dry_run: bool = True,
) -> dict:
    """Close stale open rows the exchange says are finished.

    Defaults to ``dry_run`` — this rewrites booked P&L, so producing the plan
    and applying it are separate decisions.
    """
    lock = _lock_for(user.user_id)
    if not lock.acquire(blocking=False):
        # The hourly loop and the sync button share this code; overlapping
        # passes would double every exchange call for zero benefit.
        return {"checked": 0, "active": 0, "resolved": [], "updated": 0,
                "dry_run": dry_run, "hours": hours, "busy": True,
                "true_up": {"candidates": 0, "checked": 0, "corrected": 0,
                            "confirmed": 0, "skipped": 0, "deferred": 0,
                            "rows": []}}
    try:
        return _reconcile_locked(db, user, hours=hours, dry_run=dry_run)
    finally:
        lock.release()


def _price_row(db: Session, client, settlements: list[dict], t: Trade,
               ticker_counts: dict[str, int], now_ts: float) -> tuple[str, dict]:
    """Price one ledger row from the exchange.

    Returns (verdict, info): ``no_record`` — nothing on the exchange;
    ``skip`` — cannot be finalized safely yet (info['reason']);
    ``priced`` — info has pnl/fees/n_fills/n_sett/note.
    """
    flow = FillsFlow(client, t.ticker)
    sett_rev, n_sett = _settlement_revenue(client, t.ticker, settlements)
    if flow.seen == 0 and n_sett == 0:
        return "no_record", {}
    if flow.newest_ts and now_ts - flow.newest_ts < RECENT_FILL_S:
        # The market traded moments ago: a round may still be in flight, and
        # the position/count snapshots predate this fill anyway.
        return "skip", {"reason": "fills in the last few minutes — in flight"}
    if flow.open_qty > 1e-6 and n_sett == 0:
        # Contracts that never round-tripped MUST be explained by a
        # settlement record. None yet = the market just closed (settlement
        # lags fills by minutes) or the position is still open beyond our
        # snapshot. Finalizing now would book a winner as a full loss.
        return "skip", {"reason": "unmatched contracts but no settlement record yet"}
    total = round(flow.cash + sett_rev, 2)
    if ticker_counts.get(t.ticker, 0) <= 1:
        return "priced", {"pnl": total, "fees": flow.fees,
                          "n_fills": flow.seen, "n_sett": n_sett,
                          "settlement_revenue": sett_rev, "note": "sole owner"}
    # Shared ticker (re-entry, another user on shared credentials, or a
    # manual trade): the account total is exact, so attribute by subtraction
    # when every sibling row already carries a booked figure.
    others = [r for r in _ticker_rows(db, t.ticker) if r.id != t.id]
    if others and all(r.pnl_usd is not None for r in others):
        pnl = round(total - sum(r.pnl_usd for r in others), 2)
        return "priced", {"pnl": pnl, "fees": None,
                          "n_fills": flow.seen, "n_sett": n_sett,
                          "settlement_revenue": sett_rev,
                          "note": f"account total {total} minus {len(others)} "
                                  f"booked sibling row(s)"}
    return "skip", {"reason": "shared ticker with unpriced sibling rows"}


def _reconcile_locked(
    db: Session,
    user: User,
    *,
    hours: int,
    dry_run: bool,
) -> dict:
    candidates = stale_open(db, user, hours=hours)
    unverified = closed_unverified(db, user, days=TRUE_UP_DAYS)
    if not candidates and not unverified:
        return {"checked": 0, "active": 0, "resolved": [], "updated": 0,
                "dry_run": dry_run, "hours": hours,
                "true_up": {"candidates": 0, "checked": 0, "corrected": 0,
                            "confirmed": 0, "skipped": 0, "deferred": 0,
                            "rows": []}}

    try:
        creds = credentials.load_kalshi_credentials(user.user_root_folder)
        client = kalshi_client.KalshiClient(
            creds.api_key_id, creds.private_key_path, creds.base_uri
        )
    except Exception as exc:                      # noqa: BLE001 - reported, not raised
        raise ReconcileError(f"cannot reach Kalshi: {exc}") from exc

    try:
        # One positions call for the whole sweep. A ticker with a non-zero
        # position is still live and is left strictly alone.
        active = {
            p.get("ticker") for p in client.positions(limit=1000)
            if int(p.get("position") or 0) != 0
        }
        # Settlements are account-wide and not ticker-filterable on this
        # client, so fetch once and match locally rather than per row.
        settlements = client.settlements(limit=1000)
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        now_iso = datetime.now(timezone.utc).isoformat()
        now_ts = datetime.now(timezone.utc).timestamp()
        ticker_counts = _live_ticker_counts(db)

        # ── pass 1: settle stale open rows ────────────────────────────────
        resolved, still_open = [], 0
        for t in candidates:
            if t.ticker in active:
                still_open += 1
                continue
            try:
                verdict, info = _price_row(db, client, settlements, t,
                                           ticker_counts, now_ts)
            except Exception as exc:              # noqa: BLE001 - row-scoped
                resolved.append({"id": t.id, "ticker": t.ticker,
                                 "action": "error", "reason": str(exc)[:200]})
                continue
            if verdict == "no_record":
                # No exchange record at all. Could be a paper row mislabelled
                # live, or a ticker outside this account's history. Refuse to
                # invent a $0 settlement for it.
                resolved.append({
                    "id": t.id, "ticker": t.ticker, "bot_key": t.bot_key,
                    "opened_at": str(t.opened_at), "action": "skipped",
                    "reason": "no fills or settlements on this ticker",
                })
                continue
            if verdict == "skip":
                resolved.append({
                    "id": t.id, "ticker": t.ticker, "bot_key": t.bot_key,
                    "opened_at": str(t.opened_at), "action": "skipped",
                    "reason": info["reason"],
                })
                continue
            pnl = info["pnl"]
            status = "won" if pnl > 0 else ("lost" if pnl < 0 else "closed")
            resolved.append({
                "id": t.id, "ticker": t.ticker, "bot_key": t.bot_key,
                "opened_at": str(t.opened_at),
                "old_status": t.status, "old_pnl": t.pnl_usd,
                "new_status": status, "new_pnl": pnl, "fees": info["fees"],
                "settlement_revenue": info["settlement_revenue"],
                "fills": info["n_fills"], "settlements": info["n_sett"],
                "note": info["note"],
                "action": "would_update" if dry_run else "updated",
            })
            if dry_run:
                continue
            t.status = status
            t.pnl_usd = pnl
            if info["fees"] is not None and info["n_fills"]:
                t.fees_usd = info["fees"]
            t.closed_at = now_naive
            # Stamped so this row is never mistaken for a bot-reported figure.
            raw = dict(t.raw or {})
            raw["reconciled"] = {
                "at": now_iso,
                "source": "kalshi fills+settlements",
                "fees": info["fees"],
                "settlement_revenue": info["settlement_revenue"],
                "note": info["note"],
                "replaced_status": "open",
            }
            t.raw = raw
            # Per-row commit: an exchange error later in the pass must not
            # discard finished corrections, and it shrinks the window in
            # which a concurrent CSV sync could overwrite an unstamped row.
            db.commit()

        # ── pass 2: fee-true-up of closed rows ────────────────────────────
        tu_rows: list[dict] = []
        tu_checked = tu_corrected = tu_confirmed = tu_skipped = 0
        deferred = 0
        for t in unverified:
            if tu_checked >= TRUE_UP_CAP:
                deferred += 1
                continue
            if t.ticker in active:
                tu_skipped += 1
                tu_rows.append({"id": t.id, "ticker": t.ticker,
                                "action": "skipped",
                                "reason": "position active again on this ticker"})
                continue
            try:
                verdict, info = _price_row(db, client, settlements, t,
                                           ticker_counts, now_ts)
            except Exception as exc:              # noqa: BLE001 - row-scoped
                tu_skipped += 1
                tu_rows.append({"id": t.id, "ticker": t.ticker,
                                "action": "error", "reason": str(exc)[:200]})
                continue
            tu_checked += 1
            if verdict == "no_record":
                # Beyond fills history, or never really traded. Stamp it so
                # the sweep does not re-query it every sync, change nothing.
                tu_skipped += 1
                tu_rows.append({"id": t.id, "ticker": t.ticker,
                                "action": "no_exchange_record"})
                if not dry_run:
                    raw = dict(t.raw or {})
                    raw["fee_checked"] = {"at": now_iso,
                                          "result": "no_exchange_record"}
                    t.raw = raw
                    db.commit()
                continue
            if verdict == "skip":
                tu_skipped += 1
                tu_rows.append({"id": t.id, "ticker": t.ticker,
                                "action": "skipped", "reason": info["reason"]})
                continue
            pnl = info["pnl"]
            old = t.pnl_usd
            if old is not None and abs(pnl - old) <= _PNL_TOL:
                # Booked figure already fee-true (sports books it this way).
                tu_confirmed += 1
                tu_rows.append({"id": t.id, "ticker": t.ticker, "pnl": pnl,
                                "fees": info["fees"], "action": "confirmed"})
                if not dry_run:
                    if t.fees_usd is None and info["fees"] is not None and info["n_fills"]:
                        t.fees_usd = info["fees"]
                    raw = dict(t.raw or {})
                    raw["fee_checked"] = {"at": now_iso, "pnl": pnl,
                                          "fees": info["fees"],
                                          "source": "kalshi fills+settlements"}
                    t.raw = raw
                    db.commit()
                continue
            status = "won" if pnl > 0 else ("lost" if pnl < 0 else "closed")
            tu_corrected += 1
            tu_rows.append({
                "id": t.id, "ticker": t.ticker, "bot_key": t.bot_key,
                "old_status": t.status, "old_pnl": old,
                "new_status": status, "new_pnl": pnl, "fees": info["fees"],
                "settlement_revenue": info["settlement_revenue"],
                "fills": info["n_fills"], "settlements": info["n_sett"],
                "note": info["note"],
                "action": "would_correct" if dry_run else "corrected",
            })
            if dry_run:
                continue
            t.pnl_usd = pnl
            t.status = status
            if info["fees"] is not None and info["n_fills"]:
                t.fees_usd = info["fees"]
            raw = dict(t.raw or {})
            raw["reconciled"] = {
                "at": now_iso,
                "source": "kalshi fills+settlements",
                "mode": "fee_true_up",
                "old_pnl": old,
                "fees": info["fees"],
                "settlement_revenue": info["settlement_revenue"],
                "note": info["note"],
            }
            t.raw = raw
            db.commit()
    finally:
        client.close()

    updated = sum(1 for r in resolved if r["action"] == "updated")
    logger.info(
        "reconcile: %s stale, %s still active, %s resolved, %s written; "
        "true-up: %s candidates, %s checked, %s corrected, %s confirmed, "
        "%s skipped, %s deferred",
        len(candidates), still_open, len(resolved), updated,
        len(unverified), tu_checked, tu_corrected, tu_confirmed,
        tu_skipped, deferred)
    return {
        "checked": len(candidates),
        "active": still_open,
        "resolved": resolved,
        "updated": updated,
        "dry_run": dry_run,
        "hours": hours,
        "true_up": {
            "candidates": len(unverified),
            "checked": tu_checked,
            "corrected": tu_corrected,
            "confirmed": tu_confirmed,
            "skipped": tu_skipped,
            "deferred": deferred,
            "rows": tu_rows,
        },
    }


# ── fast reconcile: aggressive 30-min check for unclosed positions ────────

def _fast_stale_open(db: Session, user: User, *, minutes: int = FAST_STALE_MINUTES) -> list[Trade]:
    """Live rows still ``open`` after ``minutes``, excluding rows already
    stamped ``reconciled`` or ``not_found``.
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes)
    stmt = (
        select(Trade)
        .where(
            Trade.user_id == user.user_id,
            Trade.bot_key.in_(BOT_KEYS),
            Trade.status == "open",
            Trade.is_live.is_(True),
            Trade.opened_at < cutoff,
        )
        .order_by(Trade.opened_at.desc())
    )
    rows = list(db.scalars(stmt).all())
    return [t for t in rows if not _stamped(t)]


def reconcile_fast(
    db: Session,
    user: User,
    *,
    minutes: int = FAST_STALE_MINUTES,
    give_up_hours: int = FAST_GIVE_UP_HOURS,
) -> dict:
    """Aggressively close open rows the exchange says are finished.

    Runs every 30 minutes and checks positions open longer than ``minutes``.
    For each open row:
      - If the ticker is still an active Kalshi position → leave it alone
      - If fills/settlements exist → close the row with true P&L
      - If no exchange record and the row is older than ``give_up_hours`` → mark "not_found"
      - Otherwise → log a retry attempt in raw and wait for the next pass
    """
    lock = _lock_for(user.user_id)
    if not lock.acquire(blocking=False):
        return {"checked": 0, "active": 0, "resolved": 0,
                "not_found": 0, "retried": 0, "busy": True}
    try:
        return _reconcile_fast_locked(db, user, minutes=minutes,
                                      give_up_hours=give_up_hours)
    finally:
        lock.release()


def _reconcile_fast_locked(
    db: Session,
    user: User,
    *,
    minutes: int,
    give_up_hours: int,
) -> dict:
    candidates = _fast_stale_open(db, user, minutes=minutes)
    if not candidates:
        return {"checked": 0, "active": 0, "resolved": 0,
                "not_found": 0, "retried": 0}

    try:
        creds = credentials.load_kalshi_credentials(user.user_root_folder)
        client = kalshi_client.KalshiClient(
            creds.api_key_id, creds.private_key_path, creds.base_uri
        )
    except Exception as exc:
        raise ReconcileError(f"cannot reach Kalshi: {exc}") from exc

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    now_iso = datetime.now(timezone.utc).isoformat()
    now_ts = datetime.now(timezone.utc).timestamp()
    give_up_cutoff = now_naive - timedelta(hours=give_up_hours)
    resolved = active = not_found = retried = 0

    try:
        active_tickers = {
            p.get("ticker") for p in client.positions(limit=1000)
            if int(p.get("position") or 0) != 0
        }
        settlements = client.settlements(limit=1000)
        ticker_counts = _live_ticker_counts(db)

        for t in candidates:
            if t.ticker in active_tickers:
                active += 1
                continue

            try:
                verdict, info = _price_row(db, client, settlements, t,
                                           ticker_counts, now_ts)
            except Exception:
                retried += 1
                continue

            if verdict == "priced":
                pnl = info["pnl"]
                status = "won" if pnl > 0 else ("lost" if pnl < 0 else "closed")
                t.status = status
                t.pnl_usd = pnl
                if info["fees"] is not None and info["n_fills"]:
                    t.fees_usd = info["fees"]
                t.closed_at = now_naive
                raw = dict(t.raw or {})
                raw["reconciled"] = {
                    "at": now_iso,
                    "source": "kalshi fills+settlements",
                    "mode": "fast_reconcile",
                    "fees": info["fees"],
                    "settlement_revenue": info["settlement_revenue"],
                    "note": info["note"],
                    "replaced_status": "open",
                }
                t.raw = raw
                db.commit()
                resolved += 1
                logger.info("fast-reconcile: closed %s as %s (pnl=%s)",
                            t.ticker, status, pnl)
                continue

            if t.opened_at < give_up_cutoff:
                t.status = "not_found"
                t.closed_at = now_naive
                raw = dict(t.raw or {})
                retries = raw.get("fast_reconcile_retries", 0)
                raw["reconciled"] = {
                    "at": now_iso,
                    "source": "fast_reconcile",
                    "mode": "give_up",
                    "retries": retries,
                    "reason": "open > 24h with no exchange record",
                    "replaced_status": "open",
                }
                t.raw = raw
                db.commit()
                not_found += 1
                logger.info("fast-reconcile: marked %s as not_found after %s retries",
                            t.ticker, retries)
                continue

            raw = dict(t.raw or {})
            retries = raw.get("fast_reconcile_retries", 0) + 1
            raw["fast_reconcile_retries"] = retries
            raw["fast_reconcile_last"] = now_iso
            t.raw = raw
            db.commit()
            retried += 1
            logger.debug("fast-reconcile: retry #%s for %s (verdict=%s)",
                         retries, t.ticker, verdict)
    finally:
        client.close()

    logger.info("fast-reconcile: %s candidates, %s active, %s resolved, "
                "%s not_found, %s retried",
                len(candidates), active, resolved, not_found, retried)
    return {"checked": len(candidates), "active": active,
            "resolved": resolved, "not_found": not_found, "retried": retried}
