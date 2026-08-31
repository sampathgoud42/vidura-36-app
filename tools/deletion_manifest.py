"""Phase 9: what can be deleted, and the evidence that it is unused.

Produces the manifest. Deletes NOTHING -- the brief's own precondition is that
Phase 7 tests are green first, and deleting the old backend before the app
cutover would take the live desk down.

    .venv\\Scripts\\python tools\\deletion_manifest.py
"""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".venv", "node_modules", "dist", "__pycache__",
        ".pytest_cache", "var", ".vite"}


def rule(title: str) -> None:
    print(f"\n{title}\n{'=' * len(title)}")


def _norm(src: str) -> str | None:
    """Strip comments and docstrings so drift shows, not formatting."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body.pop(0)
    try:
        return ast.unparse(tree)
    except Exception:                                   # noqa: BLE001
        return None


def duplicate_modules() -> list[tuple[str, list[Path], int]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    lines: dict[str, int] = {}
    for path in PROJECT.rglob("*.py"):
        if SKIP & set(path.parts):
            continue
        try:
            norm = _norm(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if not norm or len(norm) < 200:
            continue
        digest = hashlib.sha1(norm.encode()).hexdigest()
        groups[digest].append(path)
        lines[digest] = len([l for l in norm.splitlines() if l.strip()])
    return [(d, sorted(v), lines[d]) for d, v in groups.items() if len(v) > 1]


def duplicate_docs() -> list[tuple[Path, Path, float]]:
    import difflib

    out = []
    for pattern in ("runtime/super_research/*_research/README.md",
                    "runtime/prediction-trade/kalshi/commodities/*/ENGINE.md"):
        files = sorted(PROJECT.glob(pattern))
        if len(files) < 2:
            continue
        base = files[0]
        base_text = base.read_text(encoding="utf-8", errors="replace")
        for other in files[1:]:
            ratio = difflib.SequenceMatcher(
                None, base_text,
                other.read_text(encoding="utf-8", errors="replace")).ratio()
            if ratio >= 0.90:
                out.append((base, other, ratio))
    return out


def generated_reports() -> list[tuple[Path, int]]:
    """Machine-written research output living in the docs tree."""
    out = []
    for path in PROJECT.glob("runtime/**/REPORT.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"Super-Signal research", text[:400]):
            out.append((path, len(text)))
    return sorted(out, key=lambda p: -p[1])


def unreferenced_backend_modules() -> list[Path]:
    """Old-build modules nothing in the NEW tree imports.

    Deliberately conservative: a module is only listed when no file outside
    its own package mentions its name at all.
    """
    old = sorted((PROJECT / "backend" / "app" / "services").glob("*.py"))
    haystack = ""
    for path in PROJECT.rglob("*.py"):
        if SKIP & set(path.parts) or "services" in path.parts:
            continue
        haystack += path.read_text(encoding="utf-8", errors="replace")
    return [p for p in old
            if p.stem != "__init__" and p.stem not in haystack]


def main() -> int:
    print(f"Phase 9 deletion manifest - {PROJECT}")
    print("NOTHING IS DELETED BY THIS SCRIPT. It reports and cites evidence.")

    rule("A. DUPLICATED MODULES (byte-identical after normalisation)")
    dupes = duplicate_modules()
    wasted = 0
    for _, paths, n in sorted(dupes, key=lambda d: -len(d[1]) * d[2]):
        wasted += n * (len(paths) - 1)
        rel = paths[0].relative_to(PROJECT)
        print(f"\n  {rel.name:<20} {len(paths)} copies x {n} lines")
        print(f"    canonical : {rel}")
        for p in paths[1:]:
            print(f"    duplicate : {p.relative_to(PROJECT)}")
    print(f"\n  TOTAL redundant lines: {wasted}")
    print("  EVIDENCE: identical after stripping comments and docstrings.")
    print("  BLOCKED: these are vendored engines the bots import by path.")
    print("  Collapsing them is a code change, not a deletion, and belongs")
    print("  with the runtime refactor rather than with cleanup.")

    rule("B. DUPLICATE DOCUMENTS (>= 90% identical)")
    docs = duplicate_docs()
    for base, other, ratio in docs:
        print(f"  {ratio:.0%}  {other.relative_to(PROJECT)}")
        print(f"        superseded by {base.relative_to(PROJECT)}")
    print(f"\n  {len(docs)} file(s). EVIDENCE: measured similarity.")
    print("  SAFE TO DELETE once a single canonical doc replaces them.")

    rule("C. GENERATED RESEARCH OUTPUT IN THE DOCS TREE")
    reports = generated_reports()
    total = sum(n for _, n in reports)
    for path, n in reports[:6]:
        print(f"  {n/1024:>7.0f} KB  {path.relative_to(PROJECT)}")
    if len(reports) > 6:
        print(f"  ... and {len(reports) - 6} more")
    print(f"\n  {len(reports)} files, {total/1024/1024:.2f} MB total.")
    print("  EVIDENCE: machine-written, regenerated by the research engines.")
    print("  SAFE TO DELETE, but they are OUTPUT rather than dead code -- the")
    print("  question is whether you want the history, not whether it is used.")

    rule("D. OLD BACKEND MODULES NOTHING NEW IMPORTS")
    orphans = unreferenced_backend_modules()
    for path in orphans:
        print(f"  {path.relative_to(PROJECT)}")
    print(f"\n  {len(orphans)} module(s).")
    print("  BLOCKED: app.main still serves the live desk from these. They")
    print("  become deletable at cutover, not before.")

    rule("E. WHAT THE BRIEF ASKS FOR THAT IS NOT YET SAFE")
    print("  - CSV-based state and the code that reads it")
    print("      the vendored bots still WRITE those CSVs; removing the")
    print("      readers means changing the bots, which Phase 2 put out of")
    print("      scope until you say otherwise")
    print("  - the old migration history")
    print("      there is none to delete: Alembic started from a clean")
    print("      baseline and the old build had no migration tool at all")
    print("  - the old backend (app/api, app/services, app/models)")
    print("      blocked on cutover")

    rule("PRECONDITION CHECK")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/rebuild", "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=PROJECT, capture_output=True, text=True, timeout=1800)
    tail = [l for l in result.stdout.strip().splitlines() if "passed" in l
            or "failed" in l]
    print(f"  Phase 7 suite: {tail[-1] if tail else 'could not determine'}")
    print("\n  The brief: 'Do not delete anything until Phase 7 tests are")
    print("  green.' Until they are, this manifest is the deliverable and")
    print("  the deletions are not.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
