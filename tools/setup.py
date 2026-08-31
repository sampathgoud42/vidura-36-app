"""One-time setup on a fresh machine.

Run with the SYSTEM python (this is what creates the virtualenv):

    python tools/setup.py

Idempotent — safe to re-run after pulling changes. Steps:

    1. .venv/ + backend dependencies
    2. .env from .env.example, if absent
    3. frontend/node_modules + a production build of the desk
    4. a self-containment audit (tools/doctor.py)

Node is optional. Without it the API still runs and is fully usable through
/docs; you just have no web desk until a build exists. A build produced on
another machine ships fine in frontend/dist-v2 — it is plain static files.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = os.name == "nt"
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")

MIN_PYTHON = (3, 12)

# A Windows console defaults to cp1252, and a redirected stdout raises there
# rather than mangling. Paths printed below can contain anything.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # pragma: no cover
    pass


def step(n: int, text: str) -> None:
    print(f"\n[{n}/4] {text}")


def run(cmd: list[str], **kw) -> int:
    printable = " ".join(str(c) for c in cmd)
    print(f"    $ {printable}")
    return subprocess.call([str(c) for c in cmd], cwd=str(ROOT), **kw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-frontend", action="store_true",
                    help="do not touch npm even if it is installed")
    ap.add_argument("--skip-audit", action="store_true")
    args = ap.parse_args()

    print(f"Tradier Bot setup\n  project: {ROOT}")

    if sys.version_info < MIN_PYTHON:
        print(f"\nPython {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required; this is "
              f"{sys.version.split()[0]} at {sys.executable}")
        return 1

    # ---- 1. virtualenv + dependencies ---------------------------------
    step(1, "Python environment")
    if VENV_PY.is_file():
        print(f"    .venv already exists ({VENV_PY})")
    else:
        if run([sys.executable, "-m", "venv", str(VENV)]) != 0:
            print("    FAILED to create the virtualenv")
            return 1
    if run([VENV_PY, "-m", "pip", "install", "--upgrade", "pip", "-q"]) != 0:
        print("    WARNING: could not upgrade pip; continuing")
    if run([VENV_PY, "-m", "pip", "install", "-r",
            str(ROOT / "requirements.txt"), "-q"]) != 0:
        print("    FAILED to install backend dependencies")
        return 1
    print("    backend dependencies installed")

    # ---- 2. machine configuration -------------------------------------
    step(2, "Configuration")
    env = ROOT / ".env"
    if env.is_file():
        print("    .env already present, left untouched")
    else:
        shutil.copy2(ROOT / ".env.example", env)
        print("    .env created from .env.example (paper-only by default)")

    # ---- 3. the desk ---------------------------------------------------
    step(3, "Web desk")
    npm = shutil.which("npm.cmd" if IS_WINDOWS else "npm") or shutil.which("npm")
    # dist-v2, which is where api_v2 serves the desk from. This built
    # into frontend/dist -- the retired app's output -- so a fresh setup
    # finished "successfully" and left the API with no UI to serve.
    built = ROOT / "frontend" / "dist-v2" / "index.html"
    if args.skip_frontend:
        print("    skipped (--skip-frontend)")
    elif npm is None:
        print("    npm not found - skipping.")
        if built.is_file():
            print("    frontend/dist-v2 is already built, so the desk still works.")
        else:
            print("    The API will run without a UI. Install Node 18+ and re-run")
            print("    this script to build the desk.")
    else:
        if run([npm, "install", "--prefix", "frontend"]) != 0:
            print("    FAILED: npm install")
            return 1
        # --outDir dist-v2: vite's own default is dist, and that is the
        # retired app's output directory. api_v2 serves dist-v2.
        if run([npm, "run", "build", "--prefix", "frontend",
                "--", "--outDir", "dist-v2"]) != 0:
            print("    FAILED: npm run build")
            return 1
        print("    desk built into frontend/dist-v2 (the API serves it)")

    # ---- 4. audit -------------------------------------------------------
    step(4, "Self-containment audit")
    if args.skip_audit:
        print("    skipped (--skip-audit)")
    else:
        rc = run([VENV_PY, str(ROOT / "tools" / "doctor.py")])
        if rc != 0:
            print("\nSetup finished, but the audit found problems (above).")
            return rc

    start = "start.bat" if IS_WINDOWS else "./start.sh"
    stop = "stop.bat" if IS_WINDOWS else "./stop.sh"
    print(f"""
Setup complete.

    {start}          start the app        http://127.0.0.1:8790
    {stop}           stop it
    {'status.bat' if IS_WINDOWS else './status.sh'}         see what is running

The desk and the API are the same port: the API serves the built UI.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
