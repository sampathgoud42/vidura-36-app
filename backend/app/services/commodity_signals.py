"""Live gold15/silver15/oil15 DMI signal snapshot for the bot-station UI.

Wraps runtime/indicators/commodity_dmi.py — the same DI-dominance engine
the v2 commodity bots trade on — so the desk can show a live call/put
readout per commodity without spinning up a bot process. Cached in-memory
(55s TTL, just under the frontend's 60s poll) since each refresh makes three
yfinance calls.
"""
from __future__ import annotations

import sys
import threading
import time

from app.core.config import get_settings

LABELS = {"gold15": "Gold", "silver15": "Silver", "oil15": "WTI Oil"}

_CACHE: dict = {}
_LOCK = threading.Lock()
_TTL = 55

_dmi_path_ready = False


def _dmi_module():
    global _dmi_path_ready
    if not _dmi_path_ready:
        indicators_dir = get_settings().source_repo / "indicators"
        if str(indicators_dir) not in sys.path:
            sys.path.insert(0, str(indicators_dir))
        _dmi_path_ready = True
    import commodity_dmi  # local import: only resolvable once the path above is set
    return commodity_dmi


def _row(bot_key: str, sc: dict) -> dict:
    m1, m2 = sc.get("m1") or {}, sc.get("m2") or {}
    return {
        "bot": bot_key,
        "label": LABELS.get(bot_key, bot_key),
        "last": sc.get("live_price"),
        "signal": sc.get("signal"),
        "direction": sc.get("direction"),
        "m1_side": sc.get("m1_side"),
        "m1_adx": m1.get("adx"), "m1_pdi": m1.get("plus_di"),
        "m1_mdi": m1.get("minus_di"), "m1_slope": m1.get("adx_slope"),
        "m2_side": sc.get("m2_side"),
        "m2_adx": m2.get("adx"), "m2_pdi": m2.get("plus_di"),
        "m2_mdi": m2.get("minus_di"), "m2_slope": m2.get("adx_slope"),
        "bars_1m": sc.get("bars_1m"), "bars_2m": sc.get("bars_2m"),
    }


def commodities_snapshot(force: bool = False) -> dict:
    with _LOCK:
        cached = _CACHE.get("snap")
        if not force and cached is not None and time.monotonic() - cached["at"] < _TTL:
            return {
                "rows": cached["rows"], "meta": cached["meta"],
                "age_s": int(time.monotonic() - cached["at"]),
            }

    dmi = _dmi_module()
    started = time.time()
    rows: list[dict] = []
    for bot_key in dmi.SYMBOLS:
        try:
            sc = dmi.score_commodity_dmi(bot_key)
            rows.append(_row(bot_key, sc))
        except Exception as exc:  # noqa: BLE001
            rows.append({"bot": bot_key, "label": LABELS.get(bot_key, bot_key), "error": str(exc)})

    meta = {"source": "yfinance", "took_s": round(time.time() - started, 1), "scanned": len(rows)}
    with _LOCK:
        _CACHE["snap"] = {"at": time.monotonic(), "rows": rows, "meta": meta}
    return {"rows": rows, "meta": meta, "age_s": 0}
