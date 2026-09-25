"""bot_best_pair: the best pairs, auto-traded by a process of its own.

It spends money with nobody watching and alongside the desk's own
auto-trader, so what this holds is mostly what it must NOT do:

* its shipped settings are the desk form it was asked to mirror -- min edge
  57, delta 0.25-0.45, non-0DTE, TP 10%, SL 30%, 40% of buying power +-10%,
  min 1 contract, smart limit, 08:30-14:30 CST -- and a bad setting stops it
  before the first pass;
* it trades only the report's best pairs that meet its minimums, rechecked on
  this side of the wire, through the desk's own tick and the desk's own BUY;
* it never buys what the desk's watcher bought: one idempotency key per
  signal, one cooldown per ticker read from the positions table, and one
  owner of the signal desk per operator -- the desk refuses to arm a signal
  strategy while the bot holds it, and the bot stands by while the desk does;
* a second bot for the same operator refuses to run, and a crashed one frees
  the desk by itself;
* stops are swept by the bot only while the desk's own risk monitor is not.

A pinned clock and a fake signal desk drive the bot's pass directly, so no
test waits on a thread, a market or a network.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime

import pytest

from app.domains.trading.execution import autotrade, orders, signal_owner
from app.domains.trading.risk import clock
from app.services import super_signals as desk

from bot_best_pair import bot as bot_mod
from bot_best_pair import config

V1 = "/api/v1/tradier"
TSLA_LONG = "poc|poc_72h|medium|LONG"
MU_LONG = "flow|vidya_dmi+adx_strong||LONG"
NVDA_SHORT = "flow|adx_di_cross+momentum+adx_strong||SHORT"
AAPL_LONG = "levels|orb30_break||LONG"


def _pair(rank, ticker, key, edge, *, wins=9, losses=1, timeouts=1, win_pct=90.0, net_r=8.32):
    return {"rank": rank, "ticker": ticker, "type_key": key, "signal": key.replace("|", " "),
            "edge": edge, "wins": wins, "losses": losses, "timeouts": timeouts,
            "win_pct": win_pct, "net_r": net_r}


PAIRS = [_pair(1, "TSLA", TSLA_LONG, 70.1), _pair(2, "MU", MU_LONG, 66.0),
         _pair(5, "NVDA", NVDA_SHORT, 58.1)]


def _row(sid, *, key=TSLA_LONG, ticker="TSLA", time="10:30", source="live", outcome="open"):
    agent, setup, grade, direction = key.split("|")
    return {"id": sid, "agent": agent, "setup": setup, "grade": grade,
            "direction": direction, "ticker": ticker, "time": time,
            "source": source, "outcome": outcome}


def _weekday(day: date) -> date:
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


class Desk:
    """The signal desk's /api/best-pairs and /api/session."""

    def __init__(self, day: date):
        self.day = day
        self.rows: list[dict] = []
        self.pairs = [dict(p) for p in PAIRS]
        self.asked: list[dict | None] = []
        self.down: desk.Unavailable | None = None

    def get_json(self, path, params=None):
        if self.down is not None:
            raise self.down
        if path == "/api/best-pairs":
            self.asked.append(params)
            return {"table": "best_ticker_signal_pairs", "session": self.day.isoformat(),
                    "window": {"sessions": 30, "from": "2026-08-13", "to": "2026-09-24"},
                    "total": 25, "count": len(self.pairs), "pairs": list(self.pairs)}
        assert path == "/api/session", path
        return {"date": self.day.isoformat(), "signals": list(self.rows)}


@pytest.fixture()
def at(monkeypatch):
    """Pin every clock the bot reads to one weekday instant: the desk clock,
    and the database stamps the cooldown and the desk claim compare against.

    A weekday on or after today, so a weekend run still has a session, and the
    expiries the fake venue lists are never in the past."""
    day = _weekday(date.today())
    holder = {}

    def set_time(hh, mm, *, on: date | None = None):
        holder["now"] = datetime.combine(on or holder.get("day", day), dtime(hh, mm),
                                         tzinfo=clock.DESK_TZ)
        holder["day"] = holder["now"].date()
        return holder["now"]

    def db_now():
        return holder["now"].astimezone(UTC).replace(tzinfo=None)

    set_time(10, 32)
    monkeypatch.setattr(clock, "now", lambda: holder["now"])
    monkeypatch.setattr(signal_owner, "utcnow", db_now)
    monkeypatch.setattr(orders, "utcnow", db_now)
    set_time.day = day
    return set_time


