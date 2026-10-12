"""The 15M Combo, built and placed by itself every quarter hour.

While an operator has it on, at :05, :20, :35 and :50 Chicago time -- five
minutes into each fifteen-minute market -- one combo is built and placed in
the background, with nobody there to confirm it:

  1. build  combo15.preview: every fifteen-minute market the collection
            hosts, and the legs that pass its DMI validation (the ones the
            15M COMBO sheet ticks by default: DMI fresh, CALL or PUT, bid
            35-90c, at most 5c wide, more than a minute left);
  2. pick   past MAX_LEGS of them, a random MAX_LEGS; fewer than two, the
            slot is skipped -- a combo takes two or more;
  3. judge  the combo's chance of winning, the product of its legs' bids --
            the sheet's own "chance" -- must lie within MIN_CHANCE..MAX_CHANCE.
            Past MAX_LEGS legs a few other random picks are tried for one that
            does; none, and the slot is skipped;
  4. place  combo15.place at a stake of MIN_USD..MAX_USD, at random to the
            cent, once the combo shards (0 and 1) hold at least MAX_USD.
  5. settle once the combo market resolves, its outcome -- won, lost or void,
            with Kalshi's settlement P&L -- goes in combo15_auto_result
            (settle_all_tenants, at most every SETTLE_EVERY_S).

Each slot is claimed by writing its row FIRST, unique per (operator, slot), as
the Luck schedule does: a slot runs once, across loop passes and restarts. A
run a restart cut off is marked interrupted and never repeated -- repeating a
placement could buy the combo twice.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

TZ = ZoneInfo("America/Chicago")
# Minutes past each hour: five minutes into each fifteen-minute market.
MINUTES = (5, 20, 35, 50)
# A slot the loop did not see on time still runs up to this long after it;
# later, the quarter is too far gone for a combo built for it.
GRACE_S = 4 * 60
POLL_S = 20
STALE_RUN_S = 15 * 60
MAX_LEGS = 5
MIN_CHANCE, MAX_CHANCE = 0.11, 0.51
MIN_USD, MAX_USD = 1.0, 1.5
# Past MAX_LEGS legs, how many random picks are tried for one in the chance band.
PICK_TRIES = 25
# Settling asks Kalshi about every unresolved combo, so not on every pass.
SETTLE_EVERY_S = 60
# A combo resolves within its quarter; past this one still unresolved is
# given up on rather than asked about forever.
SETTLE_GIVE_UP_S = 3 * 24 * 3600
# Market resolved but no settlement row yet: wait this long for one before
# recording the result without a P&L.
SETTLEMENT_WAIT_S = 2 * 3600
_last_settle = 0.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _naive_utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def _slot_at(local: datetime) -> datetime | None:
    """The slot moment at or before ``local`` within GRACE_S, else None."""
    for minute in MINUTES:
        at = local.replace(minute=minute, second=0, microsecond=0)
        if at <= local < at + timedelta(seconds=GRACE_S):
            return at
    return None


def due_slot(now: datetime | None = None) -> str | None:
    """The slot due now, "2026-10-12 10:05" -- or None."""
    at = _slot_at((now or _now()).astimezone(TZ))
    return at.strftime("%Y-%m-%d %H:%M") if at else None


def next_slot(now: datetime | None = None) -> datetime:
    """When the next slot starts, in UTC."""
    local = (now or _now()).astimezone(TZ)
    for hours in (0, 1):
        base = local + timedelta(hours=hours)
        for minute in MINUTES:
            at = base.replace(minute=minute, second=0, microsecond=0)
            if at > local:
                return at.astimezone(timezone.utc)
    return local.astimezone(timezone.utc)            # unreachable


def chance(legs: list[dict]) -> float:
    """A combo's chance of winning on the bids: every leg must land."""
    out = 1.0
    for leg in legs:
        out *= (leg.get("bid_c") or 0) / 100
    return out


