"""Generate docs/data-model.md from the actual schema.

Derived rather than written, so it cannot drift from what the database really
is. Re-run it after any migration:

    .venv\\Scripts\\python tools\\gen_data_model.py

The prose that explains WHY a table or column exists is kept in WHY below and
keyed by name -- the shape comes from the schema, the reasoning comes from the
decisions that produced it, and neither is guessed at.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

OUT = PROJECT / "docs" / "data-model.md"

DOMAIN = {
    "tenant": "tenancy", "tenant_credential": "tenancy",
    "tenant_world_access": "tenancy", "tenant_secret_audit": "tenancy",
    "wellness_profile": "tenancy", "wellness_goal": "tenancy",
    "position": "trading", "execution_attempt": "trading",
    "execution_lease": "trading", "risk_heartbeat": "trading",
    "signal": "trading",
    "bot_run": "bot-station", "bot_trade": "bot-station",
}

WHY = {
    "tenant": "One operator. There is no organisation above this: Phase 0 "
              "proved it from four directions -- no tenant column in the old "
              "user table, one credential folder per person, one password "
              "beside those credentials, and world access keyed by username.",
    "tenant_credential": "A venue credential, envelope-encrypted. Reversible "
                         "on purpose, unlike the password: the system has to "
                         "present it to Tradier or Kalshi.",
    "tenant_world_access": "Which tiles an operator may open. Replaces "
                           "worlds.json -- a file edit per operator failed the "
                           "customer onboarding contract.",
    "tenant_secret_audit": "The one audit table, and it exists because the "
                           "brief requires recording who changed a credential "
                           "-- not because audit tables are good practice in "
                           "the abstract.",
    "wellness_profile": "Special-category personal data. UNIQUE on tenant_id: "
                        "the username is the unique id, expressed through the "
                        "tenant rather than duplicated as a string, so a "
                        "rename moves the profile instead of orphaning it.",
    "wellness_goal": "A child table rather than a JSON array, because the "
                     "value is genuinely multi-valued and a blob would make "
                     "'add a goal' a read-modify-write.",
    "position": "An options position and both its exits.",
    "execution_attempt": "What makes a duplicate order impossible to EXPRESS "
                         "rather than unlikely. The row is written before the "
                         "venue is called; a repeat submit hits the uniqueness "
                         "constraint and returns the first outcome.",
    "execution_lease": "A mutex that holds across processes. The primary key "
                       "IS the mutex -- two processes inserting the same key "
                       "cannot both succeed. An in-process lock does not span "
                       "workers, and two have run on this machine.",
    "risk_heartbeat": "The stop-loss's own watchdog. A stop that exists only "
                      "inside a running loop is not a risk control, so the "
                      "order path refuses new entries when this goes stale.",
    "signal": "Super-research signals: market data, identical for every "
              "operator. THE ONLY TABLE WITHOUT A TENANT, and the exemption "
              "is enumerated in the registry rather than implied.",
    "bot_run": "One supervised bot process. Bankroll and target are per BOT, "
               "never per account: the venue account is shared, so an "
               "account-wide floor let one bot's drawdown halt the others.",
    "bot_trade": "One trade a bot recorded, mirrored into the shared ledger. "
                 "Nothing here names a bot family -- adding a bot must not "
                 "add a table.",
}

COLUMN_WHY = {
    ("tenant", "slug"): "the username; the natural key, and what the wellness "
                        "profile's uniqueness is expressed through",
    ("tenant", "password_hash"): "Argon2id, never reversible. A venue key must "
                                 "be decrypted because it is presented to a "
                                 "venue; a password only needs comparing.",
    ("position", "delta_at_entry"): "SIGNED. A call's delta runs 0..+1 and a "
                                    "put's 0..-1; storing the magnitude "
                                    "recorded every put as positive.",
    ("position", "stop_order_id"): "the stop that rests AT THE VENUE, so it "
                                   "survives this process dying",
    ("position", "stop_protection"): "says out loud whether the stop survives "
                                     "a crash: venue_resting or monitored_only",
    ("position", "pnl_usd"): "derived, but stored: the ledger sorts and "
                             "aggregates on it (deliberate denormalisation)",
    ("bot_trade", "is_live"): "NULLABLE ON PURPOSE. 93 of the imported v2 rows "
                              "predate the dry-run flag and their mode is "
                              "unknowable. Unknown stays unknown.",
    ("bot_trade", "external_id"): "deterministic, supplied by the adapter, so "
                                  "re-ingesting is idempotent",
    ("execution_attempt", "idempotency_key"): "UNIQUE per tenant. A global key "
                                              "space would let one operator's "
                                              "retry return another's order.",
    ("tenant_credential", "wrapped_dek"): "the per-record data key, itself "
                                          "encrypted by the master key",
    ("tenant_credential", "key_version"): "which master key wrapped this "
                                          "record; what makes a re-key possible",
    ("wellness_profile", "age_band"): "a BAND (\"35-44\"), never a number. "
                                      "Named so nobody types it INTEGER.",
}


def main() -> int:
    from sqlalchemy import inspect

    from app.platform.db import registry
    from app.platform.db.base import Base

    registry.all_models()
    meta = Base.metadata

    scoped = {m.__tablename__ for m in registry.tenant_owned_models()
              if hasattr(m, "__tablename__")}

    lines: list[str] = []
    w = lines.append

    w("# Data model")
    w("")
    w("**Generated from the live schema by `tools/gen_data_model.py`.** Do not")
    w("edit by hand -- re-run it after a migration and the shape follows the")
    w("database instead of drifting from it.")
    w("")
    w(f"SQLite, one schema, {len(meta.tables)} tables. Every tenant-owned table")
    w("carries a `tenant_id` foreign key that is NOT NULL, so a row without an")
    w("owner cannot be written even by a raw INSERT.")
    w("")
    w("## Why one schema")
    w("")
    w("Schema-per-tenant and schema-per-world were both rejected in Phase 0.")
    w("The deciding argument was not the arithmetic but the onboarding")
    w("contract: adding a customer must cost zero deploys and zero DDL, and")
    w("every alternative makes it a migration. SQLite reinforces it -- there is")
    w("no `CREATE SCHEMA`, and the nearest equivalent means a file per world")
    w("with foreign keys the database will not enforce.")
    w("")

    # ---- diagram ----------------------------------------------------------
    w("## Entity relationships")
    w("")
    w("```mermaid")
    w("erDiagram")
    for table in sorted(meta.tables.values(), key=lambda t: t.name):
        for fk in table.foreign_keys:
            target = fk.column.table.name
            label = "owns" if fk.parent.name == "tenant_id" else fk.parent.name
            optional = "|o" if fk.parent.nullable else "||"
            w(f"    {target} {optional}--o{{ {table.name} : {label}")
    for table in sorted(meta.tables.values(), key=lambda t: t.name):
        if not table.foreign_keys and not any(
                fk.column.table is table
                for t in meta.tables.values() for fk in t.foreign_keys):
            w(f"    {table.name} {{")
            w(f"        text standalone")
            w("    }")
    w("```")
    w("")
    w("`signal` and `execution_lease` stand alone deliberately. Signals are")
    w("market data with no owner; a lease is transient bookkeeping whose key")
    w("already carries the tenant.")
    w("")

    # ---- tables -----------------------------------------------------------
    for domain in ("tenancy", "trading", "bot-station"):
        w(f"## {domain}")
        w("")
        for table in sorted(meta.tables.values(), key=lambda t: t.name):
            if DOMAIN.get(table.name) != domain:
                continue
            marker = " · tenant-scoped" if table.name in scoped else ""
            w(f"### `{table.name}`{marker}")
            w("")
            if table.name in WHY:
                w(WHY[table.name])
                w("")
            w("| column | type | null | notes |")
            w("| --- | --- | --- | --- |")
            for col in table.columns:
                bits = []
                if col.primary_key:
                    bits.append("**PK**")
                for fk in col.foreign_keys:
                    bits.append(f"FK → `{fk.column.table.name}`")
                if col.unique:
                    bits.append("unique")
                note = COLUMN_WHY.get((table.name, col.name))
                if note:
                    bits.append(note)
                w(f"| `{col.name}` | {col.type} | "
                  f"{'yes' if col.nullable else 'no'} | {' · '.join(bits)} |")
            w("")

            uniques = [c for c in table.constraints
                       if c.__class__.__name__ == "UniqueConstraint"]
            checks = [c for c in table.constraints
                      if c.__class__.__name__ == "CheckConstraint"]
            if uniques:
                w("**Unique:** " + ", ".join(
                    f"`({', '.join(col.name for col in c.columns)})`"
                    for c in uniques))
                w("")
            if checks:
                w("**Checks:** " + ", ".join(f"`{c.name}`" for c in checks))
                w("")
            if table.indexes:
                w("**Indexes:** " + ", ".join(
                    f"`{i.name}`" for i in sorted(table.indexes,
                                                  key=lambda i: i.name or "")))
                w("")

    w("## Conventions")
    w("")
    w("- **Timestamps are naive UTC**, one convention, converted only at the")
    w("  edge. SQLite does not round-trip timezone info -- an aware datetime")
    w("  goes in and a naive one comes back. The India signal bug in the old")
    w("  build was exactly this.")
    w("- **Constraints are named**, via a metadata naming convention. SQLite")
    w("  cannot ALTER a constraint; it rebuilds the table, and it can only do")
    w("  that when every constraint has a name.")
    w("- **Status values are CHECK constraints**, not foreign keys to a")
    w("  two-row lookup table.")
    w("- **No soft deletes, no EAV, no generic audit table.** Anything that")
    w("  could not be justified from a Phase 1 finding or a Phase 2 rule is")
    w("  not here.")
    w("")
    w("## Migrations")
    w("")
    w("Alembic, clean baseline. `alembic upgrade head`, and the app refuses to")
    w("serve if the schema is not current -- an application on a half-migrated")
    w("database answers, and the answers are wrong.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(PROJECT)} "
          f"({len(meta.tables)} tables, {len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
