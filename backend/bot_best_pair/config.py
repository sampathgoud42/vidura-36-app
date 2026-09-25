"""bot_best_pair's configuration: its own file, plus the desk's platform settings.

Two layers, and the split is deliberate:

  bot_best_pair.env    WHAT this bot trades and how -- operator, venue, the
                       pair minimums, the contract, sizing, exits, the window.
                       Its own file beside this one, so its settings never
                       ride on the desk's.
  <project>/.env       WHERE everything lives -- the database, the credential
                       master key, paper-only, the signal desk's URL. Shared
                       with the desk on purpose: a bot on another database
                       would dedupe against nothing, and one with another
                       master key could not read the operator's Tradier key.

A BOT_BEST_PAIR_* variable already set in the environment beats the file, so a
one-off ``BOT_BEST_PAIR_LIVE=false ./bot_best_pair.sh`` needs no edit.

Every value is checked here, and a bad one stops the bot before it trades,
with every problem listed at once -- the same refuse-never-clamp rule as the
desk. A clamped stop is a stop nobody chose.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
ENV_FILE = HERE / "bot_best_pair.env"
PREFIX = "BOT_BEST_PAIR_"

# The desk's database when nothing else says so -- tools/appctl.py starts the
# API on exactly this file (its _api_env). The two MUST agree: the bot's
# duplicate protection is rows in that database.
DESK_DEFAULT_DB = "var/app-v2.db"

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


class ConfigError(ValueError):
    """The bot will not start. Carries every problem, one per line."""


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines. Blank lines and # comments are skipped, a trailing
    `` # note`` is dropped, and surrounding quotes are removed."""
    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = re.split(r"\s+#", value, maxsplit=1)[0].strip().strip('"').strip("'")
        if key.strip():
            out[key.strip()] = value
    return out


def prepare_platform_env(environ: dict[str, str] | None = None, *,
                         dotenv: Path = PROJECT_ROOT / ".env") -> str:
    """Point this process at the desk's own database and settings.

    The project .env is folded into the environment the way tools/appctl.py
    folds it in for the API (an exported variable still wins), then the
    database defaults to the file the API runs on. Returns the database URL,
    so the banner can show which one this bot is trading against.
    """
    env = os.environ if environ is None else environ
    for key, value in read_env_file(dotenv).items():
        env.setdefault(key, value)
    env.setdefault("TBOT_DATABASE_URL_OVERRIDE",
                   f"sqlite:///{(PROJECT_ROOT / DESK_DEFAULT_DB).as_posix()}")
    return env["TBOT_DATABASE_URL_OVERRIDE"]


@dataclass(frozen=True)
class BotConfig:
    operator: str
    live: bool
    min_edge: float | None
    min_win_pct: float | None
    min_net_r: float | None
    delta_min: float
    delta_max: float
    zero_dte: bool
    tp_pct: float
    sl_pct: float
    buy_pct: float
    tolerance_pct: float
    min_contracts: int
    window_open: str
    window_close: str
    own_monitor: bool
    desk_url: str
    source: str = ""

    @property
    def venue(self) -> str:
        return "tradier" if self.live else "tradier_sandbox"

    def minimums(self) -> dict[str, float]:
        """The /best-pairs query: only the minimums that are set."""
        mins = {"min_edge": self.min_edge, "min_win_pct": self.min_win_pct,
                "min_net_r": self.min_net_r}
        return {k: v for k, v in mins.items() if v is not None}

    def describe_minimums(self) -> str:
        parts = [f"edge >= {self.min_edge:g}" if self.min_edge is not None else "",
                 f"win % >= {self.min_win_pct:g}" if self.min_win_pct is not None else "",
                 f"net R >= {self.min_net_r:+g}" if self.min_net_r is not None else ""]
        return ", ".join(p for p in parts if p) or "no minimums"

    def meets_minimums(self, pair: Mapping) -> bool:
        """Checked again on this side of the wire. A desk that ignored an
        unknown query parameter would answer with every pair it has, and the
        bot would trade the ones the operator filtered out."""
        for key, field in (("min_edge", "edge"), ("min_win_pct", "win_pct"),
                           ("min_net_r", "net_r")):
            floor = getattr(self, key)
            if floor is None:
                continue
            try:
                if float(pair.get(field)) < floor:
                    return False
            except (TypeError, ValueError):
                return False
        return True

    def banner(self) -> list[str]:
        return [
            f"operator     {self.operator}  on {'LIVE Tradier' if self.live else 'Tradier sandbox (paper)'}",
            f"pairs        best ticker + signal pairs with {self.describe_minimums()}",
            f"contract     delta {self.delta_min:g}-{self.delta_max:g}, "
            f"{'0DTE allowed before the auto cutoff' if self.zero_dte else 'non-0DTE (nearest expiry after today)'}",
            f"exits        TP +{self.tp_pct:g}% over entry, SL -{self.sl_pct:g}% below entry "
            f"(both resting at the venue)",
            f"sizing       {self.buy_pct:g}% of option buying power, ±{self.tolerance_pct:g}%, "
            f"min {self.min_contracts} contract(s)",
            "order        smart limit -- the desk's BUY",
            f"window       {self.window_open}-{self.window_close} CST",
            f"stops        {'swept by this bot whenever the desk is not running' if self.own_monitor else 'left to the desk (own monitor off)'}",
        ]