def pick(legs: list[dict], rng=random) -> tuple[list[dict] | None, str]:
    """The legs to buy, and why when there are none."""
    if len(legs) < 2:
        return None, f"{len(legs)} leg{'s' if len(legs) != 1 else ''} pass the DMI validation -- a combo takes 2"
    if len(legs) <= MAX_LEGS:
        tries = [legs]
    else:
        tries = [rng.sample(legs, MAX_LEGS) for _ in range(PICK_TRIES)]
    for chosen in tries:
        if MIN_CHANCE <= chance(chosen) <= MAX_CHANCE:
            return chosen, ""
    best = chance(tries[0])
    return None, (f"chance {best * 100:.1f}% is outside {MIN_CHANCE * 100:g}-{MAX_CHANCE * 100:g}%"
                  + (f" (and in {PICK_TRIES} random picks of {MAX_LEGS} from {len(legs)})"
                     if len(legs) > MAX_LEGS else ""))


def _serialize_run(row, outcome=None) -> dict:
    def stamp(moment):
        return moment.replace(tzinfo=timezone.utc).isoformat() if moment else None
    return {"slot": row.slot, "status": row.status, "detail": row.detail, "legs": row.legs,
            "chance_pct": row.chance_pct, "stake_usd": row.stake_usd,
            "cost_usd": row.cost_usd, "combo_ticker": row.combo_ticker,
            "started_at": stamp(row.created_at), "finished_at": stamp(row.finished_at),
            "result": outcome.result if outcome else None,
            "pnl_usd": outcome.pnl_usd if outcome else None,
            "payout_usd": outcome.payout_usd if outcome else None,
            "settled_at": stamp(outcome.settled_at) if outcome else None}


def rule() -> dict:
    return {"minutes": list(MINUTES), "tz": "America/Chicago", "max_legs": MAX_LEGS,
            "min_chance_pct": round(MIN_CHANCE * 100, 2), "max_chance_pct": round(MAX_CHANCE * 100, 2),
            "min_usd": MIN_USD, "max_usd": MAX_USD}


def get_state(db, tenant_id: str, *, runs: int = 8) -> dict:
    from app.domains.botstation.models import Combo15Auto, Combo15AutoResult, Combo15AutoRun
    from app.platform.db.repository import TenantRepository

    repo = TenantRepository(db, tenant_id)
    row = db.scalar(repo.query(Combo15Auto))
    recent = db.scalars(repo.query(Combo15AutoRun).order_by(
        Combo15AutoRun.created_at.desc()).limit(runs)).all()
    outcomes = {o.run_id: o for o in db.scalars(repo.query(Combo15AutoResult).where(
        Combo15AutoResult.run_id.in_([r.id for r in recent]))).all()} if recent else {}
    on = bool(row and row.enabled)
    return {"enabled": on, "rule": rule(),
            "next_run": next_slot().isoformat() if on else None,
            "runs": [_serialize_run(r, outcomes.get(r.id)) for r in recent]}


def set_state(db, tenant_id: str, *, enabled: bool) -> dict:
    from app.domains.botstation.models import Combo15Auto
    from app.platform.db.repository import TenantRepository

    repo = TenantRepository(db, tenant_id)
    row = db.scalar(repo.query(Combo15Auto))
    if row is None:
        row = Combo15Auto(enabled=False)
        repo.add(row)
    if enabled and not row.enabled:
        row.enabled_at = _naive_utc(_now())
    row.enabled = bool(enabled)
    db.commit()
    return get_state(db, tenant_id)


def run_slot(cred, tradier_cred, tenant, slot: str, rng=random) -> dict:
    """Check the cash, build, pick, judge, place. What to record."""
    from app.domains.botstation import combo15
    from app.domains.botstation.luck_schedule import _combo_cash

    cash = _combo_cash(cred)
    if cash < MAX_USD:
        return {"status": "skipped",
                "detail": f"cash ${cash:.2f} on the combo shards (0 and 1) is under "
                          f"the ${MAX_USD:.2f} a combo may spend"}
    built = combo15.preview(cred, tradier_cred=tradier_cred)
    if not built.get("ok"):
        return {"status": "skipped",
                "detail": str(built.get("detail") or "no combo could be built")[:255]}
    valid = [leg for leg in built["legs"] if leg.get("default")]
    chosen, why = pick(valid, rng=rng)
    if chosen is None:
        return {"status": "skipped", "detail": why[:255], "legs": len(valid)}
    odds = chance(chosen)
    stake = round(rng.uniform(MIN_USD, MAX_USD), 2)
    placed = combo15.place(
        cred, legs=[{"ticker": leg["ticker"], "side": leg["side"]} for leg in chosen],
        stake_usd=stake, key=f"auto-{slot.replace(' ', 'T').replace(':', '')}",
        owner=tenant.id, tenant_slug=tenant.slug)
    names = ", ".join(f"{leg['label']} {leg['side'].upper()}" for leg in chosen)
    common = {"legs": len(chosen), "chance_pct": round(odds * 100, 2), "stake_usd": stake}
    if not placed.get("placed"):
        return {"status": "failed", **common,
                "detail": f"{names}: {placed.get('detail') or 'not placed'}"[:255]}
    cost = placed.get("cost_usd")
    return {"status": "placed", **common,
            "cost_usd": float(cost) if cost is not None else None,
            "combo_ticker": placed.get("combo_ticker"),
            "detail": (f"{names} -- {placed.get('contracts')} contracts"
                       + (f" at {placed.get('filled_c')}c" if placed.get("filled_c") is not None
                          else ""))[:255]}


