"""Subprocess bootstrap for legacy 38trades bot scripts.

Run as:  python bot_launcher.py <target_script.py> [argv...]

Why it exists: commit 4e19bd1 in the source repo renamed
``bot_kalshi_btc15.py`` to ``v4_bot_kalshi_btc15.py`` but the sports bots and
kalshi_sports.py still ``import bot_kalshi_btc15``.  This bootstrap installs a
lazy meta-path finder that satisfies that import from the renamed file, then
executes the target script exactly as ``python target.py`` would.

The finder is lazy on purpose: the legacy module reads credentials from
``os.environ`` at import time, and the bots load their customer .env *before*
importing it — an eager import here would freeze empty credentials.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from pathlib import Path

LEGACY_NAME = "bot_kalshi_btc15"
RENAMED_FILE = "v4_bot_kalshi_btc15.py"


class _LegacyAliasFinder(MetaPathFinder, Loader):
    def __init__(self, btc15_dir: Path):
        self._btc15_dir = btc15_dir

    def find_spec(self, fullname, path=None, target=None):
        if fullname != LEGACY_NAME:
            return None
        # If the original file still exists (older worktrees), stand aside.
        if (self._btc15_dir / f"{LEGACY_NAME}.py").is_file():
            return None
        renamed = self._btc15_dir / RENAMED_FILE
        if not renamed.is_file():
            return None
        return importlib.util.spec_from_file_location(LEGACY_NAME, renamed)


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: bot_launcher.py <target_script.py> [args...]", file=sys.stderr)
        sys.exit(2)
    target = Path(sys.argv[1]).resolve()
    if not target.is_file():
        print(f"bot_launcher: script not found: {target}", file=sys.stderr)
        sys.exit(2)

    script_dir = target.parent
    # Make sibling modules importable exactly like a direct launch would.
    sys.path.insert(0, str(script_dir))

    # Honor the btc15-family contract "CWD supplies credentials": the legacy
    # modules call bare load_dotenv(), whose frame-based walk-up starts at
    # the SCRIPT dir and never reaches the customer folder we chdir'd into.
    # Preload it here; the modules' later override=False loads won't clobber.
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        try:
            from dotenv import load_dotenv

            load_dotenv(cwd_env, override=True)
        except ImportError:
            pass

    # Locate the btc15 dir relative to the target (works for btc15, btc60 and
    # sports scripts, which all live under prediction-trade/kalshi/...).
    for ancestor in [script_dir, *script_dir.parents]:
        candidate = ancestor / "btc" / "btc15"
        if candidate.is_dir():
            sys.meta_path.insert(0, _LegacyAliasFinder(candidate))
            sys.path.insert(1, str(candidate))
            break
        if (ancestor / RENAMED_FILE).is_file():
            sys.meta_path.insert(0, _LegacyAliasFinder(ancestor))
            break

    # Re-shape argv so the target believes it was launched directly.
    sys.argv = [str(target)] + sys.argv[2:]
    import runpy

    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
