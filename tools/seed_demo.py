"""Create (or refresh) the demo operator, with mock data on its boards.

    .venv\\Scripts\\python tools\\seed_demo.py

Idempotent: safe to re-run. It resets the demo password, re-enables the
worlds, and replaces the mock rows.

WHY THIS IS SAFE TO PUBLISH A PASSWORD FOR
The demo operator is given NO VENUE CREDENTIALS. Not empty ones -- none at
all. So it cannot reach Tradier or Kalshi even if the server is taken out of
paper mode, because there is nothing to authenticate with. The password
protects a read-only view of invented numbers.

What stops it seeing anything real is not this script, it is tenant
isolation: every query is scoped to the operator making it, asking for
another operator's record returns not-found, and there is no parameter that
can name a different one. The demo account is the honest test of that claim.
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

DEMO_SLUG = "demo"
# Deliberately published. See the module docstring for why that is defensible.
DEMO_PASSWORD = "BankF@t1M"

WORLDS = {"tradier-platform": True, "36-trade-desk": True, "bot-station": True}


def main() -> int:
    from app.platform.db.base import utcnow
    from app.platform.db.session import session_scope
    from app.domains.botstation.models import BotRun, BotTrade
    from app.domains.trading.models import Position
    from app.tenancy import repository as tenants
    from app.tenancy.models import WellnessGoal, WellnessProfile
    from sqlalchemy import delete, select

    with session_scope() as db:
        tenant = tenants.by_slug(db, DEMO_SLUG)
        if tenant is None:
            tenant = tenants.create(
                db, slug=DEMO_SLUG, display_name="Demo",
                password=DEMO_PASSWORD, is_admin=False)
            print(f"created operator '{DEMO_SLUG}'")
        else:
            tenants.set_password(db, tenant, DEMO_PASSWORD)
            tenant.status = "active"
            print(f"reset operator '{DEMO_SLUG}'")

        # Never an admin. An account whose password is in a README must not be
        # able to create operators or read anyone's credential metadata.
        tenant.is_admin = False
        tenants.set_worlds(db, tenant, WORLDS, default="tradier-platform")
        db.flush()

        for model in (Position, BotTrade, BotRun, WellnessGoal, WellnessProfile):
            db.execute(delete(model).where(model.tenant_id == tenant.id))
        db.flush()

        now = utcnow()

        # --- positions: one of each state the desk renders differently ------
        # Every one is SANDBOX and every price is invented. The point is that
        # the boards have something to lay out, not that the numbers mean
        # anything.
        demo_positions = [
            dict(underlying="SPY", occ_symbol="SPY260904C00450000",
                 option_type="call", strike=450.0, delta_at_entry=0.34,
                 contracts=5, entry_price=1.20, tp_price=1.38, sl_price=0.84,
                 status="open", stop_protection="venue_resting",
                 tp_order_id="demo-tp-1", stop_order_id="demo-stop-1",
                 note="filled @ 1.20; TP 1.38 and stop 0.84 both resting",
                 opened_at=now - timedelta(hours=2)),
            dict(underlying="QQQ", occ_symbol="QQQ260904P00380000",
                 option_type="put", strike=380.0, delta_at_entry=-0.31,
                 contracts=3, entry_price=2.05, tp_price=2.36, sl_price=1.44,
                 status="open", stop_protection="monitored_only",
                 tp_order_id="demo-tp-2",
                 note="filled @ 2.05; TP 2.36 resting, stop 1.44 MONITORED "
                      "ONLY - no venue-side stop",
                 opened_at=now - timedelta(hours=1)),
            dict(underlying="SPY", occ_symbol="SPY260828C00445000",
                 option_type="call", strike=445.0, delta_at_entry=0.41,
                 contracts=4, entry_price=0.95, tp_price=1.09, sl_price=0.67,
                 exit_price=1.09, pnl_usd=56.0, status="tp_filled",
                 stop_protection="venue_resting", note="target filled",
                 opened_at=now - timedelta(days=1),
                 closed_at=now - timedelta(hours=20)),
            dict(underlying="IWM", occ_symbol="IWM260828P00200000",
                 option_type="put", strike=200.0, delta_at_entry=-0.28,
                 contracts=2, entry_price=1.60, tp_price=1.84, sl_price=1.12,
                 exit_price=1.12, pnl_usd=-96.0, status="sl_filled",
                 stop_protection="venue_resting",
                 note="stop filled at the venue",
                 opened_at=now - timedelta(days=2),
                 closed_at=now - timedelta(days=1, hours=3)),
        ]
        for row in demo_positions:
            db.add(Position(tenant_id=tenant.id, venue_sandbox=True,
                            expiration="2026-09-04", buy_pct=10.0,
                            tolerance_pct=25.0, tp_pct=15.0, sl_pct=30.0,
                            strategy="Demo", **row))

        # --- bot ledger: a mix of live, paper and genuinely UNKNOWN ---------
        # The unknown ones are the point. They appear under neither LIVE nor
        # PAPER and are counted separately, so the demo shows the real
        # behaviour rather than a tidied-up version of it.
        demo_trades = [
            ("btc15", "KXBTC15M-26AUG281200-00", "closed", 1, 0.67, 0.74, 0.07, False),
            ("btc15", "KXBTC15M-26AUG281215-15", "closed", 1, 0.55, 0.41, -0.14, False),
            ("btc15", "KXBTC15M-26AUG281230-30", "open", 2, 0.48, None, None, None),
            ("gold15", "KXGOLD15M-26AUG281700-00", "closed", 1, 0.55, 0.90, 0.35, False),
            ("gold15", "KXGOLD15M-26AUG281715-15", "open", 1, 0.44, None, None, None),
            ("sports", "KXITFMATCH-26AUG28DEMO-A", "closed", 5, 0.41, 0.97, 2.80, True),
            ("sports", "KXITFMATCH-26AUG28DEMO-B", "closed", 5, 0.62, 0.00, -3.10, True),
            ("parley", "DEMO-PARLEY-5LEG", "open", 1, 0.81, None, None, None),
        ]
        for i, (bot, ticker, status, qty, entry, exit_, pnl, live) in enumerate(demo_trades):
            db.add(BotTrade(
                tenant_id=tenant.id, bot_key=bot, bot_version="v2",
                external_id=f"demo:{bot}:{i}", ticker=ticker, status=status,
                opened_at=now - timedelta(hours=6 - i),
                closed_at=(now - timedelta(hours=5 - i)) if status == "closed" else None,
                contracts=qty, entry_price=entry, exit_price=exit_,
                realized_pnl=pnl, is_live=live,
                raw=json.dumps({"demo": True})))

        db.add(BotRun(tenant_id=tenant.id, bot_key="gold15", bot_version="v2",
                      mode="paper", status="stopped", started_at=now - timedelta(hours=4),
                      stopped_at=now - timedelta(hours=1), bankroll=50.0,
                      target_pct=25.0, stop_pct=50.0,
                      options_json=json.dumps({"contracts": 1})))

        profile = WellnessProfile(
            tenant_id=tenant.id, gender="prefer not to say", age_band="35-44",
            ethnicity="prefer not to say", diet="balanced", style="calm",
            region="midwest", notifications=False)
        db.add(profile)
        db.flush()
        for i, goal in enumerate(("sleep-better", "move-more")):
            db.add(WellnessGoal(tenant_id=tenant.id, profile_id=profile.id,
                                goal=goal, position=i))

        # NO CREDENTIALS. Deliberately, and the whole reason the password can
        # be published: with nothing to authenticate to a venue with, this
        # account cannot place an order even if paper mode is switched off.
        creds = tenants.list_credentials(db, tenant.id)
        if creds:
            print(f"  WARNING: demo has {len(creds)} credential(s) — it should "
                  f"have none. Revoke them.")

        print(f"  worlds     : {', '.join(k for k, v in WORLDS.items() if v)}")
        print(f"  positions  : {len(demo_positions)}")
        print(f"  bot trades : {len(demo_trades)} "
              f"({sum(1 for t in demo_trades if t[7] is None)} unclassified)")
        print(f"  credentials: none — cannot reach a venue")
        print(f"\nsign in as '{DEMO_SLUG}' / {DEMO_PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