def _interrupt_stale(now: datetime) -> None:
    from app.domains.botstation.models import Combo15AutoRun
    from app.platform.db.repository import TenantRepository
    from app.platform.db.session import session_scope
    from app.tenancy.models import Tenant

    cutoff = _naive_utc(now) - timedelta(seconds=STALE_RUN_S)
    with session_scope() as db:
        for tenant_id in db.scalars(select(Tenant.id)).all():
            repo = TenantRepository(db, tenant_id)
            for row in db.scalars(repo.query(Combo15AutoRun).where(
                    Combo15AutoRun.status == "running",
                    Combo15AutoRun.created_at < cutoff)).all():
                row.status = "interrupted"
                row.detail = ("the desk restarted while this ran -- check Kalshi "
                              "for an order; it is not run again")
                row.finished_at = _naive_utc(now)


def sweep_all_tenants(now: datetime | None = None, rng=random) -> int:
    """One pass: when a slot is due, run it for every operator with the bot
    on who has not run it yet. Returns how many slots were attempted."""
    from app.api_v2 import deps
    from app.domains.botstation import signal_trade
    from app.domains.botstation.models import Combo15Auto, Combo15AutoRun
    from app.platform.db.repository import TenantRepository
    from app.platform.db.session import session_scope
    from app.tenancy import repository as tenants
    from app.tenancy.models import Tenant

    now = now or _now()
    _interrupt_stale(now)
    slot = due_slot(now)
    if slot is None:
        return 0
    slot_start = _naive_utc(datetime.strptime(slot, "%Y-%m-%d %H:%M").replace(tzinfo=TZ))
    attempted = 0
    with session_scope() as db:
        tenant_ids = list(db.scalars(select(Tenant.id)).all())
    for tenant_id in tenant_ids:
        try:
            with session_scope() as db:
                repo = TenantRepository(db, tenant_id)
                auto = db.scalar(repo.query(Combo15Auto).where(Combo15Auto.enabled.is_(True)))
                if auto is None:
                    continue
                if auto.enabled_at and auto.enabled_at > slot_start:
                    continue                    # switched on after this slot began
                run = Combo15AutoRun(slot=slot, status="running")
                repo.add(run)
                try:
                    db.commit()                 # the claim: a second one fails
                except IntegrityError:
                    db.rollback()
                    continue
                attempted += 1
                tenant = db.get(Tenant, tenant_id)
                who = SimpleNamespace(id=tenant.id, slug=tenant.slug)
                try:
                    cred = signal_trade._credential(db, tenant_id)
                    try:
                        tradier = tenants.load_credential(db, tenant_id, "tradier_sandbox",
                                                          deps.keyring())
                    except Exception:           # noqa: BLE001
                        tradier = None          # the crypto board needs none
                    db.commit()
                    outcome = run_slot(cred, tradier, who, slot, rng=rng)
                except Exception as exc:        # noqa: BLE001
                    logger.warning("combo15 auto %s for one operator: %s: %s",
                                   slot, type(exc).__name__, exc)
                    outcome = {"status": "failed",
                               "detail": f"{type(exc).__name__}: {exc}"[:255]}
                for field in ("status", "detail", "legs", "chance_pct", "stake_usd",
                              "cost_usd", "combo_ticker"):
                    if field in outcome:
                        setattr(run, field, outcome[field])
                run.finished_at = _naive_utc(_now())
        except Exception as exc:                # noqa: BLE001
            logger.warning("combo15 auto sweep for one operator: %s", type(exc).__name__)
    return attempted


