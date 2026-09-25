"""The best-pairs bot: the desk's best_pairs auto-trader, in a process of its own.

It trades exactly what ARM AUTO TRADE -> "best pairs" trades -- a new live
signal whose signal type AND ticker are one of the daily report's best pairs
buys a CALL for a LONG and a PUT for a SHORT -- and it trades it through the
same code: the desk watcher's own tick (autotrade._super_tick) and the manual
BUY's own entry (entry.open_managed), with every guard the desk has. Nothing
here is a second copy of the entry path. The last auto-trader that carried its
own copy drifted until every one of its orders raised.

What is different is only what a separate process needs:

  the pairs      read each session from the signal desk's best-pairs list
                 (its best_ticker_signal_pairs table), filtered by this bot's
                 minimums -- re-read every trading day rather than disarming
                 at the close, because the report re-ranks them overnight.
  the desk       one trader per operator (signal_owner). The bot holds the
                 claim while it runs; while the desk's own watcher holds it,
                 the bot stands by and takes over when that one disarms.
  the stops      exits are armed by the risk monitor. While the desk runs,
                 its monitor does that. While it does not, this bot sweeps its
                 operator's positions itself, or nothing would.
  the cooldown   one entry per ticker per hour, read from the positions table
                 each pass, so it spans the desk's watcher, this bot, and a
                 restart of either.

Duplicate entries are prevented by the database, not by this process: one
idempotency key per signal (the same key the desk's watcher uses), the
contract lease, the already-held check and the venue's working-order check.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime

import requests

from app.domains.trading.execution import autotrade, signal_owner
from app.domains.trading.risk import clock
from app.services import super_signals as desk

from bot_best_pair.config import BotConfig

logger = logging.getLogger("bot_best_pair")

NAME = "bot_best_pair"
LABEL = "Auto/bot_best_pair"
POLL_S = autotrade.SUPER_POLL_SECONDS
# An empty or unreadable list is asked for again this often, not every pass.
PAIRS_RETRY_S = 300
# How long one answer from the desk's /readiness is believed.
READINESS_TTL_S = 30


class AlreadyRunning(RuntimeError):
    """Another bot_best_pair holds this operator's signal desk."""


@dataclass
class PairWatcher(autotrade.Watcher):
    """The desk's best_pairs watcher, with this bot's label on its positions --
    so the desk's position list says which of the two traders opened each."""

    @property
    def label(self) -> str:
        return LABEL


def parse_pairs(body: dict, cfg: BotConfig) -> tuple[list[dict], list[str]]:
    """The pairs this bot trades, best first, and why any listed one is not.

    A pair must be well formed by the arm form's own definition, and must meet
    the minimums on this side of the wire too (BotConfig.meets_minimums)."""
    keep, dropped, seen = [], [], set()
    for p in body.get("pairs") or []:
        key = str(p.get("type_key") or "").strip()
        ticker = str(p.get("ticker") or "").strip().upper()
        if not autotrade._TYPE_KEY.match(key) or not autotrade._SYMBOL.match(ticker):
            dropped.append(f"malformed pair {ticker or '?'} {key or '?'}")
        elif not cfg.meets_minimums(p):
            dropped.append(f"{ticker} {key} is under {cfg.describe_minimums()}")
        elif (key, ticker) not in seen:
            seen.add((key, ticker))
            keep.append({**p, "type_key": key, "ticker": ticker})
    return keep, dropped


def describe_pair(p: dict) -> str:
    record = f"{p.get('wins', '?')}-{p.get('losses', '?')}-{p.get('timeouts', '?')}"
    try:
        stats = (f"{float(p.get('win_pct')):.0f}% · {float(p.get('net_r')):+.2f}R · "
                 f"edge {float(p.get('edge')):g}")
    except (TypeError, ValueError):
        stats = f"edge {p.get('edge')}"
    return f"#{p.get('rank', '?')} {p['ticker']} {p.get('signal') or p['type_key']} · {record} · {stats}"


