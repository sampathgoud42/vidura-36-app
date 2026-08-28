#!/usr/bin/env python3
"""sport_adapters/basketball.py — basketball plugin (pipeline/TBD; stub model).

Everything generic (state fetch, market mapping, TP policy) comes from
GenericGameAdapter; the model lives in
prediction-trade/sports/basketball/prediction_basketball_v1.py (a stub for now).
"""
from __future__ import annotations

from .generic import GenericGameAdapter


class BasketballAdapter(GenericGameAdapter):
    name = "basketball"
    MODEL_MODULE = "basketball.prediction_basketball_v1"
    DEFAULTS = {"max_live_hours": 4, "stop_loss_c": 0}
