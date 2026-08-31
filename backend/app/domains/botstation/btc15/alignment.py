"""BTC-15 v6: trade the 15-minute market only when the majors agree.

The premise is that a BTC-15 contract is a bet on where BTC sits at the close
of a fifteen-minute window, and that the strongest read on which way it is
leaning is not BTC alone -- it is BTC, ETH and SOL pointing the same way at
once. One coin trending is noise that reverses inside a quarter hour; three
majors trending together is the whole crypto complex moving, which is a
different thing.

So this engine takes NO view of its own. It reads the desk's crypto board --
the same 1m/2m/5m/10m DMI the CRYPTO panel shows, from the same module, so the
bot and the screen can never disagree -- and trades only on unanimity.

    all three CALL  ->  buy YES
    all three PUT   ->  buy NO
    anything else   ->  stand aside

Three gates sit in front of every entry, and each exists because of how a
15-minute market behaves:

  TIMING   1 to 5 minutes after the market opens. Before a minute there is no
           book worth trading; after five the window is half gone and the
           price has already absorbed the move this engine is trying to catch.

  PRICE    40c to 70c on the side being bought. Below 40c the market thinks
           we are wrong and the payout is not worth the odds; above 70c most
           of the move is priced in and the remaining upside does not cover
           a 40% stop.

  AGREEMENT  All three, or nothing. Two-of-three is deliberately NOT enough:
           the whole reason for looking at three coins is that any one of
           them can be trending on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# The majors this engine reads, in the order it reports them. BTC first
# because it is the instrument being traded; the other two are corroboration.
COINS = ("btc", "eth", "sol")

# The entry window, in seconds after the market opened.
ENTRY_OPEN_S = 60
ENTRY_CLOSE_S = 300

# What we are willing to pay, in cents, for the side we are buying.
MIN_PRICE_C = 40
MAX_PRICE_C = 70

# call -> the YES side pays if BTC finishes above the strike.
SIDE_FOR = {"call": "yes", "put": "no"}


@dataclass(frozen=True)
class Alignment:
    """What the three majors are saying, and whether that is tradeable."""

    aligned: bool
    direction: str | None          # call | put | None
    side: str | None               # yes | no | None
    per_coin: dict[str, str | None]
    reason: str

    @property
    def tradeable(self) -> bool:
        return self.aligned and self.side is not None


def read_alignment(rows: list[dict]) -> Alignment:
    """Are BTC, ETH and SOL all pointing the same way.

    ``rows`` are the crypto board's own rows, so a coin whose feed failed
    arrives with ``signal`` unset and correctly blocks the trade: an unknown
    is not agreement, and treating a missing reading as neutral would let two
    coins speak for three.
    """
    by_key = {r.get("bot"): r for r in rows}
    per_coin: dict[str, str | None] = {}
    for coin in COINS:
        row = by_key.get(coin) or {}
        per_coin[coin] = None if row.get("error") else row.get("signal")

    missing = [c for c, s in per_coin.items() if s is None]
    if missing:
        return Alignment(False, None, None, per_coin,
                         f"no signal for {', '.join(missing)} — "
                         f"an unknown is not agreement")

    sides = set(per_coin.values())
    if len(sides) != 1:
        return Alignment(False, None, None, per_coin,
                         "majors disagree: "
                         + ", ".join(f"{c}={s}" for c, s in per_coin.items()))

    direction = sides.pop()
    side = SIDE_FOR.get(direction)
    if side is None:
        return Alignment(False, direction, None, per_coin,
                         f"no tradeable side for {direction!r}")
    return Alignment(True, direction, side, per_coin,
                     f"BTC, ETH and SOL all {direction} -> buy {side.upper()}")


def seconds_since_open(open_time: str, now: datetime | None = None) -> float | None:
    """How long this market has been open. None when the time is unreadable.

    None rather than 0: a market whose open time cannot be parsed has an
    UNKNOWN age, and treating that as "just opened" would trade the one
    market we understand least.
    """
    if not open_time:
        return None
    try:
        opened = datetime.fromisoformat(str(open_time).replace("Z", "+00:00"))
    except ValueError:
        return None
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    return ((now or datetime.now(timezone.utc)) - opened).total_seconds()


def within_entry_window(age_s: float | None, *, opens_at: int = ENTRY_OPEN_S,
                        closes_at: int = ENTRY_CLOSE_S) -> tuple[bool, str]:
    if age_s is None:
        return False, "the market's open time could not be read"
    if age_s < opens_at:
        return False, (f"only {age_s:.0f}s since open; the window starts at "
                       f"{opens_at}s")
    if age_s > closes_at:
        return False, (f"{age_s:.0f}s since open; the window closed at "
                       f"{closes_at}s")
    return True, f"{age_s:.0f}s after open"


def within_price_band(price_c: int | None, *, low: int = MIN_PRICE_C,
                      high: int = MAX_PRICE_C) -> tuple[bool, str]:
    """Refuse, never clamp. A price outside the band is a different trade from
    the one this engine was configured to take, and buying it anyway at the
    nearest allowed number is how a band becomes a suggestion."""
    if price_c is None:
        return False, "no price on that side — the market is not quoted"
    if price_c < low:
        return False, (f"{price_c}c is below the {low}c floor — the market "
                       f"disagrees and the odds do not pay for it")
    if price_c > high:
        return False, (f"{price_c}c is above the {high}c ceiling — the move "
                       f"is already priced in")
    return True, f"{price_c}c is inside {low}-{high}c"


def decide(rows: list[dict], *, open_time: str, price_c: int | None,
           now: datetime | None = None, opens_at: int = ENTRY_OPEN_S,
           closes_at: int = ENTRY_CLOSE_S, low: int = MIN_PRICE_C,
           high: int = MAX_PRICE_C) -> dict:
    """The whole entry decision, as data.

    Every gate is evaluated and reported even after one fails, because "the
    majors agreed but we were 40 seconds early" and "we were in the window but
    the majors disagreed" are different days, and a bot that logs only the
    first failure makes them look identical.
    """
    alignment = read_alignment(rows)
    age = seconds_since_open(open_time, now)
    timing_ok, timing_why = within_entry_window(age, opens_at=opens_at,
                                                closes_at=closes_at)
    # A missing price means two different things and they must not read the
    # same. The caller only ASKS for a price once the majors have picked a
    # side, so when there is no side there is no quote to report -- saying
    # "the market is not quoted" there blames the exchange for a decision the
    # engine never made. That misreading cost real time: 69 of 70 price
    # failures in one session were logged as an unquoted market when the
    # actual reason was that the coins disagreed.
    if price_c is None and not alignment.tradeable:
        price_ok, price_why = False, "not asked — no side to price yet"
    else:
        price_ok, price_why = within_price_band(price_c, low=low, high=high)

    gates = {"agreement": (alignment.tradeable, alignment.reason),
             "timing": (timing_ok, timing_why),
             "price": (price_ok, price_why)}
    blocked = [name for name, (ok, _) in gates.items() if not ok]

    return {
        "enter": not blocked,
        "side": alignment.side if not blocked else None,
        "direction": alignment.direction,
        "per_coin": alignment.per_coin,
        "age_s": age,
        "price_c": price_c,
        "blocked_by": blocked,
        "gates": {name: {"ok": ok, "why": why}
                  for name, (ok, why) in gates.items()},
    }
