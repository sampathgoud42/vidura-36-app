"""python -m bot_best_pair [--check] -- see cli.py."""

import sys
from pathlib import Path

# backend/ on the path, so this also runs as `python backend/bot_best_pair`.
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from bot_best_pair.cli import main  # noqa: E402

raise SystemExit(main())
