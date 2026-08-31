#!/usr/bin/env python
"""One-shot bootstrap for the freshly onboarded amzn worker.

Builds the B-book from real bars, then emits everything today already fired so
the ticker shows up on the desk immediately instead of after the next session.
Runs detached; its output is _onboard.out beside this file.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def step(name, args):
    print(f"\n=== {name} ===", flush=True)
    r = subprocess.run([sys.executable, *args], cwd=str(HERE))
    print(f"=== {name} exit {r.returncode} ===", flush=True)
    return r.returncode


# iterate.py downloads ~60 days of 5m bars and greedily unions the composites
# that clear its win-rate bar; that IS the playbook, so a failure here leaves
# the ticker registered but silent rather than emitting untested signals.
if step("iterate", ["iterate.py"]) == 0:
    step("backfill", ["amzn_intraday_bot.py", "--backfill-today"])
else:
    print("iterate failed — no B-book, worker will stay quiet", flush=True)