@pytest.fixture()
def feed(monkeypatch, at) -> Desk:
    d = Desk(at.day)
    monkeypatch.setattr(desk, "get_json", d.get_json)
    return d


def _cfg(op, **over) -> config.BotConfig:
    env = {"BOT_BEST_PAIR_OPERATOR": op.slug, "BOT_BEST_PAIR_OWN_MONITOR": "off"}
    env.update({f"BOT_BEST_PAIR_{k.upper()}": str(v) for k, v in over.items()})
    return config.load(env, file=config.ENV_FILE)


def _bot(op, **over) -> bot_mod.Bot:
    return bot_mod.Bot(_cfg(op, **over), tenant_id=op.tenant_id)


def _positions(client, op):
    r = client.get(f"{V1}/positions", headers=op.headers)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _desk_watcher(op, pairs=((TSLA_LONG, "TSLA"),)):
    """The desk's own best_pairs watcher, built the way its tests build it."""
    pairs = set(pairs)
    return autotrade.Watcher(
        tenant_id=op.tenant_id, tickers=sorted({t for _, t in pairs}), strategy="best_pairs",
        live=False, buy_pct=20.0, tp_pct=15.0, sl_pct=30.0, tolerance_pct=25.0,
        min_contracts=1, delta_min=0.35, delta_max=0.65, armed_at=clock.now(),
        pairs=pairs, window_open="08:30", window_close="14:30")


def _arm(client, op, **over):
    body = {"strategy": "best_pairs", "tickers": "", "live": False, "buy_pct": 20,
            "tp_pct": 15, "sl_pct": 30, "tolerance_pct": 25, "min_contracts": 1,
            "delta_min": 0.35, "delta_max": 0.65,
            "pairs": [{"type_key": TSLA_LONG, "ticker": "TSLA"}],
            "window_open": "08:30", "window_close": "14:30"}
    body.update(over)
    return client.post(f"{V1}/autotrade/start", json=body, headers=op.headers)


def _said(bot) -> str:
    return " | ".join(bot._said.values())


# ---- settings -----------------------------------------------------------------

def test_the_shipped_settings_are_the_best_pairs_form_it_mirrors():
    cfg = config.load({"BOT_BEST_PAIR_OPERATOR": "someone"}, file=config.ENV_FILE)
    assert cfg.minimums() == {"min_edge": 57.0}
    assert (cfg.delta_min, cfg.delta_max, cfg.zero_dte) == (0.25, 0.45, False)
    assert (cfg.tp_pct, cfg.sl_pct) == (10.0, 30.0)
    assert (cfg.buy_pct, cfg.tolerance_pct, cfg.min_contracts) == (40.0, 10.0, 1)
    assert (cfg.window_open, cfg.window_close) == ("08:30", "14:30")
    assert cfg.live is False and cfg.venue == "tradier_sandbox"
    assert cfg.own_monitor is True


def test_the_environment_overrides_the_file():
    cfg = config.load({"BOT_BEST_PAIR_OPERATOR": "someone", "BOT_BEST_PAIR_MIN_EDGE": "60",
                       "BOT_BEST_PAIR_MIN_WIN_PCT": "80"}, file=config.ENV_FILE)
    assert cfg.minimums() == {"min_edge": 60.0, "min_win_pct": 80.0}


def test_bad_settings_stop_the_bot_and_every_problem_is_named(tmp_path):
    bad = tmp_path / "bad.env"
    bad.write_text("BOT_BEST_PAIR_OPERATOR=\n"
                   "BOT_BEST_PAIR_DELTA_MIN=0.6\nBOT_BEST_PAIR_DELTA_MAX=0.4\n"
                   "BOT_BEST_PAIR_SL_PCT=100\n"
                   "BOT_BEST_PAIR_MIN_EDGE=nan\n"
                   "BOT_BEST_PAIR_WINDOW_OPEN=14:30\nBOT_BEST_PAIR_WINDOW_CLOSE=08:30\n"
                   "BOT_BEST_PAIR_LIVE=maybe\n", encoding="utf-8")
    with pytest.raises(config.ConfigError) as err:
        config.load({}, file=bad)
    said = str(err.value)
    for why in ("OPERATOR is empty", "delta range", "sl_pct 100", "MIN_EDGE",
                "start before it ends", "LIVE='maybe'"):
        assert why in said, why


