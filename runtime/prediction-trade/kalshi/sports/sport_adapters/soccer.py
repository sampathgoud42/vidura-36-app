#!/usr/bin/env python3
"""sport_adapters/soccer.py — soccer plugin (pipeline/TBD; stub model).

Everything generic (state fetch, market mapping, TP policy) comes from
GenericGameAdapter; the model lives in
prediction-trade/sports/soccer/prediction_soccer_v1.py (a stub for now).
"""
from __future__ import annotations

from .generic import GenericGameAdapter


class SoccerAdapter(GenericGameAdapter):
    name = "soccer"
    MODEL_MODULE = "soccer.prediction_soccer_v1"
    DEFAULTS = {"max_live_hours": 3, "stop_loss_c": 0}
