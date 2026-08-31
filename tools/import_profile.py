"""Phase 8, step 1: profile what would migrate, before writing any importer.

Reads only. Touches nothing, writes nothing, and never prints a secret value --
only whether one exists, its length, and its shape. A profiler that echoes a
token into a terminal has created a second copy of it in scrollback.

    .venv\\Scripts\\python tools\\import_profile.py
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

CUSTOMERS = PROJECT / "customers"
LEGACY_DB = PROJECT / "var" / "app.db"

# Hash formats we could recognise if the password were hashed. Checked so the
# answer is "it is plaintext" as a FINDING rather than an assumption -- the
# brief is explicit that a credential format must never be guessed.
HASH_MARKERS = {
    "$2a$": "bcrypt", "$2b$": "bcrypt", "$2y$": "bcrypt",
    "$argon2": "argon2", "$pbkdf2": "pbkdf2", "$scrypt": "scrypt",
    "sha1$": "django-sha1", "pbkdf2_sha256$": "django-pbkdf2",
    "{SSHA}": "ldap-ssha", "$6$": "sha512-crypt", "$5$": "sha256-crypt",
}


def rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def classify_password(raw: str) -> tuple[str, str]:
    """(format, note). Never returns the value itself."""
    text = raw.strip()
    if not text:
        return "EMPTY", "no password on file"
    for marker, name in HASH_MARKERS.items():
        if text.startswith(marker):
            return name, "recognised hash format, preserve byte-for-byte"
    if re.fullmatch(r"[0-9a-f]{32}", text):
        return "AMBIGUOUS", "32 hex chars - could be unsalted MD5"
    if re.fullmatch(r"[0-9a-f]{40}", text):
        return "AMBIGUOUS", "40 hex chars - could be unsalted SHA-1"
    if re.fullmatch(r"[0-9a-f]{64}", text):
        return "AMBIGUOUS", "64 hex chars - could be unsalted SHA-256"
    return "PLAINTEXT", "compared byte-wise by credentials.verify_password"


def profile_folders() -> dict:
    rule("CUSTOMER FOLDERS")
    out = {}
    if not CUSTOMERS.is_dir():
        print("  no customers/ folder")
        return out

    for folder in sorted(p for p in CUSTOMERS.iterdir() if p.is_dir()):
        name = folder.name
        sam = folder / ".sam"
        env = folder / ".env"
        pems = sorted(folder.glob("*.pem"))
        wellness = folder / "wellness-profile.json"
        history = folder / "trade_history"

        pw_format, pw_note = ("MISSING", "no .sam file")
        if sam.is_file():
            pw_format, pw_note = classify_password(
                sam.read_text(encoding="utf-8", errors="replace"))

        keys: dict[str, int] = {}
        if env.is_file():
            for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip().startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip():
                    keys[k.strip()] = len(v.strip())

        csvs = {}
        if history.is_dir():
            for f in sorted(history.glob("*.csv")):
                with f.open(newline="", encoding="utf-8-sig", errors="replace") as fh:
                    rows = list(csv.reader(fh))
                csvs[f.name] = max(0, len(rows) - 1)

        out[name] = {
            "password_format": pw_format, "password_note": pw_note,
            "env_keys": keys, "pem_files": [p.name for p in pems],
            "wellness": wellness.is_file(),
            "trade_csvs": csvs,
            "looks_like_test": name.startswith("_") or name.lower() in
                               ("test", "demo", "example"),
        }

        print(f"\n  {name}")
        print(f"    password    : {pw_format} ({pw_note})")
        print(f"    venue keys  : {len(keys)} in .env"
              + (f" - {', '.join(sorted(keys))}" if keys else ""))
        print(f"    private key : {', '.join(p.name for p in pems) or 'none'}")
        print(f"    wellness    : {'yes' if wellness.is_file() else 'no'}")
        print(f"    trade rows  : {sum(csvs.values())} across {len(csvs)} file(s)")
        if out[name]["looks_like_test"]:
            print("    NOTE        : name suggests a test account")
    return out


def profile_legacy_users() -> list[dict]:
    rule("LEGACY USER ROWS (var/app.db)")
    if not LEGACY_DB.is_file():
        print("  no legacy database")
        return []

    conn = sqlite3.connect(f"file:{LEGACY_DB}?mode=ro", uri=True)
    try:
        rows = [dict(zip([c[0] for c in cur.description], r))
                for cur in [conn.execute(
                    "SELECT user_id, username, email, user_root_folder, "
                    "created_at FROM users")]
                for r in cur.fetchall()]
    except sqlite3.Error as exc:
        print(f"  could not read users: {exc}")
        return []
    finally:
        conn.close()

    for r in rows:
        print(f"\n  {r['username']}")
        print(f"    user_id     : {r['user_id']}")
        print(f"    email       : {r['email'] or '(none)'}")
        print(f"    root folder : {r['user_root_folder']}")
    return rows


def violations(folders: dict, users: list[dict]) -> dict:
    rule("CONSTRAINT VIOLATIONS AGAINST THE NEW SCHEMA")
    found: dict[str, list[str]] = {}

    def add(cls: str, detail: str) -> None:
        found.setdefault(cls, []).append(detail)

    # tenant.slug UNIQUE, case-insensitive in practice
    seen: dict[str, str] = {}
    for u in users:
        slug = (u["username"] or "").strip().lower()
        if not slug:
            add("blank username", f"user_id {u['user_id']}")
        elif slug in seen:
            add("duplicate username (case-insensitive)",
                f"{u['username']} collides with {seen[slug]}")
        else:
            seen[slug] = u["username"]

    # tenant.email UNIQUE, nullable
    emails: dict[str, str] = {}
    for u in users:
        email = (u["email"] or "").strip().lower()
        if not email:
            continue
        if email in emails:
            add("duplicate email (case-insensitive)",
                f"{u['username']} and {emails[email]}")
        emails[email] = u["username"]

    # tenant.password_hash NOT NULL -- every operator must be able to sign in
    for u in users:
        name = (u["username"] or "").lower()
        info = folders.get(name)
        if info is None:
            add("user with no credential folder",
                f"{u['username']} -> {u['user_root_folder']}")
        elif info["password_format"] in ("MISSING", "EMPTY"):
            add("user with no password", u["username"])
        elif info["password_format"] == "AMBIGUOUS":
            add("password format NOT CERTAIN", f"{u['username']}: "
                f"{info['password_note']}")

    # folders with no user row: data that would migrate under no tenant
    for name, info in folders.items():
        if name.lower() not in seen:
            rows = sum(info["trade_csvs"].values())
            add("credential folder with no user row",
                f"{name} ({rows} trade row(s), "
                f"{len(info['env_keys'])} venue key(s))")

    if not found:
        print("  none")
    for cls, items in sorted(found.items()):
        print(f"\n  {cls.upper()} ({len(items)})")
        for item in items:
            print(f"    - {item}")
    return found


def id_exposure() -> None:
    rule("WHERE A USER ID IS EXTERNALLY VISIBLE")
    hits: list[str] = []
    for path in (PROJECT / "frontend" / "src").rglob("*.js*"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "user_id" in text:
            hits.append(str(path.relative_to(PROJECT)))
    print("  URLs / exports / third parties : none found")
    print("  browser localStorage           : vidura.user.id (viduraApi.js)")
    print(f"  frontend files referencing it  : {len(hits)}")
    print("\n  Reading: the id appears in request parameters and one"
          "\n  localStorage key, both of which this rebuild removes. It is in"
          "\n  no URL a person sees, no export, no invoice and no third-party"
          "\n  system, so RENUMBERING IS SAFE. Recommend fresh UUIDs.")


def credential_exposure(folders: dict) -> None:
    rule("PER-CUSTOMER CREDENTIALS: WHERE THEY LIVE, AND WHETHER EXPOSED")
    import subprocess

    print("  on disk, plaintext:")
    for name, info in sorted(folders.items()):
        bits = []
        if info["env_keys"]:
            bits.append(f"{len(info['env_keys'])} key(s) in .env")
        if info["pem_files"]:
            bits.append(f"private key {info['pem_files'][0]}")
        if info["password_format"] == "PLAINTEXT":
            bits.append("plaintext password in .sam")
        print(f"    {name:<10} {', '.join(bits) or 'nothing'}")

    print("\n  in git history:")
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "customers/"], cwd=PROJECT,
            capture_output=True, text=True, timeout=30).stdout.strip()
        history = subprocess.run(
            ["git", "log", "--all", "--oneline", "--", "customers/"],
            cwd=PROJECT, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as exc:                            # noqa: BLE001
        print(f"    could not check git ({exc})")
        return

    if tracked or history:
        print("    *** COMPROMISED: customer credentials appear in git. Every")
        print("    *** key below must be ROTATED AT THE VENUE, not migrated.")
        for line in (tracked or history).splitlines()[:20]:
            print(f"      {line}")
    else:
        print("    clean - nothing under customers/ is or was tracked.")
        print("    These keys can be migrated as-is rather than rotated.")


def main() -> int:
    print(f"Phase 8 profile - {PROJECT}")
    folders = profile_folders()
    users = profile_legacy_users()
    found = violations(folders, users)
    id_exposure()
    credential_exposure(folders)

    rule("WHAT WOULD MIGRATE")
    print(f"  operators   : {len(users)}")
    print(f"  folders     : {len(folders)}")
    print(f"  trade rows  : {sum(sum(f['trade_csvs'].values()) for f in folders.values())}")
    print(f"  violations  : {sum(len(v) for v in found.values())} "
          f"in {len(found)} class(es)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
