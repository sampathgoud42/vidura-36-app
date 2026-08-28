"""Copy the local SQLite ledger into a Postgres database.

The cloud deployment runs on Postgres because Cloud Run's filesystem does not
survive a restart, and losing this database while positions are open means
live Tradier positions that nothing is managing a stop-loss for. This is the
one-time move of what is already on disk.

    python tools/migrate_to_postgres.py --target postgresql+psycopg://...

Safe by default: it refuses to write into a database that already has rows,
so re-running it cannot silently double the ledger. --force replaces the
contents of the tables it copies.

Nothing here prints a credential. The target URL is echoed with its password
masked, because the whole point of the run is to confirm you pointed it at
the right host.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))


def mask(url: str) -> str:
    """The URL with its password replaced, for printing."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable url>"
    if not parts.password:
        return url
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    netloc = f"{parts.username or ''}:***@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def normalise(url: str) -> str:
    """Accept the same shapes the app accepts."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=os.environ.get("TBOT_DATABASE_URL_OVERRIDE", ""),
                    help="Postgres URL (or set TBOT_DATABASE_URL_OVERRIDE)")
    ap.add_argument("--source", default=str(PROJECT_ROOT / "var" / "app.db"),
                    help="SQLite file to copy from (default: var/app.db)")
    ap.add_argument("--force", action="store_true",
                    help="replace rows in a target that is not empty")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be copied and change nothing")
    args = ap.parse_args()

    if not args.target:
        ap.error("no --target given and TBOT_DATABASE_URL_OVERRIDE is unset")
    target_url = normalise(args.target)
    if target_url.startswith("sqlite"):
        ap.error("--target is a SQLite URL; this tool moves data INTO Postgres")

    source_path = Path(args.source)
    if not source_path.is_file():
        ap.error(f"no SQLite database at {source_path}")

    from sqlalchemy import create_engine, insert, select, text

    from app.core.database import Base
    from app import models  # noqa: F401  - registers the tables on Base

    src = create_engine(f"sqlite:///{source_path.as_posix()}",
                        connect_args={"check_same_thread": False})

    print(f"source  {source_path}")
    print(f"target  {mask(target_url)}")

    # sorted_tables is dependency-ordered, so parents land before the rows
    # that reference them and the copy never trips a foreign key.
    tables = list(Base.metadata.sorted_tables)

    with src.connect() as sconn:
        counts = {}
        for t in tables:
            try:
                counts[t.name] = sconn.execute(
                    select(text("count(*)")).select_from(t)).scalar_one()
            except Exception:                              # noqa: BLE001
                counts[t.name] = 0        # table absent in an older SQLite file

    total = sum(counts.values())
    print("\nrows to copy:")
    for name, n in counts.items():
        if n:
            print(f"  {name:<24} {n}")
    if not total:
        print("  (nothing)")
    print(f"  {'TOTAL':<24} {total}")

    if args.dry_run:
        # Deliberately before the target engine is built: a dry run should
        # report what is here without needing the target to exist, be
        # reachable, or have a driver installed.
        print("\ndry run - nothing written")
        return 0

    dst = create_engine(target_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=dst)

    with dst.begin() as dconn:
        occupied = {}
        for t in tables:
            n = dconn.execute(select(text("count(*)")).select_from(t)).scalar_one()
            if n:
                occupied[t.name] = n
        if occupied and not args.force:
            print("\nTarget already holds rows:")
            for name, n in occupied.items():
                print(f"  {name:<24} {n}")
            print("\nRefusing to write. Re-run with --force to replace them.")
            return 2
        if occupied:
            # reverse order: children before the parents they point at
            for t in reversed(tables):
                dconn.execute(t.delete())

        copied = 0
        with src.connect() as sconn:
            for t in tables:
                if not counts.get(t.name):
                    continue
                rows = [dict(r._mapping) for r in sconn.execute(select(t))]
                if not rows:
                    continue
                dconn.execute(insert(t), rows)
                copied += len(rows)
                print(f"  copied {len(rows):>5}  {t.name}")

        # Postgres sequences do not know about ids that arrived by copy, so
        # the next insert would collide with an existing primary key.
        if dst.dialect.name == "postgresql":
            for t in tables:
                for col in t.primary_key.columns:
                    if not col.autoincrement or not str(col.type).lower().startswith("int"):
                        continue
                    dconn.execute(text(
                        "SELECT setval(pg_get_serial_sequence(:t, :c), "
                        "COALESCE((SELECT MAX(%s) FROM %s), 0) + 1, false)"
                        % (col.name, t.name)
                    ), {"t": t.name, "c": col.name})
                    print(f"  sequence reset  {t.name}.{col.name}")

    print(f"\ndone - {copied} row(s) copied")
    print("Verify before pointing the app at it:")
    print("  the desk's positions list should show the same rows it does locally")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