class Bot:
    """One operator's best-pairs bot. ``step`` is one pass; ``run`` loops it."""

    def __init__(self, cfg: BotConfig, *, tenant_id: str) -> None:
        self.cfg = cfg
        self.tenant_id = tenant_id
        self.holder = signal_owner.holder_name(NAME, "live" if cfg.live else "paper")
        self.stop_flag = threading.Event()
        self.watcher: PairWatcher | None = None
        self.pairs_day: str | None = None
        self.pairs_tried_at = 0.0
        self.baseline_day: str | None = None
        self.owns_desk = False
        self._said: dict[str, str] = {}
        self._readiness: tuple[float, bool] | None = None
        self._http = requests.Session()
        self._http.trust_env = False            # the desk is on loopback

    # ---- one pass -------------------------------------------------------

    def step(self, now: datetime) -> None:
        """Stops first, then the desk claim, then today's pairs, then the tick."""
        self._watch_stops()
        if not self._hold_desk():
            return
        if not clock.is_regular_session(now):
            self._say("session", "outside the regular session -- waiting for 08:30 CST")
            return
        self._say("session", "in session")
        if not self._load_pairs(now):
            return
        self._share_cooldown()
        self.baseline_day = autotrade._super_tick(self.watcher, now, self.baseline_day)

    # ---- the desk -------------------------------------------------------

    def _hold_desk(self) -> bool:
        other = signal_owner.claim(self.tenant_id, self.holder)
        if other is None:
            if not self.owns_desk:
                self.owns_desk = True
                # Signals that fired while another trader held the desk were its
                # business: the first pass after taking it baselines them.
                self.baseline_day = None
                self._say("desk", f"holding the signal desk for {self.cfg.operator} -- "
                                  f"the desk's own signal auto-trader cannot arm while this runs")
            return True
        self.owns_desk = False
        if other.kind == NAME:
            raise AlreadyRunning(f"{other.describe()} is already trading best pairs for "
                                 f"{self.cfg.operator}")
        self._say("desk", f"standing by: {other.describe()} holds the signal desk for "
                          f"{self.cfg.operator}; this bot takes over when it disarms")
        return False

    def release(self) -> None:
        try:
            signal_owner.release(self.tenant_id, self.holder)
        except Exception as exc:                        # noqa: BLE001
            logger.warning("could not release the signal desk (it expires by itself "
                           "within %ss): %s", signal_owner.TTL_S, exc)
        self.owns_desk = False

    # ---- the pairs ------------------------------------------------------

    def _load_pairs(self, now: datetime) -> bool:
        """Today's pairs, read once per session day from the signal desk."""
        today = now.date().isoformat()
        if self.pairs_day == today and self.watcher is not None:
            return True
        if time.monotonic() - self.pairs_tried_at < PAIRS_RETRY_S and self.pairs_tried_at:
            return False
        self.pairs_tried_at = time.monotonic()
        try:
            body = desk.get_json("/api/best-pairs", self.cfg.minimums() or None)
        except desk.Unavailable as exc:
            self._say("pairs", f"the signal desk cannot list the best pairs -- {exc.detail}; "
                               f"asking again in {PAIRS_RETRY_S // 60} min")
            return False
        pairs, dropped = parse_pairs(body, self.cfg)
        for why in dropped:
            logger.warning("not traded: %s", why)
        window = body.get("window") or {}
        source = (f"the {body.get('session') or '?'} report · {window.get('sessions', '?')} "
                  f"sessions ({window.get('from', '?')} -> {window.get('to', '?')}) · "
                  f"{len(pairs)} of {body.get('total', '?')} meet {self.cfg.describe_minimums()}")
        if not pairs:
            self._say("pairs", f"no best pair to trade from {source}; asking again in "
                               f"{PAIRS_RETRY_S // 60} min")
            return False
        carried = dict(self.watcher.last_entry) if self.watcher else {}
        self.watcher = PairWatcher(
            tenant_id=self.tenant_id, tickers=sorted({p["ticker"] for p in pairs}),
            strategy="best_pairs", live=self.cfg.live, buy_pct=self.cfg.buy_pct,
            tp_pct=self.cfg.tp_pct, sl_pct=self.cfg.sl_pct,
            tolerance_pct=self.cfg.tolerance_pct, min_contracts=self.cfg.min_contracts,
            delta_min=self.cfg.delta_min, delta_max=self.cfg.delta_max, armed_at=now,
            pairs={(p["type_key"], p["ticker"]) for p in pairs},
            window_open=self.cfg.window_open, window_close=self.cfg.window_close,
            zero_dte=self.cfg.zero_dte, desk_holder=self.holder)
        self.watcher.last_entry.update(carried)
        self.pairs_day, self.baseline_day, self.pairs_tried_at = today, None, 0.0
        self._say("pairs", f"trading {len(pairs)} best pair(s) from {source}")
        for p in pairs:
            logger.info("  %s", describe_pair(p))
        return True

    def _share_cooldown(self) -> None:
        """Fold in entries the desk's watcher -- or this bot before a restart --
        made on these tickers inside the cooldown, keeping the later of each."""
        recent = signal_owner.recent_entries(self.tenant_id, self.watcher.tickers,
                                             within_s=autotrade.SUPER_COOLDOWN_S)
        for ticker, at in recent.items():
            mine = self.watcher.last_entry.get(ticker)
            if mine is None or at > mine:
                self.watcher.last_entry[ticker] = at

    # ---- the stops ------------------------------------------------------

    def _desk_monitor_running(self) -> bool:
        """Whether the desk's own risk monitor is up, from its /readiness.
        Anything but a clear yes is a no: an unanswered question about who is
        watching a stop must end with somebody watching it."""
        cached = self._readiness
        if cached and time.monotonic() - cached[0] < READINESS_TTL_S:
            return cached[1]
        try:
            r = self._http.get(f"{self.cfg.desk_url}/readiness", timeout=3)
            loop = ((r.json() or {}).get("background") or {}).get("risk-monitor") or {}
            running = bool(r.ok and loop.get("running"))
        except (requests.RequestException, ValueError, AttributeError):
            running = False
        self._readiness = (time.monotonic(), running)
        return running

    def _watch_stops(self) -> None:
        if not self.cfg.own_monitor:
            return
        if self._desk_monitor_running():
            self._say("stops", f"stops: the desk's risk monitor is running ({self.cfg.desk_url}) "
                               f"and watches them")
            return
        self._say("stops", "stops: the desk's risk monitor is not running -- this bot "
                           f"sweeps {self.cfg.operator}'s positions itself")
        from app.domains.trading.risk import monitor

        try:
            result = monitor.run_pass(tenant_id=self.tenant_id)
        except monitor.MonitorPassIncomplete as exc:
            self._say("sweep", f"stops: sweep incomplete -- {exc}", level=logging.WARNING)
            return
        except Exception as exc:                        # noqa: BLE001
            self._say("sweep", f"stops: sweep failed -- {type(exc).__name__}: {exc}",
                      level=logging.WARNING)
            return
        self._say("sweep", "stops: sweeping")
        for event in result.get("events") or []:
            logger.info("stops: %s", event)

    # ---- the loop -------------------------------------------------------

    def _say(self, topic: str, message: str, *, level: int = logging.INFO) -> None:
        """Log a state once, when it changes -- an outage that lasts an hour is
        one line, not two hundred and forty."""
        if self._said.get(topic) != message:
            self._said[topic] = message
            logger.log(level, message)

    def run(self) -> None:
        """Pass after pass until stopped. Only a second bot for the same
        operator ends it early; every other failure is logged and retried."""
        try:
            while not self.stop_flag.is_set():
                try:
                    self.step(clock.now())
                except AlreadyRunning:
                    raise
                except Exception as exc:                # noqa: BLE001
                    # The traceback once, not every 15 seconds for as long as
                    # the fault lasts; a different fault is said in full again.
                    what = f"pass failed: {type(exc).__name__}: {exc}"
                    if self._said.get("error") != what:
                        logger.exception(what)
                    self._said["error"] = what
                else:
                    self._said.pop("error", None)
                self.stop_flag.wait(POLL_S)
        finally:
            self.release()
