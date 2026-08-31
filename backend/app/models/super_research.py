"""Re-export of the research models, which now live in the research domain.

These four tables were defined TWICE for a while: once here on the legacy
Base against `super_signals` / `daily_snapshots` / `gex0dte_hourly` /
`pusher_heartbeats`, and once in app.domains.research.models against the
rebuilt names. Two ORM classes for one concept is exactly the duplication the
rebuild exists to remove -- and it is not a harmless one: the columns drifted
the moment either side was edited, and nothing would have told anybody.

So the definition moved to the domain and this module became a re-export.
The four services that read these tables (gex, gex0dte, earnings,
super_research) are unchanged and now operate on the one definition, against
whichever session they are handed.

This shim exists for those services' import lines, not as an archive. It goes
when they are folded into the research domain outright.
"""

from __future__ import annotations

from app.domains.research.models import (DailySnapshot, Gex0dteHour,
                                         PusherHeartbeat)
from app.domains.research.models import ResearchSignal as SuperSignal

__all__ = ["DailySnapshot", "Gex0dteHour", "PusherHeartbeat", "SuperSignal"]
