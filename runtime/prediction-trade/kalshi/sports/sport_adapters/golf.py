#!/usr/bin/env python3
"""sport_adapters/golf.py — golf plugin (pipeline/TBD; stub model).

Everything generic (state fetch, market mapping, TP policy) comes from
GenericGameAdapter; the model lives in
prediction-trade/sports/golf/prediction_golf_v1.py (a stub for now).

NOTE: Kalshi golf is mostly tournament OUTRIGHTS; the engine's
head-to-head discovery drops those, so activating golf will also need
a filter_discovered override here (keep outrights, cap the field).
"""
from __future__ import annotations

from .generic import GenericGameAdapter


class GolfAdapter(GenericGameAdapter):
    name = "golf"
    MODEL_MODULE = "golf.prediction_golf_v1"
    DEFAULTS = {"max_live_hours": 8, "stop_loss_c": 0}
