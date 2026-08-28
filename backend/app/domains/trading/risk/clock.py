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


# The desk's regular session, in its own timezone. Commodity signals are read
# from the venue inside this window and from the off-hours engine outside it,
# so this is the switch between two different data sources rather than a
# cosmetic label.
SESSION_OPEN = time(8, 30)
SESSION_CLOSE = time(15, 0)


def is_weekday(at: datetime | None = None) -> bool:
    return (at or now()).weekday() < 5          # Mon-Fri


def is_regular_session(at: datetime | None = None) -> bool:
    """08:30-15:00 CST, Monday to Friday.

    Does NOT know about market holidays. A holiday reads as in-session and the
    venue simply returns no bars for it, which the caller reports as "no
    reading" -- the honest outcome. Hard-coding a holiday calendar that goes
    stale would be worse: it would claim the market is shut on a day it is
    open, and the operator would not know why the board was empty.
    """
    moment = at or now()
    if not is_weekday(moment):
        return False
    clock_time = moment.timetz().replace(tzinfo=None)
    return SESSION_OPEN <= clock_time <= SESSION_CLOSE
