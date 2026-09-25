"""V7: trade the quarter-hour only when the WHOLE DMI stack points one way.

The premise is narrower than v6's and easier to state. v6 asked three
different instruments (BTC, ETH, SOL) whether they agreed, and used only the
board's headline ``signal`` -- which is itself just the 1m and 2m sides
matching. That threw away the two slower columns the panel already shows.

V7 asks ONE instrument -- the one actually being traded -- whether all four
timeframes on the desk's board agree:

    1m up,   2m up,   5m up,   10m up      ->  buy YES
    1m down, 2m down, 5m down, 10m down    ->  buy NO
    anything else                          ->  stand aside

That is exactly the line the panel renders, read the way an operator reads it:

    BTC 79381.00  1m 15^  2m 37^  5m 50^  10m 34^   -> yes
    GOLD 405.24   1m 15v  2m 37v  5m 50v  10m 34v   -> no

Four arrows the same way is a trend that survives being looked at on four
different clocks. One timeframe disagreeing is the fast money and the slow
money wanting different things, and a fifteen-minute contract is too short to
wait out that argument.

WHY THIS MODULE IS NOT UNDER ``btc15/``
The rule is not BTC's. Gold, silver and oil trade the same quarter-hour shape
against the same board, so all four V7-family engines import this one module
and the row key is the only thing that differs between them. Putting it in
``btc15/alignment.py`` would have made gold import a package named for
bitcoin, and the second engine to want a tweak would have forked it.

WHY v6's ``alignment.py`` IS UNTOUCHED
It is a different rule -- three instruments, headline signal, 60-300s, 40-70c
-- and it is still selectable. The three gate helpers below look like the ones
in that module and are deliberately not shared with it: v6 is frozen on its
own numbers, and reaching into a live engine to re-parameterise its gates is
how a version that was working stops working. When v6 is retired, that module
goes with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# The four columns of the board, in the order the panel prints them, mapped to
# the label the operator reads. These are the SAME keys
# ``app.domains.trading.market.board.row_from_bars`` emits, because this rule
# is defined as "what the panel is showing" -- a second opinion computed here
# would drift from the screen the first time either was touched, and nothing
# compares them.
TIMEFRAMES = ("m1", "m2", "m5", "m10")
LABELS = {"m1": "1m", "m2": "2m", "m5": "5m", "m10": "10m"}

# TWO INDEPENDENT THINGS, and the panel draws them as two independent things.
# Getting them confused is the whole reason this comment exists.
#
#   SIDE   call or put -- which way +DI/-DI is leaning. The panel prints the
#          timeframe's LABEL in green for call and red for put.
#   SLOPE  is ADX rising or falling -- whether the trend is BUILDING or dying.
#          The panel prints the ↑ or ↓ beside the number, from m*_slope.
#
# A call↓ is a market leaning up whose conviction is fading; a put↑ is a
# market leaning down and getting more certain about it. They are different
# facts and V8 counts them separately.
ARROWS = {True: "↑", False: "↓"}
WORDS = {"call": "call", "put": "put"}

# How many of the four timeframes V8 needs. Three of four rather than four of
# four: v7's unanimity is the strictest reading of the board and it stands
# aside on a stack that is three-quarters convinced, which on a fifteen-minute
# market is most of them.
MAJORITY_NEED = 3

# Which rule an engine is running. Named rather than passed as a bool, because
# "unanimous=False" at a call site says nothing about what it does instead.
UNANIMOUS = "unanimous"
MAJORITY = "majority"

# The entry window, in seconds after the market opened.
ENTRY_OPEN_S = 5
ENTRY_CLOSE_S = 300

# What we are willing to pay, in cents, for the side being bought.
MIN_PRICE_C = 30
MAX_PRICE_C = 65

# call -> the YES side pays if the underlying finishes above the strike.
SIDE_FOR = {"call": "yes", "put": "no"}


@dataclass(frozen=True)
class Stack:
    """What one instrument's four timeframes say, and whether that is a trade."""

    aligned: bool
    direction: str | None          # call | put | None
    side: str | None               # yes | no | None
    per_tf: dict[str, str | None]  # m1/m2/m5/m10 -> call | put | None
    adx: dict[str, float | None]
    last: float | None
    label: str
    reason: str
    # Is ADX RISING on each timeframe -- the panel's ↑/↓, which is not the
    # side. None where the board could not compute a slope, which counts as
    # "not rising" rather than as rising: an unknown must never satisfy a
    # threshold.
    rising: dict[str, bool | None] = field(default_factory=dict)

    @property
    def tradeable(self) -> bool:
        return self.aligned and self.side is not None

    def board_line(self) -> str:
        """The row as the panel prints it, for the log.

        ``BTC 79381.00  1m 15 call↑  2m 37 call↑  5m 50 put↑  10m 34 call↓``

        Both facts, spelled out. The panel shows the side as a COLOUR and the
        slope as the arrow, and a log cannot print a colour -- so the side is
        written as a word next to the same arrow the screen draws. An earlier
        version used the arrow for the side, which read fine on its own and
        disagreed with the screen about what ↑ meant.

        Worth the few lines: when a bot stands aside and the operator is
        looking at a board that appears to agree with it, the argument is
        settled by putting the two lines next to each other rather than by
        reasoning about which one is stale.
        """
        price = f"{self.last:g}" if self.last is not None else "?"
        cells = []
        for name in TIMEFRAMES:
            adx = self.adx.get(name)
            if adx is None:
                # No reading at all -- not a flat one. Printed as a gap rather
                # than as a zero with an arrow beside it, which is what a
                # missing feed would otherwise look like on the board.
                cells.append(f"{LABELS[name]} --")
                continue
            up = self.rising.get(name)
            cells.append(
                f"{LABELS[name]} {adx:.0f} "
                f"{WORDS.get(self.per_tf.get(name), 'flat')}"
                f"{ARROWS.get(bool(up), '-') if up is not None else '·'}")
        return f"{self.label} {price}  " + "  ".join(cells)


