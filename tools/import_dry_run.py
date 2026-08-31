"""Phase 8, step 2: import into a SCRATCH database and reconcile.

Touches nothing real. Builds a throwaway database, runs the whole import
against it, and reports source counts against imported counts so the
difference is visible before anything is done for real.

    .venv\\Scripts\\python tools\\import_dry_run.py
    .venv\\Scripts\\python tools\\import_dry_run.py --keep    (leave the scratch db)

Credentials go from the file straight into the encrypted store. They are never
written to an intermediate file, a log line, a temp table or this script's
output -- the point of the exercise is not to create a fifth copy of them.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

CUSTOMERS = PROJECT / "customers"
LEGACY_DB = PROJECT / "var" / "app.db"

DEFAULT_WORLDS = {"tradier-platform": True, "36-trade-desk": True,
                  "bot-station": True}

# Which .env keys belong to which venue. Anything not listed is reported as
# unrecognised rather than swept into a bucket -- an unknown key in a
# credential file is a question, not a default.
# env-var name -> the CANONICAL field the credential store reads.
#
# This map used to be a plain list of env names, and the secret was stored
# under those names verbatim. load_credential() reads "token" / "account_id" /
# "base_url" / "private_key_pem", so every imported credential decrypted
# perfectly into an object whose token was the empty string. It failed at the
# venue with "401 Invalid access token" -- which reads like a bad key, not a
# bad import, and is why it survived the dry run: the dry run counted rows and
# never asked whether the values were usable.
VENUE_KEYS = {
    "tradier": {
        "TRADIER_PROD_TOKEN": "token",
        "TRADIER_ACCESS_TOKEN": "token",          # pre-2026-08 name
        "TRADIER_PROD_ACCOUNT_ID": "account_id",
        "TRADIER_ACCOUNT_ID": "account_id",       # pre-2026-08 name
        "TRADIER_PROD_URI": "base_url",
    },
    "tradier_sandbox": {
        "TRADIER_SANDBOX_TOKEN": "token",
        "TRADIER_SANDBOX_ACCOUNT_ID": "account_id",
        "TRADIER_SANDBOX_URI": "base_url",
    },
    "kalshi": {
        "KALSHI_API_KEY_ID": "token",             # the key id IS the identity
        "BASE_URI": "base_url",
        # KALSHI_PRIVATE_KEY names a FILE; the PEM itself is read below.
    },
}


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip():
            out[key.strip()] = value.strip()
    return out


def legacy_users() -> list[dict]:
    if not LEGACY_DB.is_file():
        return []
    conn = sqlite3.connect(f"file:{LEGACY_DB}?mode=ro", uri=True)
    try:
        cur = conn.execute("SELECT user_id, username, email, user_root_folder "
                           "FROM users ORDER BY created_at")
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true",
                        help="leave the scratch database in place")
    args = parser.parse_args()

    scratch_dir = Path(tempfile.mkdtemp(prefix="vidura_import_dry_"))
    scratch = scratch_dir / "scratch.db"
    url = f"sqlite:///{scratch.as_posix()}"

    import os
    os.environ["TBOT_DATABASE_URL_OVERRIDE"] = url
    os.environ.setdefault("TBOT_ENCRYPTION_MASTER_KEY", "dry-run-key-not-real")

    from app.core.config import get_settings
    get_settings.cache_clear()

    from app.platform.db import migrations, session
    from app.platform.security.envelope import Keyring
    from app.tenancy import repository as tenants
    from app.tenancy.models import WellnessGoal, WellnessProfile

    session.reset_for_tests()
    migrations.upgrade_to_head(url=url)
    keyring = Keyring.from_env()

    print(f"scratch database: {scratch}\n")

    users = legacy_users()
    report = {"operators": [], "rejected": [], "unassigned": []}

    with session.session_scope() as db:
        for row in users:
            slug = (row["username"] or "").strip().lower()
            folder = CUSTOMERS / slug
            sam = folder / ".sam"

            if not folder.is_dir():
                report["rejected"].append(
                    {"slug": slug, "reason": "no credential folder"})
                continue
            if not sam.is_file() or not sam.read_text(
                    encoding="utf-8", errors="replace").strip():
                report["rejected"].append(
                    {"slug": slug, "reason": "no password on file"})
                continue

            # PLAINTEXT in, Argon2id out. Profiled as certain rather than
            # assumed: credentials.verify_password compares the file byte-wise,
            # so there is no hash format to preserve.
            password = sam.read_text(encoding="utf-8", errors="replace").strip()
            tenant = tenants.create(
                db, slug=slug, display_name=slug.title(),
                password=password, email=(row["email"] or None) or None,
                is_admin=(slug == "sampath"),
            )
            tenants.set_worlds(db, tenant, DEFAULT_WORLDS,
                               default="tradier-platform")

            env = read_env(folder / ".env")
            pem = next(iter(sorted(folder.glob("*.pem"))), None)
            # Three states, not two. A key that is DECLARED BUT EMPTY is a
            # different problem from one nobody recognises: the first means an
            # operator has no usable credential for that venue, the second
            # means this importer does not know where a value belongs. Calling
            # both "unrecognised" sends whoever reads this hunting the wrong
            # thing.
            known = {k for keymap in VENUE_KEYS.values() for k in keymap}
            empty = sorted(k for k, v in env.items() if k in known and not v)
            stored, unknown = [], {k for k, v in env.items()
                                   if v and k not in known}
            for venue, keymap in VENUE_KEYS.items():
                # Canonical names, not env names. The first env var that has a
                # value wins, so the modern name beats the legacy alias.
                secret: dict[str, str] = {}
                for env_name, canonical in keymap.items():
                    value = env.get(env_name, "").strip()
                    if value and canonical not in secret:
                        secret[canonical] = value
                if venue == "kalshi" and pem is not None and secret:
                    secret["private_key_pem"] = pem.read_text(
                        encoding="utf-8", errors="replace")
                if not secret.get("token") and not secret.get("private_key_pem"):
                    # Nothing usable. A credential row with no material is
                    # worse than none: it looks configured and fails at the
                    # venue.
                    continue
                tenants.store_credential(
                    db, tenant, venue=venue, label="default",
                    secret=secret, keyring=keyring, actor="import")
                stored.append(venue)

            profile = folder / "wellness-profile.json"
            wellness = False
            if profile.is_file():
                data = json.loads(profile.read_text(encoding="utf-8"))
                row_obj = WellnessProfile(
                    tenant_id=tenant.id, gender=data.get("gender"),
                    # The source stores a BAND ("35-44"), never a number.
                    age_band=data.get("age") or data.get("age_band"),
                    ethnicity=data.get("ethnicity"), diet=data.get("diet"),
                    style=data.get("style"), region=data.get("region"),
                    notifications=bool(data.get("notifications")))
                db.add(row_obj)
                db.flush()
                for i, goal in enumerate(data.get("goals") or []):
                    db.add(WellnessGoal(tenant_id=tenant.id,
                                        profile_id=row_obj.id,
                                        goal=str(goal)[:64], position=i))
                wellness = True

            report["operators"].append({
                "slug": slug, "new_id": tenant.id, "legacy_id": row["user_id"],
                "credentials": stored,
                "unrecognised_env_keys": sorted(unknown),
                "declared_but_empty": empty,
                "wellness": wellness,
            })

    # Folders with no user row cannot be assigned a tenant, and the brief is
    # explicit that they must NOT be defaulted into a shared one.
    for folder in sorted(p for p in CUSTOMERS.iterdir() if p.is_dir()):
        if folder.name.lower() not in {u["slug"] for u in report["operators"]}:
            rows = 0
            history = folder / "trade_history"
            if history.is_dir():
                for f in history.glob("*.csv"):
                    with f.open(newline="", encoding="utf-8-sig",
                                errors="replace") as fh:
                        rows += max(0, len(list(csv.reader(fh))) - 1)
            report["unassigned"].append({"folder": folder.name,
                                         "trade_rows": rows})

    _print(report, scratch, url)
    if not args.keep:
        import shutil
        session.reset_for_tests()
        shutil.rmtree(scratch_dir, ignore_errors=True)
        print("\nscratch database removed (--keep to retain it)")
    return 0


def _print(report: dict, scratch: Path, url: str) -> None:
    print("IMPORTED")
    print("-" * 60)
    for op in report["operators"]:
        print(f"  {op['slug']}")
        print(f"    legacy id  : {op['legacy_id']}")
        print(f"    new id     : {op['new_id']}  (renumbered)")
        print(f"    credentials: {', '.join(op['credentials']) or 'none'}")
        print(f"    wellness   : {'yes' if op['wellness'] else 'no'}")
        if op["declared_but_empty"]:
            print(f"    DECLARED BUT EMPTY   : "
                  f"{', '.join(op['declared_but_empty'])}")
        if op["unrecognised_env_keys"]:
            print(f"    UNRECOGNISED keys    : "
                  f"{', '.join(op['unrecognised_env_keys'])}")

    if report["rejected"]:
        print("\nREJECTED")
        print("-" * 60)
        for r in report["rejected"]:
            print(f"  {r['slug']}: {r['reason']}")

    if report["unassigned"]:
        print("\nNOT ASSIGNED TO ANY TENANT - needs your decision")
        print("-" * 60)
        for u in report["unassigned"]:
            print(f"  {u['folder']}: {u['trade_rows']} trade row(s), no user row")
        print("\n  Not defaulted into a shared tenant, deliberately. Each is")
        print("  either a real operator who needs creating, or dead data.")

    # Reconciliation: count what landed by reading the scratch database back,
    # rather than trusting the counters this script incremented.
    print("\nRECONCILIATION (read back from the scratch database)")
    print("-" * 60)
    conn = sqlite3.connect(scratch)
    try:
        for table in ("tenant", "tenant_credential", "tenant_world_access",
                      "wellness_profile", "wellness_goal"):
            n = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            print(f"  {table:<22} {n}")
        leaked = conn.execute(
            "SELECT count(*) FROM tenant_credential WHERE ciphertext IS NULL"
        ).fetchone()[0]
        print(f"  unencrypted credentials {leaked}   <- must be 0")
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
