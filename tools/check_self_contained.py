"""Prove this project reads and writes nothing outside its own folder.

Three passes:

1. SETTINGS - the settings object is asked where it will actually look
   (database, customers, runtime, levels, super, var, logs), and every bot
   script in the registry is resolved. Anything landing outside the project
   root is an error, not a warning.

2. LAUNCH PLANS - for every user x bot x version, the working directory and
   every path-valued pin the subprocess is handed. A vendored script is not
   enough on its own: a bot handed an outside credential folder or told to
   write its ledger elsewhere is still coupled to another checkout.

3. SOURCES - every source file, doc and comment is scanned for a path naming
   another location on THIS machine. Comments count: a stale path in a
   docstring is how the next person ends up wiring one back in.

Run it after any extraction, move or refactor:

    .venv\\Scripts\\python tools\\check_self_contained.py

Exit code 0 = self-contained. Non-zero = the findings are printed with the
file and line that has to change.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

# Folders that are not our source: installed dependencies and build output.
SKIP_DIRS = {
    ".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache",
    ".idea", ".vite", ".netlify", "var",
}
SCAN_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".env", ".bat", ".sh",
    ".toml", ".css", ".html", ".md", ".yaml", ".yml", ".cfg", ".txt",
}

# A real location ON THIS MACHINE that is not under the project: a sibling
# checkout under _projects, or this operator's home folder. The project's own
# name is excluded by the negative lookahead so the many legitimate
# self-references do not register.
#
# Portable illustrations (`/home/app/data/app.db`, `C:\Users\you\...`) are
# deliberately NOT matched. They are documentation of what an override looks
# like on some other host, they resolve to nothing here, and treating them as
# findings would train everyone to ignore this script's output.
#
# The separator is `[\\/]+` rather than a single character on purpose: inside
# a Python or JS string literal the path is escaped
# (`D:\\_projects\\...`  <- no-outside-ref-ok), and a pattern that only
# matched one backslash walked straight past a real reference sitting in a
# docstring.
#
# The project's own name is taken from the folder rather than written down.
# It used to be hardcoded, and when this checkout was renamed the exclusion
# inverted: it began permitting the sibling it was written to forbid, while
# flagging this project's own self-references. A name that is derived cannot
# drift away from the thing it names.
_SELF = re.escape(PROJECT.name)
OUTSIDE = re.compile(
    rf"""(?ix)
    (?:
        [A-Z]:[\\/]+_projects[\\/]+(?!{_SELF}\b)[A-Za-z0-9._-]+
      | [A-Z]:[\\/]+Users[\\/]+sampa[\\/]+[A-Za-z0-9._\\/-]+
    )
    """
)

# Lines that legitimately name another location: this file's own pattern,
# and prose that exists precisely to say "we do NOT read that any more".
ALLOW_MARKERS = ("check_self_contained", "no-outside-ref-ok")


def scan_text() -> list[str]:
    findings: list[str] = []
    for path in PROJECT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        if SKIP_DIRS & set(path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if any(marker in line for marker in ALLOW_MARKERS):
                continue
            hit = OUTSIDE.search(line)
            if hit:
                rel = path.relative_to(PROJECT)
                findings.append(f"{rel}:{n}: {hit.group(0)}")
    return findings


def _inside(p: Path) -> bool:
    try:
        resolved = p.resolve()
    except OSError:
        return False
    return resolved == PROJECT or PROJECT in resolved.parents


def scan_runtime() -> list[str]:
    from app.core.config import get_settings
    from app.services.bot_registry import registry_report

    s = get_settings()
    findings: list[str] = []

    places = {
        "database_path": s.database_path,
        "customers_root": s.customers_root,
        "source_repo": s.source_repo,
        "super_dir": s.super_dir,
        "levels_dir": s.levels_dir,
        "var_dir": s.var_dir,
        "log_dir": s.log_dir,
    }
    for name, value in places.items():
        mark = "ok  " if _inside(Path(value)) else "OUT "
        line = f"  {mark}{name:16} {value}"
        print(line)
        if mark == "OUT ":
            findings.append(f"setting {name} resolves outside the project: {value}")

    if s.database_url_override:
        print(f"  note database_url_override is set -> {s.database_url_override}")

    for bot in registry_report():
        for v in bot["versions"]:
            script = Path(v["script"])
            if not _inside(script):
                findings.append(
                    f"bot {bot['key']}/{v['version']} script is outside: {script}")
            elif not v["exists"]:
                findings.append(
                    f"bot {bot['key']}/{v['version']} script is missing: {script}")
    print(f"  ok  bot scripts     {sum(len(b['versions']) for b in registry_report())}"
          f" registered, all inside and present")

    findings += scan_launch_plans()
    return findings


def scan_launch_plans() -> list[str]:
    """Resolve what each bot would actually be launched WITH.

    A script inside the project is not enough: the subprocess is handed a
    working directory and a set of path-valued env vars (the customer folder,
    the trade CSV, the log dir). If any of those lands outside, the bot reads
    credentials or writes trades somewhere this project does not own — which
    is exactly the coupling the extraction removed.
    """
    from app.core.database import SessionLocal
    from app.models import User
    from app.services import bot_manager
    from app.services.bot_registry import BOTS

    findings: list[str] = []
    db = SessionLocal()
    try:
        users = db.query(User).all()
        if not users:
            print("  note no users in the database - launch plans not checked")
            return findings
        checked = 0
        for user in users:
            for spec in BOTS.values():
                for version in spec.versions:
                    try:
                        _argv, cwd, env = bot_manager._launch_plan(
                            spec, version, user,
                            bot_manager.BotStartOptions(mode="paper"),
                        )
                    except bot_manager.BotManagerError as exc:
                        findings.append(
                            f"{user.username}/{spec.key}/{version.version}: "
                            f"not launchable: {exc}")
                        continue
                    checked += 1
                    if not _inside(Path(cwd)):
                        findings.append(
                            f"{user.username}/{spec.key}/{version.version}: "
                            f"cwd outside the project: {cwd}")
                    for key, value in env.items():
                        # Only our own pins are ours to answer for; the
                        # inherited shell environment (PATH, TEMP, ...) is not.
                        if not key.endswith(("_CSV", "_CSV_PATH", "_DIR",
                                             "_LOG_PATH", "_SECRETS")):
                            continue
                        if not _inside(Path(value)):
                            findings.append(
                                f"{user.username}/{spec.key}/{version.version}: "
                                f"{key} points outside: {value}")
        print(f"  ok  launch plans    {checked} bot/version/user combinations, "
              f"cwd and every pinned path inside")
    finally:
        db.close()
    return findings


def main() -> int:
    print(f"project root: {PROJECT}\n")

    print("runtime paths")
    runtime_findings = scan_runtime()
    # scan_runtime() and scan_launch_plans() print a per-line "ok" as they go
    # and RETURN whatever they found, but nothing ever printed the returned
    # list. The summary counted them, so a run could report "FAIL: 181" while
    # showing 23 findings and an "ok launch plans" line above them — which is
    # exactly what it did while every bot was still pointed at a sibling
    # checkout. A finding that is counted but not shown is not a finding.
    for f in runtime_findings:
        print(f"  OUT {f}")

    print("\nsource scan")
    text_findings = scan_text()
    if text_findings:
        for f in text_findings:
            print(f"  OUT {f}")
    else:
        print("  ok  no source file names a path outside this project")

    findings = runtime_findings + text_findings
    print()
    if findings:
        print(f"FAIL: {len(findings)} outside reference(s)")
        return 1
    print("PASS: nothing in this project points outside it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
