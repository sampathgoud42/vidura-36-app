"""Which worlds an operator may open.

Read from worlds.json at the project root rather than the database: this is
deployment configuration, not user data. It is one file an admin can edit
and read back, it travels with the folder, and it does not need a migration
to add a world.

The flag is enforced by the app as a HARD STOP, not by hiding the link — an
operator following an old bookmark should be told the world is disabled
rather than left looking at a blank page wondering what broke.

Advisory, not a security boundary: it decides what the UI offers, and every
underlying endpoint stays behind the same login it always was. A disabled
world is "not for you today", not "your credentials cannot reach this".
"""

from __future__ import annotations

import json
import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT
from app.core.database import get_db
from app.models import User

router = APIRouter(prefix="/worlds", tags=["worlds"])
logger = logging.getLogger(__name__)

CONFIG = PROJECT_ROOT / "worlds.json"

# Every world this build ships. A name absent from here is not a world, so a
# typo in worlds.json cannot invent one.
KNOWN = ("tradier-platform", "36-trade-desk", "bot-station")

_CACHE: tuple[float, dict] | None = None
_MUTEX = threading.Lock()
_TTL_S = 10          # short: an admin edits the file and wants it to take


def _load() -> dict:
    """worlds.json, cached briefly so an edit lands without a restart."""
    global _CACHE
    with _MUTEX:
        if _CACHE and time.time() - _CACHE[0] < _TTL_S:
            return _CACHE[1]
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except (OSError, ValueError) as exc:
        # A malformed file must not lock everyone out of everything, so it
        # falls back to permissive and says so loudly.
        logger.error("worlds.json is unreadable (%s) - allowing all worlds", exc)
        data = {}
    with _MUTEX:
        _CACHE = (time.time(), data)
    return data


def resolve(username: str) -> dict:
    cfg = _load()
    fallback = cfg.get("defaults") or {}
    entry = (cfg.get("users") or {}).get(username, fallback)

    allowed = {w: True for w in KNOWN}
    allowed.update({k: bool(v) for k, v in (fallback.get("worlds") or {}).items()
                    if k in KNOWN})
    allowed.update({k: bool(v) for k, v in (entry.get("worlds") or {}).items()
                    if k in KNOWN})

    want = entry.get("default") or fallback.get("default")
    # The landing world must be one they can actually open, or the app would
    # bounce them straight into the hard stop on every visit.
    if want not in allowed or not allowed.get(want):
        want = next((w for w in KNOWN if allowed.get(w)), None)

    return {"worlds": allowed, "default": want,
            "any_enabled": any(allowed.values())}


@router.get("", operation_id="getWorlds")
def get_worlds(user_id: str = Query(...), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    out = resolve(user.username)
    out["username"] = user.username
    return out
