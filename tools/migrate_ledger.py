"""Bring the trade ledger and the venue credentials across, in place.

    .venv\\Scripts\\python tools\\migrate_ledger.py            (dry run)
    .venv\\Scripts\\python tools\\migrate_ledger.py --apply

Additive and idempotent. It does not recreate the database, so operators
added since the first import -- the demo account, for one -- survive.

Two jobs, and they are here together because they are the same omission
noticed twice:

  CREDENTIALS  The first import stored secrets under their ENV VAR NAMES
               (TRADIER_PROD_TOKEN) while the store reads canonical ones
               (token). Every credential decrypted into an object whose token
               was the empty string, and failed at the venue with "401 Invalid
               access token" -- which reads like a bad key rather than a bad
               import. Re-stored here from the same .env files, mapped
               properly.

  LEDGER       Phase 8 migrated operators and credentials only. That was too
               narrow a reading of "customer data": 370 trades and 59
               positions are the operator's own history, and a desk that shows
               none of it is not the desk they had.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

LEGACY_DB = PROJECT / "var" / "app.db"
CUSTOMERS = PROJECT / "customers"


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip():
            out[k.strip()] = v.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write; without it, report only")
    args = ap.parse_args()

    # The corrected map, loaded by path so this works regardless of how
    # the script is invoked.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_import_run", PROJECT / "tools" / "import_run.py")
    _mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_mod)
    VENUE_KEYS = _mod.VENUE_KEYS

    from app.api_v2 import deps
    from app.domains.botstation.ledger.ingest import _as_datetime
    from app.domains.botstation.models import BotTrade
    from app.platform.db.session import session_scope
    from app.tenancy import repository as tenants
    from app.tenancy.models import TenantCredential
    from sqlalchemy import delete, select

    legacy = sqlite3.connect(f"file:{LEGACY_DB}?mode=ro", uri=True)
    legacy.row_factory = sqlite3.Row

    creds_fixed = trades_added = trades_skipped = 0

    with session_scope() as db:
        keyring = deps.keyring()

        for tenant in tenants.list_all(db):
            folder = CUSTOMERS / tenant.slug
            env = read_env(folder / ".env")
            pem = next(iter(sorted(folder.glob("*.pem"))), None)

            # ---- credentials -------------------------------------------
            for venue, keymap in VENUE_KEYS.items():
                secret: dict[str, str] = {}
                for env_name, canonical in keymap.items():
                    value = env.get(env_name, "").strip()
                    if value and canonical not in secret:
                        secret[canonical] = value
                if venue == "kalshi" and pem is not None and secret:
                    secret["private_key_pem"] = pem.read_text(
                        encoding="utf-8", errors="replace")
                if not secret.get("token") and not secret.get("private_key_pem"):
                    continue

                have = [c for c in tenants.list_credentials(db, tenant.id)
                        if c.venue == venue and c.active]
                what = "rotate" if have else "create"
                print(f"  {tenant.slug:<9} {venue:<16} {what}  "
                      f"({', '.join(sorted(secret))})")
                creds_fixed += 1
                if args.apply:
                    if have:
                        row = db.get(TenantCredential, have[0].credential_id)
                        tenants.rotate_credential(db, row, secret=secret,
                                                  keyring=keyring,
                                                  actor="migrate_ledger")
                    else:
                        tenants.store_credential(db, tenant, venue=venue,
                                                 label="default", secret=secret,
                                                 keyring=keyring,
                                                 actor="migrate_ledger")

            # ---- ledger -------------------------------------------------
            legacy_user = legacy.execute(
                "SELECT user_id FROM users WHERE lower(username)=?",
                (tenant.slug.lower(),)).fetchone()
            if legacy_user is None:
                continue

            rows = legacy.execute(
                "SELECT * FROM trades WHERE user_id=?",
                (legacy_user["user_id"],)).fetchall()
            if not rows:
                continue

            existing = {
                e for (e,) in db.execute(
                    select(BotTrade.external_id).where(
                        BotTrade.tenant_id == tenant.id))
            }
            new_rows = [r for r in rows if r["external_id"] not in existing]
            unclassified = sum(1 for r in new_rows if r["is_live"] is None)
            print(f"  {tenant.slug:<9} ledger           "
                  f"{len(new_rows)} new of {len(rows)} "
                  f"({unclassified} unclassified, {len(rows)-len(new_rows)} already present)")
            trades_added += len(new_rows)
            trades_skipped += len(rows) - len(new_rows)

            if args.apply:
                for r in new_rows:
                    db.add(BotTrade(
                        tenant_id=tenant.id, bot_key=r["bot_key"],
                        bot_version=r["bot_version"],
                        external_id=r["external_id"], ticker=r["ticker"] or "",
                        status=r["status"] or "closed",
                        # sqlite3 hands these back as STRINGS. SQLAlchemy's
                        # DateTime refuses anything but a datetime, and the
                        # failure surfaces on a later flush -- in a credential
                        # rotation, nowhere near the row that caused it.
                        opened_at=_as_datetime(r["opened_at"]),
                        closed_at=_as_datetime(r["closed_at"]),
                        contracts=r["contracts"],
                        entry_price=r["price_cents"],
                        realized_pnl=r["pnl_usd"],
                        # NULL stays NULL. 324 btc15 rows genuinely predate the
                        # dry-run column and their mode is unknowable; guessing
                        # would label real money as paper.
                        is_live=r["is_live"],
                        raw=r["raw"] if isinstance(r["raw"], str)
                            else json.dumps(r["raw"], default=str)))

        if not args.apply:
            db.rollback()

    legacy.close()
    print()
    print(f"credentials {'re-stored' if args.apply else 'to re-store'}: {creds_fixed}")
    print(f"trades {'imported' if args.apply else 'to import'}: {trades_added} "
          f"({trades_skipped} already present)")
    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
