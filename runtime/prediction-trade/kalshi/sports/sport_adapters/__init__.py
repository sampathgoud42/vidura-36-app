#!/usr/bin/env python3
"""
sport_adapters — sport-plugin registry for bot_kalshi_main.py.
==============================================================
To plug in a NEW sport:
  1. create sport_adapters/<sport>.py with ``class <Sport>Adapter(SportAdapter)``
     (see base.py for the contract — every hook has a safe default);
  2. add it to ``_REGISTRY`` below;
  3. add "<sport>" to MAIN_SPORTS_LIST and its <SPORT>_BANK / <SPORT>_CONTRACTS /
     <SPORT>_STOP_LOSS_PCT knobs to kaslhi_sports.env.
The engine (discovery, execution, guardian, bank risk) needs no changes.
"""
from __future__ import annotations

import importlib

from .base import SportAdapter, SportBook, SportConfig, sport_env  # noqa: F401

_REGISTRY = {
    # active (full prediction models)
    "tennis": (".tennis", "TennisAdapter"),
    "baseball": (".baseball", "BaseballAdapter"),
    # pipeline (GenericGameAdapter + STUB models — always WAIT until the model
    # in prediction-trade/sports/<sport>/prediction_<sport>_v1.py is implemented)
    "basketball": (".basketball", "BasketballAdapter"),
    "cricket": (".cricket", "CricketAdapter"),
    "hockey": (".hockey", "HockeyAdapter"),
    "soccer": (".soccer", "SoccerAdapter"),
    "golf": (".golf", "GolfAdapter"),
}


def available() -> list[str]:
    return sorted(_REGISTRY)


def create_adapter(sport: str) -> SportAdapter:
    """Instantiate the adapter for ``sport`` with its resolved SportConfig.
    Imports lazily so one broken/missing sport module can't break the others."""
    key = (sport or "").strip().lower()
    if key not in _REGISTRY:
        raise KeyError(f"no adapter registered for sport {sport!r} "
                       f"(available: {', '.join(available())})")
    mod_name, cls_name = _REGISTRY[key]
    module = importlib.import_module(mod_name, package=__name__)
    cls = getattr(module, cls_name)
    return cls(SportConfig.load(key, getattr(cls, "DEFAULTS", None)))