def test_the_bot_defaults_to_the_desks_own_database(tmp_path):
    env: dict[str, str] = {}
    url = config.prepare_platform_env(env, dotenv=tmp_path / "missing.env")
    assert url.startswith("sqlite:///") and url.endswith("/var/app-v2.db")

    dotenv = tmp_path / ".env"
    dotenv.write_text("TBOT_DATABASE_URL_OVERRIDE=sqlite:///./elsewhere.db\n", encoding="utf-8")
    assert config.prepare_platform_env({}, dotenv=dotenv) == "sqlite:///./elsewhere.db"
    assert config.prepare_platform_env({"TBOT_DATABASE_URL_OVERRIDE": "sqlite:///x.db"},
                                       dotenv=dotenv) == "sqlite:///x.db"


# ---- the pairs ------------------------------------------------------------------

def test_the_pairs_are_asked_for_with_the_minimums_and_rechecked_here(client, alice, feed, at):
    """A desk that ignored the filter would answer with every pair it has."""
    feed.pairs.append(_pair(9, "AAPL", AAPL_LONG, 55.0))
    bot = _bot(alice)
    bot.step(clock.now())
    assert feed.asked == [{"min_edge": 57.0}]
    assert bot.watcher.pairs == {(TSLA_LONG, "TSLA"), (MU_LONG, "MU"), (NVDA_SHORT, "NVDA")}
    assert bot.watcher.tickers == ["MU", "NVDA", "TSLA"]


def test_each_session_day_reads_the_pairs_again(client, alice, feed, at):
    bot = _bot(alice)
    bot.step(clock.now())
    bot.step(clock.now())
    assert len(feed.asked) == 1                       # once per day, not per pass
    feed.pairs = [_pair(1, "MU", MU_LONG, 66.0)]
    at(8, 45, on=_weekday(at.day + timedelta(days=1)))
    feed.day = clock.now().date()
    bot.step(clock.now())
    assert len(feed.asked) == 2
    assert bot.watcher.pairs == {(MU_LONG, "MU")}


def test_a_desk_that_cannot_list_the_pairs_trades_nothing_and_asks_later(client, alice, feed, at):
    feed.down = desk.Unavailable(503, "the super signals service is not answering")
    bot = _bot(alice)
    bot.step(clock.now())
    bot.step(clock.now())
    assert bot.watcher is None
    assert "cannot list the best pairs" in _said(bot)
    feed.down = None
    bot.step(clock.now())
    assert bot.watcher is None                        # not before the retry interval
    bot.pairs_tried_at -= bot_mod.PAIRS_RETRY_S
    bot.step(clock.now())
    assert bot.watcher is not None


# ---- what it trades -------------------------------------------------------------

def test_a_live_signal_on_a_pair_is_bought_the_way_the_form_says(client, alice, feed, at):
    bot = _bot(alice)
    bot.step(clock.now())                             # pairs, desk, empty baseline
    feed.rows = [_row("tsla-1", key=TSLA_LONG, ticker="TSLA", time="10:30")]
    bot.step(clock.now())

    [pos] = _positions(client, alice)
    assert pos["strategy"] == "Auto/bot_best_pair" and pos["venue"] == "sandbox"
    assert pos["underlying"] == "TSLA" and pos["option_type"] == "call"
    # non-0DTE: the nearest listed expiry after today
    assert pos["expiration"] == (at.day + timedelta(days=2)).isoformat()
    # delta 0.25-0.45: the contract nearest the middle of the band
    assert pos["delta_at_entry"] == pytest.approx(0.35)
    assert (pos["tp_pct"], pos["sl_pct"]) == (10.0, 30.0)
    # smart limit: mid of 1.20 x 1.26, not the ask; 40% of $10,000 at $123 = 32
    assert "32 @ 1.23 limit" in pos["note"] and pos["contracts"] == 32
    assert bot.watcher.placed == 1


def test_a_short_pair_buys_a_put(client, alice, feed, at):
    bot = _bot(alice)
    bot.step(clock.now())
    feed.rows = [_row("nvda-1", key=NVDA_SHORT, ticker="NVDA")]
    bot.step(clock.now())
    [pos] = _positions(client, alice)
    assert pos["option_type"] == "put" and pos["delta_at_entry"] == pytest.approx(-0.35)


