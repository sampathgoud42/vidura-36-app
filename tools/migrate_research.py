"""Move the super-research history into the api_v2 database.

Four tables, no reshaping: the columns mean the same thing on both sides, so
this is a copy rather than a transformation. What it DOES normalise is time.
The old tables mixed tz-aware and naive timestamps; the rebuild stores naive
UTC everywhere, so an offset-carrying string is converted rather than copied
verbatim -- otherwise two rows written a second apart could sort hours apart.

Idempotent by construction: every table has a natural key with a UNIQUE
index, and the insert is INSERT OR IGNORE against it. Running this twice
copies nothing the second time, which is what makes it safe to re-run after a
partial failure rather than something you get one attempt at.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (source table, destination table, columns, natural key)
TABLES = [
    ("super_signals", "research_signal",
     ["external_id", "book", "category", "ticker", "direction", "grade",
      "combo", "price", "accuracy_pct", "bar_time", "logged_at", "archived",
      "raw", "created_at"],
     "external_id"),
    ("daily_snapshots", "research_snapshot",
     ["kind", "snapshot_date", "payload", "source_file", "fetched_at"],
     "kind, snapshot_date"),
    ("gex0dte_hourly", "research_gex0dte_hour",
     ["trade_date", "hour_cst", "ticker", "net_gex", "call_gex", "put_gex",
      "spot", "regime", "flip", "call_wall", "put_wall", "fetched_at"],
     "trade_date, hour_cst"),
    ("pusher_heartbeats", "research_pusher_heartbeat",
     ["session", "seq", "ok", "reason", "wall_ms", "mono_ms", "received_at"],
     "session, seq"),
]

TIME_COLUMNS = {"logged_at", "created_at", "fetched_at", "received_at"}


def to_naive_utc(value):
    """An offset-aware timestamp string becomes naive UTC; anything else is
    passed through untouched. A value we cannot parse is copied verbatim
    rather than dropped -- losing a timestamp is worse than keeping an odd
    one, and it stays visible for someone to look at."""
    if not isinstance(value, str) or not value.strip():
        return value
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.isoformat(sep=" ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(ROOT / "var" / "app.db"))
    ap.add_argument("--dest", default=str(ROOT / "var" / "app-v2.db"))
    ap.add_argument("--apply", action="store_true",
                    help="without this the script reports and changes nothing")
    args = ap.parse_args()

    src = sqlite3.connect(f"file:{args.source}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    dest = sqlite3.connect(args.dest)

    total_copied = 0
    for source_table, dest_table, columns, key in TABLES:
        try:
            rows = src.execute(f"SELECT * FROM {source_table}").fetchall()
        except sqlite3.OperationalError:
            print(f"  {source_table:<22} absent in source; skipped")
            continue

        before = dest.execute(f"SELECT count(*) FROM {dest_table}").fetchone()[0]
        if args.apply:
            placeholders = ", ".join("?" for _ in columns)
            statement = (f"INSERT OR IGNORE INTO {dest_table} "
                         f"({', '.join(columns)}) VALUES ({placeholders})")
            payload = [
                tuple(to_naive_utc(row[c]) if c in TIME_COLUMNS else row[c]
                      for c in columns)
                for row in rows
            ]
            dest.executemany(statement, payload)
            dest.commit()
        after = dest.execute(f"SELECT count(*) FROM {dest_table}").fetchone()[0]
        copied = after - before
        total_copied += copied
        verb = "copied" if args.apply else "would copy"
        print(f"  {source_table:<22} {len(rows):>5} rows -> {dest_table:<28} "
              f"{verb} {copied if args.apply else len(rows) - before:>5} "
              f"(key: {key})")

    print(f"\n{'copied' if args.apply else 'DRY RUN — nothing written'}: "
          f"{total_copied} rows")
    if not args.apply:
        print("re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
