"""Registry of launchable bot scripts in the 38trades source repo.

Versions map to real files on disk; ``exists`` is checked live so the
API reports honestly when a script is renamed or missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import get_settings


@dataclass(frozen=True)
class BotVersion:
    version: str
    rel_script: str  # relative to the source repo root
    default: bool = False


@dataclass(frozen=True)
class BotSpec:
    key: str
    name: str
    category: str  # btc | sports
    cadence: str | None
    versions: tuple[BotVersion, ...]
    # How the subprocess is launched; drives env/cwd in bot_manager.
    launch_style: str = "cwd_customer"  # cwd_customer | env_customer | argv_customer
    extra: dict = field(default_factory=dict)

    def version_or_default(self, version: str | None) -> BotVersion:
        if version is None:
            for v in self.versions:
                if v.default:
                    return v
            return self.versions[0]
        for v in self.versions:
            if v.version == version:
                return v
        raise KeyError(f"Unknown version '{version}' for bot '{self.key}'")


_BTC15_DIR = "prediction-trade/kalshi/btc/btc15"
_BTC60_DIR = "prediction-trade/kalshi/btc/btc60"
_SPORTS_DIR = "prediction-trade/kalshi/sports"
_GOLD15_DIR = "prediction-trade/kalshi/commodities/gold15"
_SILVER15_DIR = "prediction-trade/kalshi/commodities/silver15"
_OIL15_DIR = "prediction-trade/kalshi/commodities/oil15"

BOTS: dict[str, BotSpec] = {
    "btc15": BotSpec(
        key="btc15",
        name="Kalshi BTC 15-minute bot",
        category="btc",
        cadence="15m",
        # v2 is the requirement-named default; v5 is the currently-live engine.
        versions=(
            BotVersion("v2", f"{_BTC15_DIR}/v2_bot_kalshi_btc15.py", default=True),
            BotVersion("v3", f"{_BTC15_DIR}/v3_bot_kalshi_btc15.py"),
            BotVersion("v4", f"{_BTC15_DIR}/v4_bot_kalshi_btc15.py"),
            BotVersion("v5", f"{_BTC15_DIR}/v5_bot_btc_15_2.py"),
        ),
        # btc15 bots resolve .env/PEM against the CWD -> launch from user folder.
        launch_style="cwd_customer",
    ),
    "btc60": BotSpec(
        key="btc60",
        name="Kalshi BTC 60-minute bot",
        category="btc",
        cadence="60m",
        versions=(
            BotVersion("fable5", f"{_BTC60_DIR}/bot_kalshi_btc60_fable5.py", default=True),
            BotVersion("burst", f"{_BTC60_DIR}/bot_kalshi_btc60_burst.py"),
        ),
        # btc60 bots take BTC_CUSTOMERS_DIR/BTC_CUSTOMER env vars.
        launch_style="env_customer",
    ),
    "sports": BotSpec(
        key="sports",
        name="Kalshi multi-sport bot",
        category="sports",
        cadence="live-match",
        versions=(
            BotVersion("main", f"{_SPORTS_DIR}/bot_kalshi_main.py", default=True),
            BotVersion("v1", f"{_SPORTS_DIR}/bot_kalshi_sports_v1.py"),
            BotVersion("v2", f"{_SPORTS_DIR}/bot_kalshi_sports_v2.py"),
        ),
        # sports bots take the customer name as argv[1] plus SPORTS_* env vars.
        launch_style="argv_customer",
    ),
    "parley": BotSpec(
        key="parley",
        name="Kalshi live-sport parlay bot",
        category="sports",
        cadence="live-match",
        versions=(
            BotVersion("v1", f"{_SPORTS_DIR}/bot_kalshi_parley.py", default=True),
        ),
        # Same family as the sports bots — it imports their engine, so it
        # inherits the customer-as-argv[1] contract along with the plumbing.
        launch_style="argv_customer",
    ),
    "gold15": BotSpec(
        key="gold15",
        name="Kalshi Gold 15-minute bot",
        category="commodities",
        cadence="15m",
        # v2 is the DMI DI-dominance engine (ported from tradier-bot) and is
        # now the default; v1's Yahoo trend/volume score is still selectable.
        versions=(
            BotVersion("v1", f"{_GOLD15_DIR}/bot_kalshi_gold15.py"),
            BotVersion("v2", f"{_GOLD15_DIR}/v2_bot_kalshi_gold15.py", default=True),
        ),
        launch_style="cwd_customer",
    ),
    "silver15": BotSpec(
        key="silver15",
        name="Kalshi Silver 15-minute bot",
        category="commodities",
        cadence="15m",
        versions=(
            BotVersion("v1", f"{_SILVER15_DIR}/bot_kalshi_silver15.py"),
            BotVersion("v2", f"{_SILVER15_DIR}/v2_bot_kalshi_silver15.py", default=True),
        ),
        launch_style="cwd_customer",
    ),
    "oil15": BotSpec(
        key="oil15",
        name="Kalshi WTI Oil 15-minute bot",
        category="commodities",
        cadence="15m",
        versions=(
            BotVersion("v1", f"{_OIL15_DIR}/bot_kalshi_oil15.py"),
            BotVersion("v2", f"{_OIL15_DIR}/v2_bot_kalshi_oil15.py", default=True),
        ),
        launch_style="cwd_customer",
    ),
}


def script_path(spec: BotSpec, version: BotVersion) -> Path:
    return get_settings().source_repo / version.rel_script


def get_bot(bot_key: str) -> BotSpec:
    try:
        return BOTS[bot_key]
    except KeyError:
        raise KeyError(f"Unknown bot '{bot_key}' (known: {', '.join(BOTS)})") from None


def registry_report() -> list[dict]:
    report = []
    for spec in BOTS.values():
        versions = [
            {
                "version": v.version,
                "script": str(script_path(spec, v)),
                "exists": script_path(spec, v).is_file(),
                "default": v.default,
            }
            for v in spec.versions
        ]
        report.append(
            {
                "key": spec.key,
                "name": spec.name,
                "category": spec.category,
                "cadence": spec.cadence,
                "versions": versions,
            }
        )
    return report
