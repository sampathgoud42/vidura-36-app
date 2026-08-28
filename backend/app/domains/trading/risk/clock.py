"""Session time. One module owns "what time is it for the desk".

The 0DTE cutoff is checked TWICE on every same-day entry — once so an
observation that cannot finish before the cutoff never starts, and again at
the moment of the order. The gap between those two moments is exactly where a
request that was legal on arrival becomes illegal on execution, and a
same-day contract entered late is a different trade from the one the operator
asked for.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

# The desk trades US markets and its rules are written in Central time. One
# timezone constant, used everywhere, so an hour is never lost converting.
DESK_TZ = ZoneInfo("America/Chicago")

# Same-day contracts are only entered while there is still session left for
# the move to happen.
ZERO_DTE_CUTOFF = time(13, 0)


def now() -> datetime:
    return datetime.now(DESK_TZ)


def today() -> date:
    return now().date()


def past_zero_dte_cutoff(at: datetime | None = None) -> bool:
    return (at or now()).timetz().replace(tzinfo=None) >= ZERO_DTE_CUTOFF


def is_same_day(expiration: str, at: datetime | None = None) -> bool:
    try:
        return date.fromisoformat(expiration) == (at or now()).date()
    except ValueError:
        return False


def within_window(open_hhmm: str, close_hhmm: str,
                  at: datetime | None = None) -> bool:
    """Is the desk clock inside a configured CST window."""
    moment = (at or now()).timetz().replace(tzinfo=None)
    return time.fromisoformat(open_hhmm) <= moment <= time.fromisoformat(close_hhmm)
