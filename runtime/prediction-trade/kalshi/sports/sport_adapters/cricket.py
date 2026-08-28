#!/usr/bin/env python3
"""sport_adapters/cricket.py — cricket plugin (pipeline/TBD; stub model).

Everything generic (state fetch, market mapping, TP policy) comes from
GenericGameAdapter; the model lives in
prediction-trade/sports/cricket/prediction_cricket_v1.py (a stub for now).
"""
from __future__ import annotations

from .generic import GenericGameAdapter


class CricketAdapter(GenericGameAdapter):
    name = "cricket"
    MODEL_MODULE = "cricket.prediction_cricket_v1"
    DEFAULTS = {"max_live_hours": 9, "stop_loss_c": 0}