def _blocked(per_tf, adx, last, label, reason, rising=None) -> Stack:
    return Stack(False, None, None, per_tf, adx, last, label, reason,
                 rising or {})


def _read_row(rows: list[dict], row_key: str):
    """The board row for one instrument, unpacked into the four facts.

    Returns (row, label, per_tf, rising, adx, last) or a blocked Stack when
    there is no usable row -- shared by both rules so they cannot disagree
    about what the board said, only about what it means.
    """
    row = next((r for r in rows if r.get("bot") == row_key), None)
    if row is None:
        seen = ", ".join(sorted(str(r.get("bot")) for r in rows)) or "nothing"
        return _blocked({}, {}, None, row_key,
                        f"no {row_key} row on the board (it carried: {seen})")

    label = str(row.get("label") or row_key).upper()
    per_tf = {n: row.get(f"{n}_side") for n in TIMEFRAMES}
    adx = {n: row.get(f"{n}_adx") for n in TIMEFRAMES}
    slopes = {n: row.get(f"{n}_slope") for n in TIMEFRAMES}
    rising = {n: (None if v is None else float(v) > 0)
              for n, v in slopes.items()}
    last = row.get("last")

    if row.get("error"):
        return _blocked(per_tf, adx, last, label,
                        f"the board could not read {label}: {row['error']}",
                        rising)
    return row, label, per_tf, rising, adx, last


