"""The luck parley, on a schedule -- the desk's AUTO ORDER.

While an operator has it switched on, a ticket is built and placed in the
background -- at 9:00 and 18:00 Chicago time every day, or every N hours on
the hour when the operator picked a frequency -- from the settings the Luck
form held when it was switched on or last updated:

  1. cash   the shards a combo spends from -- 0 and 1; Kalshi moves cash from
            0 to 1 itself for a combo -- must hold at least the ticket's most
            spend, or the slot is skipped;
  2. build  luck.preview with those settings, which has Kalshi accept the
            exact legs before anything is bought, as on the desk;
  3. pick   the legs the form would have ticked: every one up to ten, a
            random three in four past ten, never fewer than the minimum;
  4. odds   the chance of the picked legs all winning -- the product of
            their prices, as the sheet shows it -- must be under the cap
            (10% unless set), or the slot is skipped;
  5. place  luck.place.

Each slot is claimed by writing its row FIRST, unique per (operator, slot):
a slot runs once, across loop passes and across restarts. A run cut off by a
restart is marked interrupted and never repeated -- repeating a placement
could buy the ticket twice.
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

TZ = ZoneInfo("America/Chicago")
# (hour, minute), Chicago time, every day of the week.
SLOTS = ((9, 0), (18, 0))
# A slot the loop did not see on time -- the desk was restarting at 9:00 --
# still runs up to this long after it. Later than that it is let go: a
# morning ticket bought at noon is not the ticket that was scheduled.
GRACE_S = 45 * 60
POLL_S = 60
# A run still 'running' after this long was cut off by a restart.
STALE_RUN_S = 30 * 60
# The form's own default pick, which a scheduled ticket keeps to: past this
# many legs a random share of them, never fewer than the minimum.
PICK_OVER = 10
PICK_SHARE = 0.75
# The frequencies AUTO ORDER offers, in hours. Each divides the day, so the
# slots fall on the same clock hours every day: every 6 is 0, 6, 12, 18. 0 is
# the original twice a day, at SLOTS.
EVERY_HOURS = (0, 1, 2, 3, 4, 6, 8, 12, 24)
MAX_CHANCE_PCT = 10.0

CONFIG_DEFAULTS = {
    "min_legs": 5, "max_legs": 24, "min_usd": 5.0, "max_usd": 7.5,
    "min_leg_c": 67, "max_leg_c": 97, "min_volume_usd": 5000.0,
    "max_spread_c": 3, "max_hours": 72, "no_side_only": False, "sports": [],
    "every_hours": 0, "max_chance_pct": MAX_CHANCE_PCT,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _naive_utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def _slots(every_hours: int = 0) -> tuple:
    """The day's (hour, minute) slots: SLOTS, or every N hours from midnight."""
    every = int(every_hours or 0)
    if every <= 0:
        return SLOTS
    return tuple((h, 0) for h in range(0, 24, every))


def due_slot(now: datetime | None = None, every_hours: int = 0) -> str | None:
    """The slot that is due now, "2026-10-04 09:00" -- or None."""
    local = (now or _now()).astimezone(TZ)
    for hour, minute in _slots(every_hours):
        at = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if at <= local < at + timedelta(seconds=GRACE_S):
            return at.strftime("%Y-%m-%d %H:%M")
    return None


def next_slot(now: datetime | None = None, every_hours: int = 0) -> datetime:
    """When the next slot starts, in UTC."""
    local = (now or _now()).astimezone(TZ)
    for days in (0, 1):
        day = local + timedelta(days=days)
        for hour, minute in _slots(every_hours):
            at = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if at > local:
                return at.astimezone(timezone.utc)
    return local.astimezone(timezone.utc)            # unreachable: a slot a day at least


def pick_tickers(legs: list[dict], min_legs: int, rng=random) -> list[str]:
    """The legs the form would have ticked: all of them up to PICK_OVER,
    past that a random PICK_SHARE, never fewer than ``min_legs``."""
    tickers = [leg["ticker"] for leg in legs]
    if len(tickers) <= PICK_OVER:
        return tickers
    want = min(len(tickers), max(int(min_legs),
                                 round(len(tickers) * PICK_SHARE)))
    return rng.sample(tickers, want)


def _config(raw: str | None) -> dict:
    try:
        saved = json.loads(raw or "{}") or {}
    except ValueError:
        saved = {}
    return {**CONFIG_DEFAULTS, **{k: v for k, v in saved.items()
                                  if k in CONFIG_DEFAULTS}}