def test_a_pairs_type_elsewhere_or_a_stale_signal_never_trades(client, alice, feed, at):
    bot = _bot(alice)
    bot.step(clock.now())
    feed.rows = [_row("wrong-ticker", key=TSLA_LONG, ticker="MU"),
                 _row("under-min", key=AAPL_LONG, ticker="AAPL"),
                 _row("backfilled", source="backfill"),
                 _row("too-old", time="10:20")]
    bot.step(clock.now())
    assert _positions(client, alice) == []


def test_the_backlog_when_the_bot_starts_is_history(client, alice, feed, at):
    feed.rows = [_row("already-there")]
    bot = _bot(alice)
    bot.step(clock.now())
    bot.step(clock.now())
    assert _positions(client, alice) == []


# ---- never twice: the desk's watcher and the bot --------------------------------

def test_a_signal_the_desks_watcher_bought_is_never_bought_by_the_bot(
        client, alice, feed, at, monkeypatch):
    """The shared idempotency key on its own: the cooldown is taken out of the
    way so the bot reaches the order and the database is what says no."""
    ui, bot = _desk_watcher(alice), _bot(alice)
    ui_day = autotrade._super_tick(ui, clock.now(), None)
    bot.step(clock.now())
    feed.rows = [_row("both-want-it")]
    autotrade._super_tick(ui, clock.now(), ui_day)
    monkeypatch.setattr(signal_owner, "recent_entries", lambda *a, **k: {})
    bot.step(clock.now())

    [pos] = _positions(client, alice)
    assert pos["strategy"] == "Auto/best_pairs"
    assert bot.watcher.placed == 0
    assert any("already acted on" in e["message"] for e in bot.watcher.events)


def test_the_bot_keeps_the_desks_cooldown_on_a_ticker(client, alice, feed, at):
    """A different signal on a ticker the desk entered twenty minutes ago is
    the same idea arriving twice -- the hour holds across both traders."""
    ui, bot = _desk_watcher(alice), _bot(alice)
    ui_day = autotrade._super_tick(ui, clock.now(), None)
    bot.step(clock.now())
    feed.rows = [_row("ui-took-it")]
    autotrade._super_tick(ui, clock.now(), ui_day)
    assert len(_positions(client, alice)) == 1

    at(10, 52)
    feed.rows.append(_row("twenty-min-later", time="10:50"))
    bot.step(clock.now())
    assert len(_positions(client, alice)) == 1
    assert any("cooldown" in e["message"] for e in bot.watcher.events)

    at(11, 40)
    feed.rows.append(_row("an-hour-later", time="11:38"))
    bot.step(clock.now())
    assert len(_positions(client, alice)) == 2


def test_arming_the_desk_carries_the_bots_cooldown(client, alice, feed, at):
    bot = _bot(alice)
    bot.step(clock.now())
    feed.rows = [_row("bot-took-it")]
    bot.step(clock.now())
    bot.release()

    r = _arm(client, alice)
    assert r.status_code == 200, r.text
    assert "TSLA" in autotrade._WATCHERS[alice.tenant_id].last_entry
    client.post(f"{V1}/autotrade/stop", headers=alice.headers)


# ---- one owner of the signal desk ------------------------------------------------

def test_the_desk_refuses_a_signal_strategy_while_the_bot_holds_it(client, alice, feed, at):
    bot = _bot(alice)
    bot.step(clock.now())
    assert bot.owns_desk

    for strategy, extra in (("best_pairs", {}),
                            ("super_signals", {"tickers": "SPY", "signals": [TSLA_LONG]})):
        r = _arm(client, alice, strategy=strategy, **extra)
        assert r.status_code == 409, r.text
        assert "bot_best_pair" in r.json()["detail"]

    st = client.get(f"{V1}/autotrade/status", headers=alice.headers).json()
    assert st["active"] is False
    assert st["signal_desk_owner"]["kind"] == "bot_best_pair"
    assert st["signal_desk_owner"]["detail"] == "paper"

    # the level-cross watcher does not trade the signal desk, so it still arms
    r = _arm(client, alice, strategy="10min_intraday_move", tickers="SPY")
    assert r.status_code == 200, r.text
    client.post(f"{V1}/autotrade/stop", headers=alice.headers)


