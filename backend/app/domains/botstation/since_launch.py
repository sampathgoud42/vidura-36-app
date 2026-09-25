"""What each bot has made SINCE IT WAS LAUNCHED, as the EXCHANGE has it.

The station already showed a session percentage, and it was computed from the
local ledger -- which is the wrong source for this question. The ledger holds
what a bot chose to write down, and most engines write nothing: of the four
bots with runs on this account, two had never recorded a single trade. A
percentage summed from an empty table is not zero percent, but it renders
exactly like it, and an operator watching a bot trade all morning sees 0.00%.

So this asks the exchange instead, and it asks the three questions the
operator actually means:

    WHEN did this bot start          the run's own started_at, to the second
    WHICH markets are its markets    the Kalshi SERIES its launch config names
    WHAT did those markets make      Kalshi's own realized P&L, fees included

    percent = realized / the bank this run was launched with

WHY A FILL DECIDES OWNERSHIP, NOT A SETTLEMENT
A settlement carries the time the market RESOLVED, which for a quarter-hour
market is up to fifteen minutes after the trade and can easily fall on the
wrong side of a launch. A fill carries the time the order actually executed.
"Orders placed after this bot started" is the question, so fills are what is
filtered and settlements are only ever consulted for the money.

WHY A TICKER IS SAFE TO ATTRIBUTE WHOLE
Kalshi tickers are unique per market INSTANCE -- KXBTC15M-26SEP041030-30 is
one particular quarter-hour, not the series -- so a ticker with a fill after
launch was traded by this run, and that ticker's realized P&L is this run's.
The one case that is not clean is a market this bot traded both before AND
after a relaunch, which for a fifteen-minute market means relaunching inside
the same quarter hour. It is reported rather than hidden: ``mixed_tickers``
counts them, so a figure that might double-count says so.

WHY SERIES ARE DECLARED, NOT DETECTED
Each bot names its Kalshi series in its own config entry, beside its script
and its options. A prefix table in this file would be a dispatch switch --
the one thing the onboarding contract forbids -- and a new bot would trade
correctly while reporting nothing.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Below this many contracts a position counts as flat. Kalshi reports
# fractional contracts as decimal strings, so an exact == 0 on a parsed float
# is not something to rely on. Same epsilon the reconciler uses.
FLAT_EPSILON = 0.0001

# The station polls every ten seconds and shows seven bots. One exchange read
# serves all of them, and it is reused for two polls -- a fill that landed a
# few seconds ago is worth showing a moment late, and is not worth seven
# accounts' worth of API traffic per tick.
CACHE_TTL_S = 20

# How far back to ask for fills when nothing is running yet. Only used to
# bound the very first read; normally the earliest running launch decides.
DEFAULT_LOOKBACK_S = 6 * 3600

_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def series_for(config) -> frozenset[str]:
    """The Kalshi series this bot's markets belong to, from its own config.

    Empty when a bot declares none, and an empty set means this figure is not
    available for that bot rather than that everything belongs to it -- the
    difference between "we cannot say" and "all of it", which on a P&L is the
    difference between a blank and a lie.
    """
    declared = (config.extra or {}).get("series") or ()
    if isinstance(declared, str):
        declared = (declared,)
    return frozenset(str(s).strip().upper() for s in declared if str(s).strip())


def series_of(ticker: str) -> str:
    """The series a ticker belongs to: the segment before the first dash.

    KXBTC15M-26SEP041030-30 -> KXBTC15M. This is the exchange's own
    convention and the sports helpers already rely on it.
    """
    return str(ticker or "").split("-", 1)[0].upper()


def _parsed(stamp) -> datetime | None:
    """A Kalshi timestamp as naive UTC, matching how runs are stored.

    Kalshi sends ISO-8601 with a Z on some feeds and a unix number on others,
    and the database stores naive UTC. Comparing an aware datetime to a naive
    one raises; comparing the wrong convention silently shifts every result by
    hours, which is worse.
    """
    if stamp in (None, ""):
        return None
    if isinstance(stamp, (int, float)):
        return datetime.fromtimestamp(float(stamp), timezone.utc).replace(
            tzinfo=None)
    try:
        moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def account_activity(cred, *, cache_key: str, since: datetime | None = None,
                     force: bool = False) -> dict:
    """Every recent fill and every position, read ONCE for all bots.

    Seven bots asking the exchange the same two questions on the same poll is
    fourteen round trips for two answers. This is those two answers, cached
    for a poll or two, and every bot's figure is computed from the same
    snapshot -- so two tiles can never disagree because they read a moment
    apart.

    Never raises. The station must keep rendering when Kalshi is unreachable,
    and a missing figure is reported as unavailable rather than as zero.
    """
    if not force:
        with _lock:
            hit = _cache.get(cache_key)
        if hit is not None and time.time() - hit[0] < CACHE_TTL_S:
            return {**hit[1], "age_s": int(time.time() - hit[0])}

    from app.domains.botstation import venue as kalshi

    floor = since or datetime.utcnow()
    min_ts = int(floor.replace(tzinfo=timezone.utc).timestamp())
    out: dict = {"fills": [], "positions": {}, "available": True,
                 "detail": "", "age_s": 0}

    try:
        # Asked of the exchange from the earliest launch, so an account with
        # months of history still costs one page.
        out["fills"] = kalshi.fills(cred, limit=200, min_ts=min_ts)
    except Exception as exc:                            # noqa: BLE001
        logger.info("since-launch fills: %s: %s", type(exc).__name__, exc)
        return {**out, "available": False,
                "detail": "Kalshi could not be reached"}

    try:
        out["positions"] = {str(p.get("ticker") or ""): p
                            for p in kalshi.positions(cred, limit=200)}
    except Exception as exc:                            # noqa: BLE001
        # Fills alone still say WHICH markets are this bot's; only the money
        # is missing, and that is said rather than guessed at.
        logger.info("since-launch positions: %s: %s", type(exc).__name__, exc)
        out["detail"] = "position P&L could not be read"

    with _lock:
        _cache[cache_key] = (time.time(), out)
    return out


def performance(activity: dict, *, series: frozenset[str],
                started_at: datetime | None, bankroll: float | None) -> dict:
    """One bot's exchange-side result since it was launched.

    ``pct`` is null rather than 0 in every case where it is unknown -- no
    bank named at launch, no series declared, the exchange unreachable. A
    percentage of nothing is not zero percent, and a zero on a tile is a
    number an operator acts on.
    """
    blank = {"available": False, "pnl_usd": None, "pct": None, "fills": 0,
             "markets": 0, "markets_open": 0, "staked_usd": 0.0,
             "mixed_tickers": 0, "series": sorted(series),
             "since": started_at, "bankroll": bankroll, "detail": ""}

    if not series:
        return {**blank, "detail": "this bot declares no Kalshi series"}
    if started_at is None:
        return {**blank, "detail": "this run has no start time"}
    if not activity.get("available"):
        return {**blank, "detail": activity.get("detail")
                or "Kalshi could not be reached"}

    ours: set[str] = set()
    before: set[str] = set()
    fills_after = 0
    staked = 0.0

    for fill in activity.get("fills") or []:
        ticker = str(fill.get("ticker") or "")
        if series_of(ticker) not in series:
            continue
        at = _parsed(fill.get("created_time") or fill.get("created_ts"))
        if at is None:
            continue
        if at < started_at:
            # Same market, earlier run. Remembered only so the overlap can be
            # counted and declared below.
            before.add(ticker)
            continue
        ours.add(ticker)
        fills_after += 1
        # What this run put at risk, from the fill itself. count is contracts
        # and the price is CENTS on the side taken.
        count = _num(fill.get("count") or fill.get("count_fp"))
        price_c = _num(fill.get("yes_price") if str(fill.get("side") or "")
                       .lower() == "yes" else fill.get("no_price"))
        if str(fill.get("action") or "buy").lower() == "buy":
            staked += count * price_c / 100.0

    positions = activity.get("positions") or {}
    realized = 0.0
    open_markets = 0
    priced = 0
    for ticker in ours:
        row = positions.get(ticker)
        if row is None:
            # Traded since launch but no longer in the position feed. Its
            # money is unknown from here rather than zero.
            continue
        priced += 1
        realized += _num(row.get("realized_pnl_dollars"))
        if abs(_num(row.get("position_fp"))) > FLAT_EPSILON:
            open_markets += 1

    pnl = round(realized, 2)
    bank = _num(bankroll)
    return {
        "available": True,
        "pnl_usd": pnl,
        # THE NUMBER THE TILE PRINTS: percent of the bank this run was
        # launched with. Null when the launch named no bank.
        "pct": (round(pnl / bank * 100, 2) if bank > 0 else None),
        "fills": fills_after,
        "markets": len(ours),
        "markets_open": open_markets,
        "markets_priced": priced,
        "staked_usd": round(staked, 2),
        # Markets this bot also traded BEFORE this run started. Their whole
        # realized P&L is counted, so a non-zero here means the figure may
        # include a previous run's result on the same market.
        "mixed_tickers": len(ours & before),
        "series": sorted(series),
        "since": started_at,
        "bankroll": bankroll,
        "detail": activity.get("detail") or "",
    }


def for_running_bots(cred, *, cache_key: str, runs: dict) -> dict:
    """Every running bot's figure, from ONE exchange snapshot.

    ``runs`` maps bot_key -> (config, started_at, bankroll). The earliest
    start decides how far back the exchange is asked, so the read is bounded
    by the oldest thing actually running rather than by a fixed window.
    """
    starts = [start for _, start, _ in runs.values() if start is not None]
    since = min(starts) if starts else None
    activity = account_activity(cred, cache_key=cache_key, since=since)
    return {key: performance(activity, series=series_for(config),
                             started_at=start, bankroll=bank)
            for key, (config, start, bank) in runs.items()}