def chance(legs: list[dict], tickers: list[str]) -> float:
    """The chance of every picked leg winning, 0-1: the product of their
    prices, the same number the sheet shows."""
    price = {leg["ticker"]: (leg.get("price_c") or 0) / 100 for leg in legs}
    out = 1.0
    for ticker in tickers:
        out *= price.get(ticker, 0.0)
    return out


def _serialize_run(row) -> dict:
    def stamp(moment):
        return (moment.replace(tzinfo=timezone.utc).isoformat()
                if moment else None)
    return {"slot": row.slot, "status": row.status, "detail": row.detail,
            "legs": row.legs, "cost_usd": row.cost_usd,
            "combo_ticker": row.combo_ticker,
            "started_at": stamp(row.created_at),
            "finished_at": stamp(row.finished_at)}


def get_state(db, tenant_id: str, *, runs: int = 6) -> dict:
    """The operator's schedule: on or off, the ticket it places, when it
    next runs, and its latest runs."""
    from app.domains.botstation.models import LuckRun, LuckSchedule
    from app.platform.db.repository import TenantRepository

    repo = TenantRepository(db, tenant_id)
    row = db.scalar(repo.query(LuckSchedule))
    recent = db.scalars(repo.query(LuckRun).order_by(
        LuckRun.created_at.desc()).limit(runs)).all()
    cfg = _config(row.config_json) if row else None
    every = int(cfg["every_hours"]) if cfg else 0
    return {
        "enabled": bool(row and row.enabled),
        "config": cfg,
        "times": [f"{h:02d}:{m:02d}" for h, m in _slots(every)],
        "every_hours_choices": list(EVERY_HOURS),
        "tz": "America/Chicago",
        "next_run": next_slot(every_hours=every).isoformat() if row and row.enabled else None,
        "runs": [_serialize_run(r) for r in recent],
    }


def set_state(db, tenant_id: str, *, enabled: bool,
              config: dict | None = None) -> dict:
    """Switch the schedule on or off, and set the ticket it places. Switching
    on needs a ticket -- this call's, or one saved before."""
    from app.domains.botstation.models import LuckSchedule
    from app.platform.db.repository import TenantRepository

    repo = TenantRepository(db, tenant_id)
    row = db.scalar(repo.query(LuckSchedule))
    if row is None:
        if enabled and config is None:
            raise ValueError("switching the schedule on needs the ticket's settings")
        row = LuckSchedule(enabled=False, config_json="{}")
        repo.add(row)
    if config is not None:
        row.config_json = json.dumps(
            {k: config[k] for k in CONFIG_DEFAULTS if k in config})
    if enabled and not row.enabled:
        row.enabled_at = _naive_utc(_now())
    row.enabled = bool(enabled)
    db.commit()
    return get_state(db, tenant_id)