def read_majority(rows: list[dict], row_key: str, *,
                  need: int = MAJORITY_NEED) -> Stack:
    """V8: ``need`` of four leaning one way, AND ``need`` of four rising.

    Two counts, taken independently across all four timeframes:

        at least 3 timeframes are CALL   and at least 3 are rising  -> buy YES
        at least 3 timeframes are PUT    and at least 3 are rising  -> buy NO

    The rising count is over the WHOLE stack, not over the agreeing side. The
    board that produced this rule shows it plainly:

        1m 15 call↑   2m 37 call↑   5m 50 put↑   10m 34 call↓   -> YES

    three calls, and three rising -- but only two of the CALLS are rising. A
    rule that wanted three rising calls would stand this one down, and it is
    the example that was asked for.

    Both thresholds cannot be met by opposite sides at once: three plus three
    is six and there are only four timeframes, so a call majority and a put
    majority cannot coexist and no tie-break is needed.

    A missing side counts toward neither, and a missing slope counts as not
    rising. Neither blocks on its own -- with four timeframes, two unknowns
    already make three unreachable, so the threshold does the refusing.
    """
    unpacked = _read_row(rows, row_key)
    if isinstance(unpacked, Stack):
        return unpacked
    _row, label, per_tf, rising, adx, last = unpacked

    calls = [n for n in TIMEFRAMES if per_tf.get(n) == "call"]
    puts = [n for n in TIMEFRAMES if per_tf.get(n) == "put"]
    ups = [n for n in TIMEFRAMES if rising.get(n)]

    shown = "  ".join(
        f"{LABELS[n]}{WORDS.get(per_tf.get(n), 'flat')}"
        f"{ARROWS.get(bool(rising.get(n)), '-') if rising.get(n) is not None else '·'}"
        for n in TIMEFRAMES)

    if len(ups) < need:
        return _blocked(per_tf, adx, last, label,
                        f"only {len(ups)} of {len(TIMEFRAMES)} rising, "
                        f"{need} needed: {shown}", rising)

    if len(calls) >= need:
        direction = "call"
    elif len(puts) >= need:
        direction = "put"
    else:
        return _blocked(per_tf, adx, last, label,
                        f"no side has {need} of {len(TIMEFRAMES)} "
                        f"({len(calls)} call, {len(puts)} put): {shown}",
                        rising)

    side = SIDE_FOR.get(direction)
    if side is None:
        return _blocked(per_tf, adx, last, label,
                        f"no tradeable side for {direction!r}", rising)

    agreeing = len(calls) if direction == "call" else len(puts)
    return Stack(True, direction, side, per_tf, adx, last, label,
                 f"{agreeing} of {len(TIMEFRAMES)} {WORDS[direction]} and "
                 f"{len(ups)} rising -> buy {side.upper()}", rising)


def read(rows: list[dict], row_key: str, *, rule: str = UNANIMOUS,
         need: int = MAJORITY_NEED) -> Stack:
    """Whichever rule the engine was launched with.

    One entry point so the loop never branches on a version number -- a bot
    names its rule in its profile and everything downstream reads a Stack.
    """
    if rule == MAJORITY:
        return read_majority(rows, row_key, need=need)
    return read_stack(rows, row_key)


def read_stack(rows: list[dict], row_key: str) -> Stack:
    """Are all four timeframes of ``row_key`` pointing the same way.

    ``rows`` are the board's own rows -- the crypto board for BTC, the
    commodity board for gold/silver/oil -- so a feed that failed arrives with
    ``error`` set and correctly blocks the trade rather than being read as a
    flat market.

    A timeframe whose side is None also blocks, and that case is real rather
    than theoretical: ``indicators.dmi`` returns None for the side when +DI
    and -DI are exactly equal, and returns no reading at all when the feed is
    too short to compute one. Neither is an arrow. Treating either as
    agreement would let three columns speak for four.
    """
    unpacked = _read_row(rows, row_key)
    if isinstance(unpacked, Stack):
        return unpacked
    _row, label, per_tf, rising, adx, last = unpacked

    missing = [LABELS[n] for n in TIMEFRAMES if per_tf.get(n) is None]
    if missing:
        return _blocked(per_tf, adx, last, label,
                        f"no side on {', '.join(missing)} -- a blank column "
                        f"is not agreement", rising)

    sides = set(per_tf.values())
    if len(sides) != 1:
        shown = "  ".join(f"{LABELS[n]}{WORDS.get(per_tf[n], 'flat')}"
                          for n in TIMEFRAMES)
        return _blocked(per_tf, adx, last, label,
                        f"the stack is split: {shown}", rising)

    direction = sides.pop()
    side = SIDE_FOR.get(direction)
    if side is None:
        return _blocked(per_tf, adx, last, label,
                        f"no tradeable side for {direction!r}", rising)

    return Stack(True, direction, side, per_tf, adx, last, label,
                 f"all four timeframes {WORDS[direction]} -> "
                 f"buy {side.upper()}", rising)