# ---- settling ----------------------------------------------------------------

def _num(value) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def outcome_of(market: dict | None, settlement: dict | None) -> dict | None:
    """What a placed combo came to, or None while it is still unresolved.

    The auto bot buys a combo on YES, so a YES resolution is a win. The P&L
    is Kalshi's settlement for the ticker -- revenue (cents) less cost and
    fees (dollars) -- when there is one.
    """
    market = market or {}
    result = str(market.get("result") or "").lower()
    status = str(market.get("status") or "").lower()
    if result in ("yes", "no"):
        won = "won" if result == "yes" else "lost"
    elif status in ("finalized", "settled") and result in ("", "void", "scalar"):
        won = "void"
    else:
        return None
    out = {"result": won, "cost_usd": None, "payout_usd": None,
           "fees_usd": None, "pnl_usd": None}
    if settlement:
        revenue = _num(settlement.get("revenue"))
        cost = ((_num(settlement.get("yes_total_cost_dollars")) or 0.0)
                + (_num(settlement.get("no_total_cost_dollars")) or 0.0))
        fees = _num(settlement.get("fee_cost")) or 0.0
        payout = revenue / 100.0 if revenue is not None else None
        out.update(cost_usd=round(cost, 4), payout_usd=payout, fees_usd=round(fees, 4),
                   pnl_usd=(round(payout - cost - fees, 2) if payout is not None else None))
    return out


def _settlement(client, ticker: str) -> dict | None:
    data = client.request("GET", "/portfolio/settlements", params={"ticker": ticker}) or {}
    for row in data.get("settlements") or []:
        if row.get("ticker") == ticker:
            return row
    return None


def settle_tenant(db, tenant_id: str, cred, now: datetime | None = None) -> int:
    """Record the outcome of every placed combo that has resolved. Returns how
    many results were written."""
    from app.domains.botstation import signal_trade, venue
    from app.domains.botstation.models import Combo15AutoResult, Combo15AutoRun
    from app.platform.db.repository import TenantRepository

    now = now or _now()
    repo = TenantRepository(db, tenant_id)
    done = select(Combo15AutoResult.run_id).where(Combo15AutoResult.tenant_id == tenant_id)
    pending = db.scalars(repo.query(Combo15AutoRun).where(
        Combo15AutoRun.status == "placed",
        Combo15AutoRun.combo_ticker.is_not(None),
        Combo15AutoRun.created_at >= _naive_utc(now) - timedelta(seconds=SETTLE_GIVE_UP_S),
        Combo15AutoRun.id.not_in(done))).all()
    if not pending:
        return 0
    written = 0
    client = venue._client(cred)
    try:
        for run in pending:
            try:
                market = signal_trade._market(client, run.combo_ticker)
                settlement = _settlement(client, run.combo_ticker) if market else None
            except Exception as exc:            # noqa: BLE001
                logger.info("combo15 settle %s: %s", run.combo_ticker, type(exc).__name__)
                continue
            outcome = outcome_of(market, settlement)
            if outcome is None:
                continue
            age = (_naive_utc(now) - run.created_at).total_seconds()
            if settlement is None and age < SETTLEMENT_WAIT_S:
                continue                        # resolved; the P&L is on its way
            repo.add(Combo15AutoResult(run_id=run.id, slot=run.slot,
                                       combo_ticker=run.combo_ticker,
                                       settled_at=_naive_utc(now), **outcome))
            written += 1
    finally:
        client.close()
    db.commit()
    return written


def settle_all_tenants(now: datetime | None = None, force: bool = False) -> int:
    """One settle pass for every operator, at most every SETTLE_EVERY_S."""
    import time

    from app.domains.botstation import signal_trade
    from app.platform.db.session import session_scope
    from app.tenancy.models import Tenant

    global _last_settle
    if not force and time.time() - _last_settle < SETTLE_EVERY_S:
        return 0
    _last_settle = time.time()
    with session_scope() as db:
        tenant_ids = list(db.scalars(select(Tenant.id)).all())
    written = 0
    for tenant_id in tenant_ids:
        try:
            with session_scope() as db:
                cred = signal_trade._credential(db, tenant_id)
                written += settle_tenant(db, tenant_id, cred, now)
        except Exception as exc:                # noqa: BLE001
            logger.info("combo15 settle for one operator: %s", type(exc).__name__)
    return written