def test_the_bot_stands_by_while_the_desks_watcher_holds_it(client, alice, feed, at):
    r = _arm(client, alice)
    assert r.status_code == 200, r.text
    bot = _bot(alice)
    bot.step(clock.now())
    assert not bot.owns_desk and bot.watcher is None
    assert "standing by" in _said(bot)

    client.post(f"{V1}/autotrade/stop", headers=alice.headers)
    bot.step(clock.now())                             # takes the desk, baselines
    assert bot.owns_desk
    feed.rows = [_row("after-handover")]
    bot.step(clock.now())
    assert [p["strategy"] for p in _positions(client, alice)] == ["Auto/bot_best_pair"]


def test_signals_from_while_the_desk_held_it_are_not_the_bots(client, alice, feed, at):
    """Taking the desk over baselines, exactly as arming does: nothing that
    fired under the other owner is bought in a burst by the new one."""
    bot = _bot(alice)
    bot.step(clock.now())
    other = "desk:best_pairs:1.1:elsewhere"
    bot.release()
    assert signal_owner.claim(alice.tenant_id, other) is None
    feed.rows = [_row("fired-under-the-desk")]
    bot.step(clock.now())
    signal_owner.release(alice.tenant_id, other)
    bot.step(clock.now())
    bot.step(clock.now())
    assert _positions(client, alice) == []


def test_a_second_bot_for_the_same_operator_refuses_to_run(client, alice, feed, at):
    first, second = _bot(alice), _bot(alice)
    second.holder = "bot_best_pair:paper:99999:another-host"
    first.step(clock.now())
    with pytest.raises(bot_mod.AlreadyRunning):
        second.step(clock.now())


def test_a_crashed_bots_claim_expires_and_frees_the_desk(client, alice, feed, at):
    assert signal_owner.claim(alice.tenant_id, "bot_best_pair:paper:1:crashed") is None
    assert _arm(client, alice).status_code == 409
    at(10, 32 + signal_owner.TTL_S // 60 + 1)
    r = _arm(client, alice)
    assert r.status_code == 200, r.text
    client.post(f"{V1}/autotrade/stop", headers=alice.headers)


def test_stopping_the_bot_gives_the_desk_back(client, alice, feed, at):
    bot = _bot(alice)
    bot.step(clock.now())
    bot.release()
    assert signal_owner.current(alice.tenant_id) is None
    assert _arm(client, alice).status_code == 200
    client.post(f"{V1}/autotrade/stop", headers=alice.headers)


def test_the_desks_watcher_stands_down_if_the_bot_took_the_desk(client, alice, feed, at):
    """Its claim lapsed -- a frozen process -- and the bot took the desk: the
    watcher must stop rather than become a second owner."""
    assert _arm(client, alice).status_code == 200
    watcher = autotrade._WATCHERS[alice.tenant_id]
    signal_owner.release(alice.tenant_id, watcher.desk_holder)
    assert signal_owner.claim(alice.tenant_id, "bot_best_pair:paper:4242:host") is None
    assert autotrade._hold_desk(watcher) is False
    assert watcher.stop_flag.is_set()


# ---- the stops -------------------------------------------------------------------

@pytest.mark.parametrize("own,desk_running,swept", [
    ("auto", False, True), ("auto", True, False), ("off", False, False)])
def test_the_bot_sweeps_stops_only_while_the_desk_does_not(
        client, alice, feed, at, monkeypatch, own, desk_running, swept):
    from app.domains.trading.risk import monitor

    calls = []
    monkeypatch.setattr(monitor, "run_pass",
                        lambda *, tenant_id: calls.append(tenant_id) or {"events": []})
    bot = _bot(alice, own_monitor=own)
    monkeypatch.setattr(bot, "_desk_monitor_running", lambda: desk_running)
    bot.step(clock.now())
    assert calls == ([alice.tenant_id] if swept else [])


class _Readiness:
    def __init__(self, body=None, fail=False):
        self.body, self.fail = body, fail

    def get(self, url, timeout=None):
        import requests

        if self.fail:
            raise requests.ConnectionError("refused")

        class R:
            ok = True
            json = staticmethod(lambda: self.body)
        return R()


@pytest.mark.parametrize("http,running", [
    (_Readiness({"background": {"risk-monitor": {"running": True}}}), True),
    (_Readiness({"background": {"risk-monitor": {"running": False}}}), False),
    (_Readiness({"background": {}}), False),          # TBOT_NO_BACKGROUND=1
    (_Readiness(fail=True), False),                   # the desk is down
])
def test_whether_the_desk_watches_stops_is_read_from_its_readiness(alice, http, running):
    bot = _bot(alice)
    bot._http = http
    assert bot._desk_monitor_running() is running
