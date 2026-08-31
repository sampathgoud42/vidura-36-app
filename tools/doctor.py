"""Prove this copy is self-contained and ready to run.

    python tools/doctor.py            # or: .venv/bin/python tools/doctor.py

Exit code 0 = nothing outside this folder is needed. Non-zero = a real
problem, printed with what to do about it. Run it after copying the project
to a new machine, and after anything that moves files or paths around.

Its companion is ``tools/check_self_contained.py``, which goes further on
the one question this file answers loosely: it resolves every bot LAUNCH
PLAN (working directory, credential folder, ledger paths) rather than only
the settings, and its pattern cannot false-positive. Run both.

Checks, in the order a new machine fails them:

    ENV      interpreter, virtualenv, dependencies
    PATHS    every resolved setting points inside this folder
    SOURCE   no code or config references a path outside it
    DATA     the runtime, credentials and database that were vendored in
    BOTS     the Bot Station: every bot script resolves, Kalshi keys
    LAUNCH   the .bat/.sh pairs, and the line endings each OS needs
    DESK     a built UI for the API to serve

WARN never fails the run: an optional piece (Node, the flashAlpha key, a
customer folder for a user in the database) is missing but the desk degrades
gracefully without it.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = os.name == "nt"

# Extensions worth scanning for stray absolute paths. Binary assets, the
# venv and node_modules are excluded by the walker below.
SCAN_EXT = {".py", ".js", ".jsx", ".json", ".css", ".html", ".bat", ".sh",
            ".env", ".config", ".toml", ".txt", ".cfg", ".ini"}
SKIP_DIRS = {".venv", "node_modules", "dist", "__pycache__", ".git",
             ".pytest_cache", "var", "cache", ".idea", ".vscode", "tools"}

# A Windows drive path, or a POSIX path under a root real deployments use.
# The first segment must start with a word character, which is what keeps
# documentation ellipses ("D:\..." / "/home/...") from reading as paths.
#
# Two guards stop this reading source code as filesystem paths, both learned
# from real false positives once the vendored bots landed here:
#
#   (?<![\w\\])  - the drive letter may not be the tail of a word or follow a
#                  backslash. Without it, "resolve:\n" scans as drive "e:" and
#                  the regex r"\d\d:\d\d" as drive "d:".
#   a second separator is required - a genuine path names a folder AND
#                  something in it. "X:\n" never does; a sibling checkout
#                  path always does  (no-outside-ref-ok: the example that
#                  used to sit here was itself flagged by the companion
#                  audit, which is the point of both).
#                  A bare "D:\foo" is missed, which is the right
#                  trade: a scanner that cries wolf gets ignored, and
#                  tools/check_self_contained.py catches the cases that matter
#                  with a pattern that cannot false-positive at all.
ABS_PATH = re.compile(
    r"""(?:(?<![\w\\])[A-Za-z]:[\\/](?![\\/])\w[\w .-]*[\\/][\w .\\/-]*"""
    r"""|/(?:home|srv|Users|opt|mnt)/\w[\w./-]*)""")

_failures: list[str] = []
_warnings: list[str] = []

# ASCII markers, deliberately. A Windows console (and a redirected stdout,
# which is worse: it raises rather than mangling) defaults to cp1252, where
# a tick character is not encodable at all. Deploy output has to survive
# being piped into a log file.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # pragma: no cover
    pass


def ok(section: str, msg: str) -> None:
    print(f"  [ ok ] {msg}")


def fail(section: str, msg: str, fix: str = "") -> None:
    print(f"  [FAIL] {msg}")
    if fix:
        print(f"         -> {fix}")
    _failures.append(f"{section}: {msg}")


def warn(section: str, msg: str, fix: str = "") -> None:
    print(f"  [warn] {msg}")
    if fix:
        print(f"         -> {fix}")
    _warnings.append(f"{section}: {msg}")


def header(name: str) -> None:
    print(f"\n{name}")


# --------------------------------------------------------------------------

def check_env() -> None:
    header("ENV")
    if sys.version_info < (3, 12):
        fail("ENV", f"Python {sys.version.split()[0]} is too old",
             "install Python 3.12+ and re-run setup")
    else:
        ok("ENV", f"Python {sys.version.split()[0]}")

    venv_py = ROOT / (".venv/Scripts/python.exe" if IS_WINDOWS else ".venv/bin/python")
    if not venv_py.is_file():
        fail("ENV", "no virtualenv at .venv/",
             "run setup.bat (Windows) or ./setup.sh")
        return
    ok("ENV", "virtualenv present")

    inside = Path(sys.prefix).resolve() == (ROOT / ".venv").resolve()
    missing = []
    for mod in ("fastapi", "uvicorn", "sqlalchemy", "pydantic_settings",
                "requests", "dotenv", "psutil", "pandas", "yfinance"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if not inside:
        warn("ENV", "not running inside the project venv, so the dependency "
                    "check reflects a different interpreter",
             f"re-run as: {venv_py} tools/doctor.py")
    elif missing:
        fail("ENV", f"missing dependencies: {', '.join(missing)}",
             "re-run setup, or: .venv/bin/pip install -r requirements.txt")
    else:
        ok("ENV", "all backend dependencies importable")


def check_paths() -> None:
    header("PATHS")
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from app.core.config import get_settings
    except Exception as exc:                      # noqa: BLE001
        fail("PATHS", f"the app will not import: {exc}",
             "run setup first; the dependencies may be missing")
        return

    s = get_settings()
    ok("PATHS", f"settings load ({s.app_name} {s.app_version})")
    for label, value in [
        ("database", s.database_path),
        ("runtime", s.source_repo),
        ("customers", s.customers_root),
        ("levels", s.levels_dir),
        ("var", s.var_dir),
    ]:
        p = Path(value).resolve()
        if p == ROOT or ROOT in p.parents:
            ok("PATHS", f"{label:10} {p.relative_to(ROOT)}")
        else:
            fail("PATHS", f"{label} points OUTSIDE the project: {p}",
                 f"unset the matching TBOT_* override in .env")

    if s.paper_only:
        ok("PATHS", "paper-only: every order goes to the Tradier sandbox")
    else:
        warn("PATHS", "LIVE TRADING is unlocked (TBOT_PAPER_ONLY=false in .env)",
             "remove that line from .env to force paper-only")


def _scan_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in SCAN_EXT or name.startswith(".env"):
                yield p


def _blank_docstrings(text: str) -> str:
    """Blank out every docstring, keeping line numbers intact.

    Documentation is where this project explains the machines it came from
    and the path formats it accepts, so those lines mention absolute paths
    on purpose. Only code that could actually OPEN such a path matters.
    """
    import ast

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    lines = text.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if not (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            continue
        for i in range(first.lineno - 1, (first.end_lineno or first.lineno)):
            if 0 <= i < len(lines):
                lines[i] = ""
    return "\n".join(lines)


def check_source() -> None:
    header("SOURCE")
    root_s = str(ROOT)
    hits: list[str] = []
    scanned = 0
    for path in _scan_files():
        # tests/ is fixture data by definition: it asserts that BOTH path
        # conventions parse, so it contains Windows and POSIX paths on
        # purpose and none of it runs in production.
        if path.relative_to(ROOT).parts[0] == "tests":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        if path.suffix == ".py":
            text = _blank_docstrings(text)
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(("#", "//", "*", "REM ", "rem ")):
                continue
            for m in ABS_PATH.finditer(line):
                found = m.group(0)
                if found.replace("/", os.sep).startswith(root_s):
                    continue                      # our own folder is fine
                hits.append(f"{path.relative_to(ROOT)}:{lineno}: {found}")
    if hits:
        fail("SOURCE", f"{len(hits)} absolute path(s) outside the project",
             "each one is a machine this copy would depend on - remove it")
        for h in hits[:12]:
            print(f"      {h}")
        if len(hits) > 12:
            print(f"      ... and {len(hits) - 12} more")
    else:
        ok("SOURCE", f"no external absolute paths in {scanned} scanned files")


def check_data() -> None:
    header("DATA")
    runtime = ROOT / "runtime"
    for sub, what in [
        ("super_research/super_signal_bot.py", "signal engine"),
        ("super_research/super_research.config", "signal registry"),
        ("stock-trade/levels_watcher.py", "level-cross watcher"),
    ]:
        p = runtime / sub
        (ok if p.is_file() else fail)(
            "DATA", f"{what}: runtime/{sub}" if p.is_file()
            else f"missing {what}: runtime/{sub}")

    customers = ROOT / "customers"
    folders = sorted(p.name for p in customers.iterdir() if p.is_dir()) \
        if customers.is_dir() else []
    if not folders:
        fail("DATA", "customers/ is empty - no credentials to trade with",
             "copy each operator's folder (.env, .sam, *.pem) into customers/")
    else:
        ok("DATA", f"credential folders: {', '.join(folders)}")
        for name in folders:
            envs = list((customers / name).glob("*.env")) \
                + [p for p in [customers / name / ".env"] if p.is_file()]
            if not envs:
                warn("DATA", f"customers/{name} has no .env - that user cannot trade")
                continue
            body = envs[0].read_text(encoding="utf-8", errors="replace")
            has_sandbox = "TRADIER_SANDBOX_TOKEN" in body
            has_live = ("TRADIER_PROD_TOKEN" in body
                        or "TRADIER_ACCESS_TOKEN" in body)
            venues = [v for v, on in (("sandbox", has_sandbox), ("live", has_live)) if on]
            if venues:
                ok("DATA", f"customers/{name}: Tradier {' + '.join(venues)}")
            else:
                warn("DATA", f"customers/{name}: no Tradier keys in {envs[0].name}")

    db = ROOT / "var" / "app.db"
    if db.is_file():
        try:
            import sqlite3

            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            users = con.execute("SELECT username, user_root_folder FROM users").fetchall()
            pos = con.execute("SELECT COUNT(*) FROM tradier_positions").fetchone()[0]
            con.close()
            ok("DATA", f"database: {len(users)} user(s), {pos} position row(s)")
            for username, root in users:
                p = Path(root.replace("\\", "/"))
                try:
                    resolved = p.resolve()
                except OSError:
                    resolved = p
                inside = (resolved == customers.resolve()
                          or customers.resolve() in resolved.parents) \
                    if customers.is_dir() else False
                if inside:
                    continue
                if p.is_dir():
                    # The dangerous case: the path RESOLVES, so nothing looks
                    # broken, but it is another copy's credential folder.
                    fail("DATA",
                         f"user '{username}' reads credentials from OUTSIDE "
                         f"this project: {root}",
                         "start the API once - it repoints roots to "
                         "customers/<name> on boot")
                else:
                    warn("DATA", f"user '{username}' points at a missing folder: {root}",
                         "the API repoints it to customers/<name> on boot when one exists")
        except Exception as exc:                  # noqa: BLE001
            warn("DATA", f"database present but unreadable: {exc}")
    else:
        warn("DATA", "var/app.db absent - the API creates an empty one on first "
                     "boot, with no users or history")


def check_bots() -> None:
    """The Bot Station's own preconditions.

    A registry entry that points at nothing reports ``exists: false`` and
    503s the moment someone presses start, so the scripts are resolved here
    rather than at the first click. Kalshi credentials are checked the same
    way the Tradier ones are above: without a key ID and a PEM the bots
    launch and then fail to authenticate, which reads as a mysterious
    crash-on-start instead of "you have no credentials".
    """
    header("BOTS")
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from app.services.bot_registry import registry_report
    except Exception as exc:  # noqa: BLE001 - a bad import IS the finding
        fail("BOTS", f"bot registry will not import: {exc}",
             "the Bot Station cannot start any bot in this state")
        return

    missing: list[str] = []
    outside: list[str] = []
    total = 0
    for bot in registry_report():
        for v in bot["versions"]:
            total += 1
            script = Path(v["script"])
            if not v["exists"]:
                missing.append(f"{bot['key']}/{v['version']} -> {script}")
            elif ROOT not in script.resolve().parents:
                outside.append(f"{bot['key']}/{v['version']} -> {script}")
    if missing:
        fail("BOTS", f"{len(missing)} bot script(s) missing on disk",
             "re-vendor runtime/prediction-trade/ - the desk will 503 on start")
        for m in missing[:6]:
            print(f"      {m}")
    elif outside:
        fail("BOTS", f"{len(outside)} bot script(s) live outside this project",
             "this copy is not self-contained")
        for m in outside[:6]:
            print(f"      {m}")
    else:
        ok("BOTS", f"{total} bot script(s) across "
                   f"{len(registry_report())} families, all vendored here")

    customers = ROOT / "customers"
    folders = sorted(p.name for p in customers.iterdir() if p.is_dir()) \
        if customers.is_dir() else []
    for name in folders:
        folder = customers / name
        env = folder / ".env"
        if not env.is_file():
            continue                    # already reported by check_data
        body = env.read_text(encoding="utf-8", errors="replace")
        has_key = "KALSHI_API_KEY_ID" in body
        has_pem = bool(list(folder.glob("*.pem")))
        if has_key and has_pem:
            ok("BOTS", f"customers/{name}: Kalshi key + private key")
        elif has_key or has_pem:
            warn("BOTS",
                 f"customers/{name}: Kalshi "
                 f"{'key but no *.pem' if has_key else '*.pem but no key id'}"
                 " - bots for this user will fail to authenticate")
        else:
            warn("BOTS", f"customers/{name}: no Kalshi credentials "
                         "- Tradier only, the Bot Station cannot trade for them")


def check_line_endings() -> None:
    header("LAUNCHERS")
    wrong = []
    for path in sorted(ROOT.glob("*.sh")) + sorted(ROOT.glob("*.bat")) \
            + sorted((ROOT / "frontend").glob("dev.*")):
        raw = path.read_bytes()
        has_crlf = b"\r\n" in raw
        want_crlf = path.suffix.lower() in (".bat", ".cmd")
        if has_crlf != want_crlf:
            wrong.append(f"{path.name} is "
                         f"{'CRLF' if has_crlf else 'LF'}, wants "
                         f"{'CRLF' if want_crlf else 'LF'}")
    if wrong:
        fail("LAUNCHERS", f"{len(wrong)} launcher(s) with the wrong line endings",
             "python tools/fix_line_endings.py")
        for w in wrong:
            print(f"      {w}")
    else:
        ok("LAUNCHERS", "*.sh are LF and *.bat are CRLF - both OSes can run them")

    pairs = ("start", "stop", "restart", "status", "setup", "doctor",
             "launch", "url")
    missing = [n for n in pairs
               if not (ROOT / f"{n}.bat").is_file() or not (ROOT / f"{n}.sh").is_file()]
    if missing:
        fail("LAUNCHERS", f"missing .bat/.sh pair(s): {', '.join(missing)}")
    else:
        ok("LAUNCHERS", f"{len(pairs)} .bat/.sh pairs present for both OSes")


def check_desk() -> None:
    header("DESK")
    # dist-v2 is what api_v2 serves; checking dist reported a healthy
    # desk while the API had nothing to serve.
    index = ROOT / "frontend" / "dist-v2" / "index.html"
    if index.is_file():
        assets = ROOT / "frontend" / "dist-v2" / "assets"
        n = len(list(assets.glob("*"))) if assets.is_dir() else 0
        ok("DESK", f"built UI present ({n} asset file(s)) - the API serves it at /")
    else:
        warn("DESK", "frontend/dist-v2 is not built - the API runs with no UI",
             "npm install --prefix frontend && npm run build --prefix frontend")


def main() -> int:
    print(f"Tradier Bot doctor\n  project: {ROOT}")
    check_env()
    check_paths()
    check_source()
    check_data()
    check_bots()
    check_line_endings()
    check_desk()

    print()
    if _failures:
        print(f"FAILED - {len(_failures)} problem(s) must be fixed:")
        for f in _failures:
            print(f"  - {f}")
        if _warnings:
            print(f"({len(_warnings)} warning(s) as well)")
        return 1
    if _warnings:
        print(f"OK with {len(_warnings)} warning(s):")
        for w in _warnings:
            print(f"  - {w}")
        print("\nThis copy is self-contained and will run.")
        return 0
    print("OK - this copy is self-contained and complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