def seconds_since_open(open_time: str, now: datetime | None = None) -> float | None:
    """How long this market has been open. None when the time is unreadable.

    None rather than 0: a market whose open time cannot be parsed has an
    UNKNOWN age, and treating that as "just opened" would trade the one market
    we understand least -- and this engine's window starts five seconds after
    the bell, so a wrong zero is a guaranteed entry rather than a near miss.
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
    """STRICTLY inside the window, both ends.

    The floor exists because the first seconds of a quarter-hour have no book
    worth hitting; the ceiling because after five minutes a third of the
    window is spent and the move this engine is trying to catch is already in
    the price.
    """
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
    """Refuse, never clamp.

    A price outside the band is a different trade from the one this engine was
    configured to take, and buying it anyway at the nearest allowed number is
    how a band becomes a suggestion.
    """
    if price_c is None:
        return False, "no price on that side -- the market is not quoted"
    if price_c < low:
        return False, (f"{price_c}c is below the {low}c floor -- the market "
                       f"disagrees with the stack and the odds do not pay "
                       f"for it")
    if price_c > high:
        return False, (f"{price_c}c is above the {high}c ceiling -- the move "
                       f"is already priced in")
    return True, f"{price_c}c is inside {low}-{high}c"


def decide(rows: list[dict], row_key: str, *, open_time: str,
           price_c: int | None, now: datetime | None = None,
           opens_at: int = ENTRY_OPEN_S, closes_at: int = ENTRY_CLOSE_S,
           low: int = MIN_PRICE_C, high: int = MAX_PRICE_C,
           rule: str = UNANIMOUS, need: int = MAJORITY_NEED) -> dict:
    """The whole entry decision, as data.

    ``rule`` picks which reading of the board applies -- v7's unanimity or
    v8's three-of-four majority. The gates below it are identical either way,
    which is the point: the two engines differ in what they consider a signal
    and in nothing else.

    Every gate is evaluated and reported even after one has failed, because
    "the stack agreed but we were three seconds early" and "we were in the
    window but 5m disagreed" are different days, and an engine that logs only
    the first failure makes them look identical.
    """
    stack = read(rows, row_key, rule=rule, need=need)
    age = seconds_since_open(open_time, now)
    timing_ok, timing_why = within_entry_window(age, opens_at=opens_at,
                                                closes_at=closes_at)

    # A missing price means two different things and they must not read the
    # same. The caller only ASKS for a price once the stack has picked a side,
    # so when there is no side there is no quote to report -- saying "the
    # market is not quoted" there blames the exchange for a decision this
    # engine never made.
    if price_c is None and not stack.tradeable:
        price_ok, price_why = False, "not asked -- no side to price yet"
    else:
        price_ok, price_why = within_price_band(price_c, low=low, high=high)

    gates = {"dmi stack": (stack.tradeable, stack.reason),
             "timing": (timing_ok, timing_why),
             "price": (price_ok, price_why)}
    blocked = [name for name, (ok, _) in gates.items() if not ok]

    return {
        "enter": not blocked,
        "side": stack.side if not blocked else None,
        "direction": stack.direction,
        "rule": rule,
        "per_tf": stack.per_tf,
        "board_line": stack.board_line(),
        "age_s": age,
        "price_c": price_c,
        "blocked_by": blocked,
        "gates": {name: {"ok": ok, "why": why}
                  for name, (ok, why) in gates.items()},
    }
