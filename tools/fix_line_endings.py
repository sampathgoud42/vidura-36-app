"""Normalise line endings so the launchers work on both OSes.

    python tools/fix_line_endings.py            # fix in place
    python tools/fix_line_endings.py --check    # report only, exit 1 if wrong

The rule, and why each half matters:

    *.bat/.cmd  CRLF  cmd.exe tolerates LF for simple one-line commands but
                      mis-parses labels and multi-line blocks, so a script
                      that works today can break the moment it grows a goto.
    everything  LF    A shell script with CRLF fails on Linux in the most
    else              confusing way possible: the shebang becomes
                      "/usr/bin/env sh\\r", and the error names an
                      interpreter that looks correct on screen.

                      Source files genuinely do not care, but consistency
                      does: the extraction scripts rewrite only the files
                      they patch, so without this the tree ends up half CRLF
                      and the next sync's diff reports every line of a file
                      that did not actually change.

This runs at the end of the extraction scripts, because writing a text file
on Windows silently translates "\\n" to "\\r\\n" — which is exactly how
frontend/dev.sh ended up broken for Linux.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", "node_modules", "dist", "__pycache__", ".git",
             ".pytest_cache", "var", "customers"}

WANT_CRLF = {".bat", ".cmd"}
# Source is LF everywhere, matching .gitattributes. Python and Node do not
# care either way, but the extraction scripts rewrite only the files they
# patch — and write_text on Windows turns those into CRLF. Left alone, the
# tree ends up half one and half the other, and the next sync's diff shows
# every line of a file that did not actually change.
WANT_LF = {".sh", ".py", ".js", ".jsx", ".css", ".html", ".json", ".md",
           ".toml", ".cfg", ".ini", ".txt", ".config"}
# Files Linux tooling reads that have no extension to match on, so every
# suffix set above misses them. Not cosmetic for a Dockerfile: the carriage
# return rides along on the last token of the line, so a CRLF
# "CMD exec uvicorn ... --timeout-keep-alive 15" passes an argument that is
# not 15, and the image builds and then fails to start.
WANT_LF_NAMES = {"Dockerfile", ".dockerignore", ".gitattributes",
                 ".gitignore", "Procfile"}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # pragma: no cover
    pass


# runtime/ is vendored VERBATIM from the source checkout, and staying
# byte-identical to it is the point — re-normalising it would churn hundreds
# of files on every sync and make `diff` against the source useless. Its
# launchers are still normalised, since those have to run on both OSes.
VERBATIM_DIRS = {"runtime"}
# npm rewrites this with native endings on every install, so normalising it
# only produces a file that flips back and forth.
GENERATED = {"package-lock.json"}


def targets():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(ROOT).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if path.name in GENERATED:
            continue
        suffix = path.suffix.lower()
        if parts and parts[0] in VERBATIM_DIRS and suffix not in ({".sh"} | WANT_CRLF):
            continue
        if (suffix in WANT_LF or suffix in WANT_CRLF
                or path.name in WANT_LF_NAMES):
            yield path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report without writing; exit 1 if anything is wrong")
    args = ap.parse_args()

    wrong: list[str] = []
    fixed = 0
    checked = 0
    for path in targets():
        raw = path.read_bytes()
        checked += 1
        want_crlf = (path.suffix.lower() in WANT_CRLF
                     and path.name not in WANT_LF_NAMES)
        # Normalise to LF first so mixed endings collapse to one convention.
        body = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        target = body.replace(b"\n", b"\r\n") if want_crlf else body
        if target == raw:
            continue
        rel = path.relative_to(ROOT).as_posix()
        wrong.append(f"{rel} (wants {'CRLF' if want_crlf else 'LF'})")
        if not args.check:
            path.write_bytes(target)
            fixed += 1

    if args.check:
        if wrong:
            print(f"[line-endings] {len(wrong)} file(s) with the wrong endings:")
            for w in wrong:
                print(f"  {w}")
            return 1
        print(f"[line-endings] all {checked} launcher file(s) correct")
        return 0

    if fixed:
        print(f"[line-endings] fixed {fixed} of {checked} file(s):")
        for w in wrong:
            print(f"  {w}")
    else:
        print(f"[line-endings] all {checked} launcher file(s) already correct")
    return 0


if __name__ == "__main__":
    sys.exit(main())