def _slot_start(slot: str) -> datetime:
    """A slot key back to the moment it starts, naive UTC."""
    local = datetime.strptime(slot, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    return _naive_utc(local)


def _combo_cash(cred) -> float:
    """Cash on the shards a combo spends from: 0 and 1."""
    from app.domains.botstation import shards, venue

    client = venue._client(cred)
    try:
        return round(sum(r["usd"] for r in shards.balances(client)
                         if r["shard"] in (0, 1)), 2)
    finally:
        client.close()


def run_ticket(cred, tenant, cfg: dict, rng=random) -> dict:
    """Check the cash, build the ticket, place it. Returns what to record:
    status, detail, legs, cost_usd, combo_ticker."""
    from app.domains.botstation import luck

    need = float(cfg["max_usd"])
    cash = _combo_cash(cred)
    if cash < need:
        return {"status": "skipped",
                "detail": f"cash ${cash:.2f} on the combo shards (0 and 1) is "
                          f"under the ${need:.2f} the ticket may spend"}
    built = luck.preview(
        cred, min_legs=int(cfg["min_legs"]), max_legs=int(cfg["max_legs"]),
        min_leg_c=int(cfg["min_leg_c"]), max_leg_c=int(cfg["max_leg_c"]),
        min_volume_usd=float(cfg["min_volume_usd"]),
        max_spread_c=cfg.get("max_spread_c"), max_hours=cfg.get("max_hours"),
        sports=list(cfg.get("sports") or []) or None,
        no_side_only=bool(cfg.get("no_side_only")), owner=tenant.id)
    if not built.get("ok"):
        return {"status": "skipped",
                "detail": str(built.get("detail") or "no ticket could be built")[:255]}
    tickers = pick_tickers(built["legs"], int(cfg["min_legs"]), rng=rng)
    cap = float(cfg.get("max_chance_pct") or MAX_CHANCE_PCT)
    odds_pct = chance(built["legs"], tickers) * 100
    if odds_pct >= cap:
        return {"status": "skipped", "legs": len(tickers),
                "detail": f"chance {odds_pct:.2f}% with {len(tickers)} of "
                          f"{len(built['legs'])} legs is not under {cap:g}% -- "
                          "nothing bought"}
    placed = luck.place(
        cred, built["token"], tenant_slug=tenant.slug, tickers=tickers,
        min_usd=float(cfg["min_usd"]), max_usd=need,
        min_legs=int(cfg["min_legs"]), owner=tenant.id)
    if not placed.get("placed"):
        return {"status": "failed",
                "detail": str(placed.get("detail") or "not placed")[:255],
                "legs": len(tickers)}
    legs = int(placed.get("legs_used") or len(tickers))
    cost = placed.get("cost_usd")
    return {"status": "placed",
            "detail": (f"{legs} of {len(built['legs'])} legs, "
                       f"{placed.get('contracts')} contracts"
                       + (f" at {placed.get('filled_c')}c"
                          if placed.get("filled_c") is not None else "")
                       + f", chance {odds_pct:.2f}%"
                       + (f" — {placed['detail']}" if placed.get("detail") else ""))[:255],
            "legs": legs, "cost_usd": float(cost) if cost is not None else None,
            "combo_ticker": placed.get("combo_ticker")}


def _interrupt_stale(now: datetime) -> None:
    """Runs a restart cut off: marked, never run again."""
    from app.domains.botstation.models import LuckRun
    from app.platform.db.repository import TenantRepository
    from app.platform.db.session import session_scope
    from app.tenancy.models import Tenant

    cutoff = _naive_utc(now) - timedelta(seconds=STALE_RUN_S)
    with session_scope() as db:
        for tenant_id in db.scalars(select(Tenant.id)).all():
            repo = TenantRepository(db, tenant_id)
            for row in db.scalars(repo.query(LuckRun).where(
                    LuckRun.status == "running",
                    LuckRun.created_at < cutoff)).all():
                row.status = "interrupted"
                row.detail = ("the desk restarted while this ran — check "
                              "Kalshi for an order; it is not run again")
                row.finished_at = _naive_utc(now)


def sweep_all_tenants(now: datetime | None = None, rng=random) -> int:
    """One pass of the schedule: when a slot is due, run it for every
    operator who has the schedule on and has not run it yet. Returns how
    many tickets were attempted."""
    from app.domains.botstation import signal_trade
    from app.domains.botstation.models import LuckRun, LuckSchedule
    from app.platform.db.repository import TenantRepository
    from app.platform.db.session import session_scope
    from app.tenancy.models import Tenant

    now = now or _now()
    _interrupt_stale(now)
    attempted = 0
    with session_scope() as db:
        tenant_ids = list(db.scalars(select(Tenant.id)).all())
    for tenant_id in tenant_ids:
        try:
            with session_scope() as db:
                repo = TenantRepository(db, tenant_id)
                schedule = db.scalar(repo.query(LuckSchedule).where(
                    LuckSchedule.enabled.is_(True)))
                if schedule is None:
                    continue
                cfg = _config(schedule.config_json)
                # Each operator's own frequency decides which slot is due.
                slot = due_slot(now, int(cfg["every_hours"] or 0))
                if slot is None:
                    continue
                if schedule.enabled_at and schedule.enabled_at > _slot_start(slot):
                    continue                    # switched on after this slot began
                # Claim the slot before anything else. The unique key makes
                # a second claim fail, which is the whole point.
                run = LuckRun(slot=slot, status="running")
                repo.add(run)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    continue
                attempted += 1
                tenant = db.get(Tenant, tenant_id)
                who = SimpleNamespace(id=tenant.id, slug=tenant.slug)
                try:
                    cred = signal_trade._credential(db, tenant_id)
                    # The ticket takes minutes; no transaction is held open
                    # across it, and nothing in it touches this session.
                    db.commit()
                    outcome = run_ticket(cred, who, cfg, rng=rng)
                except Exception as exc:                # noqa: BLE001
                    logger.warning("luck schedule %s for one operator: %s: %s",
                                   slot, type(exc).__name__, exc)
                    outcome = {"status": "failed",
                               "detail": f"{type(exc).__name__}: {exc}"[:255]}
                run.status = outcome["status"]
                run.detail = outcome.get("detail")
                run.legs = outcome.get("legs")
                run.cost_usd = outcome.get("cost_usd")
                run.combo_ticker = outcome.get("combo_ticker")
                run.finished_at = _naive_utc(_now())
                db.commit()
                logger.info("luck schedule %s: %s — %s", slot, run.status,
                            run.detail)
        except Exception as exc:                        # noqa: BLE001
            logger.warning("luck schedule for one operator: %s: %s",
                           type(exc).__name__, exc)
    return attempted