def _number(values: Mapping[str, str], name: str, problems: list[str], *,
            default: str | None = None, optional: bool = False,
            lo: float | None = None, hi: float | None = None,
            integer: bool = False) -> float | int | None:
    raw = (values.get(PREFIX + name) or "").strip()
    if not raw:
        if optional:
            return None
        raw = default or ""
    if raw.lower() in ("any", "none") and optional:
        return None
    try:
        value = int(raw) if integer else float(raw)
    except ValueError:
        problems.append(f"{PREFIX}{name}={raw!r} is not a number")
        return None
    if value != value or value in (float("inf"), float("-inf")):
        problems.append(f"{PREFIX}{name}={raw!r} is not a real number")
        return None
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        problems.append(f"{PREFIX}{name}={raw} is outside {lo}..{hi}")
        return None
    return value


def _flag(values: Mapping[str, str], name: str, default: bool,
          problems: list[str]) -> bool:
    raw = (values.get(PREFIX + name) or "").strip().lower()
    if not raw:
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    problems.append(f"{PREFIX}{name}={raw!r} is not true/false")
    return default


def load(environ: Mapping[str, str] | None = None, *, file: Path = ENV_FILE) -> BotConfig:
    """Read bot_best_pair.env, let the environment override it, and refuse
    anything the desk's own arm form would refuse."""
    from app.domains.trading.risk.validation import RiskRefused, validate_entry

    env = os.environ if environ is None else environ
    values = read_env_file(file)
    values.update({k: v for k, v in env.items() if k.startswith(PREFIX)})
    problems: list[str] = []

    operator = (values.get(PREFIX + "OPERATOR") or "").strip()
    if not operator:
        problems.append(f"{PREFIX}OPERATOR is empty -- set it to the desk sign-in "
                        f"(operator slug) whose Tradier account this bot trades")

    window_open = (values.get(PREFIX + "WINDOW_OPEN") or "08:30").strip()
    window_close = (values.get(PREFIX + "WINDOW_CLOSE") or "14:30").strip()
    if not (_HHMM.match(window_open) and _HHMM.match(window_close)):
        problems.append("the window must be HH:MM to HH:MM (CST), e.g. 08:30 and 14:30")
    elif window_open >= window_close:
        problems.append(f"the window {window_open}-{window_close} must start before it ends")

    delta_min = _number(values, "DELTA_MIN", problems, default="0.25", lo=0, hi=1)
    delta_max = _number(values, "DELTA_MAX", problems, default="0.45", lo=0, hi=1)
    if delta_min is not None and delta_max is not None and not (0 < delta_min < delta_max <= 1):
        problems.append(f"the delta range {delta_min:g}-{delta_max:g} must be 0 < min < max <= 1")

    tp_pct = _number(values, "TP_PCT", problems, default="10")
    sl_pct = _number(values, "SL_PCT", problems, default="30")
    buy_pct = _number(values, "BUY_PCT", problems, default="40")
    if None not in (tp_pct, sl_pct, buy_pct):
        try:
            validate_entry(side="call", buy_pct=buy_pct, tp_pct=tp_pct, sl_pct=sl_pct)
        except RiskRefused as exc:
            problems.append(str(exc))

    tolerance_pct = _number(values, "SIZE_TOLERANCE_PCT", problems, default="10", lo=0, hi=99)
    min_contracts = _number(values, "MIN_CONTRACTS", problems, default="1", lo=1, hi=500,
                            integer=True)

    monitor = (values.get(PREFIX + "OWN_MONITOR") or "auto").strip().lower()
    if monitor not in ("auto", "off"):
        problems.append(f"{PREFIX}OWN_MONITOR={monitor!r} must be auto or off")

    port = (env.get("TBOT_PORT") or "8791").strip()
    desk_url = (values.get(PREFIX + "DESK_URL") or f"http://127.0.0.1:{port}").strip().rstrip("/")

    cfg = BotConfig(
        operator=operator,
        live=_flag(values, "LIVE", False, problems),
        min_edge=_number(values, "MIN_EDGE", problems, optional=True, lo=0, hi=100),
        min_win_pct=_number(values, "MIN_WIN_PCT", problems, optional=True, lo=0, hi=100),
        min_net_r=_number(values, "MIN_NET_R", problems, optional=True, lo=-1000, hi=1000),
        delta_min=delta_min or 0.0, delta_max=delta_max or 0.0,
        zero_dte=_flag(values, "ZERO_DTE", False, problems),
        tp_pct=tp_pct or 0.0, sl_pct=sl_pct or 0.0, buy_pct=buy_pct or 0.0,
        tolerance_pct=0.0 if tolerance_pct is None else tolerance_pct,
        min_contracts=int(min_contracts or 0),
        window_open=window_open, window_close=window_close,
        own_monitor=monitor != "off", desk_url=desk_url, source=str(file))
    if problems:
        raise ConfigError("\n".join(problems))
    return cfg
