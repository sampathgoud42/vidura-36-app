"""Add one customer from its folder: customers/<slug>/ -> a sign-in.

The desk signs people in against the ``tenant`` table, not the folder, so a
folder dropped under customers/ is not an account until something creates
one. tools/import_run.py did that once, for every operator, into a fresh
database; this does it for ONE folder, into the live one, the same way:

  * the account, from the folder's .sam (plaintext in, Argon2id stored)
  * the three worlds switched on, the Tradier Platform as home
  * the broker keys from .env and the Kalshi .pem, into the encrypted store

    .venv\\Scripts\\python tools\\add_customer.py sampaths

The password and the keys are never printed, logged or copied anywhere but
the encrypted store. An account that already exists is refused rather than
overwritten -- changing a password is the admin API's PATCH /tenants/{id}.
Safe while the desk runs: one short write transaction.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))
sys.path.insert(0, str(PROJECT / "tools"))

from import_run import DEFAULT_WORLDS, VENUE_KEYS, read_env  # noqa: E402

CUSTOMERS = PROJECT / "customers"


def main() -> int:
    parser = argparse.ArgumentParser(description="Add one customer from customers/<slug>/.")
    parser.add_argument("slug", help="the folder name under customers/, which becomes the sign-in name")
    parser.add_argument("--admin", action="store_true", help="make this customer an admin")
    args = parser.parse_args()

    slug = args.slug.strip().lower()
    folder = CUSTOMERS / slug
    sam = folder / ".sam"
    if not folder.is_dir():
        print(f"no folder {folder}")
        return 1
    password = sam.read_text(encoding="utf-8", errors="replace").strip() if sam.is_file() else ""
    if len(password) < 8:
        # The admin API's own floor (TenantCreate.password, min 8).
        print(f"{sam} is missing, empty or shorter than 8 characters -- set a password there first")
        return 1

    from app.platform.db import migrations, session
    from app.platform.security.envelope import Keyring
    from app.tenancy import repository as tenants

    migrations.upgrade_to_head()
    keyring = Keyring.from_env()

    with session.session_scope() as db:
        if tenants.by_slug(db, slug) is not None:
            print(f"{slug!r} already has an account -- nothing changed")
            return 1
        tenant = tenants.create(db, slug=slug, display_name=slug.title(),
                                password=password, email=None, is_admin=args.admin)
        tenants.set_worlds(db, tenant, DEFAULT_WORLDS, default="tradier-platform")

        env = read_env(folder / ".env")
        pem = next(iter(sorted(folder.glob("*.pem"))), None)
        stored = []
        for venue, keymap in VENUE_KEYS.items():
            secret: dict[str, str] = {}
            for env_name, canonical in keymap.items():
                value = env.get(env_name, "").strip()
                if value and canonical not in secret:
                    secret[canonical] = value
            if venue == "kalshi" and pem is not None and secret:
                secret["private_key_pem"] = pem.read_text(encoding="utf-8", errors="replace")
            if not secret.get("token") and not secret.get("private_key_pem"):
                continue            # nothing usable: no row that looks configured and fails
            tenants.store_credential(db, tenant, venue=venue, label="default",
                                     secret=secret, keyring=keyring, actor="add_customer")
            stored.append(venue)

    print(f"added {slug!r}{' (admin)' if args.admin else ''}: sign in with the password in {sam.name}")
    print(f"  worlds: {', '.join(k for k, v in DEFAULT_WORLDS.items() if v)}")
    print(f"  broker keys stored: {', '.join(stored) or 'none -- add them to .env and use the admin API'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
