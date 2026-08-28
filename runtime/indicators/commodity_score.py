"""
commodity_score.py — multi-timeframe trend + volume score for commodities.

Mirrors the cb_btc_signal.py scoring approach but uses Yahoo Finance
for Gold (GC=F), Silver (SI=F), and WTI Oil (CL=F).

For each timeframe (5m, 15m, 30m, 1h, 1d):
    trend  = +1 if recent close > 5-bars-ago close, else -1
    volume = 2x multiplier if recent 3-bar volume > average volume
    score  = trend * multiplier

overall_score = sum across all timeframes  (range: -10 to +10)

BUY  = score > 0   (confirms LONG signal)
SELL = score < 0   (confirms SHORT signal)
NEUTRAL = 0        (no confirmation either way)
"""
from __future__ import annotations

import yfinance as yf

SYMBOLS = {
    "gold15":   "GC=F",
    "silver15": "SI=F",
    "oil15":    "CL=F",
}

TIMEFRAMES = [
    {"interval": "5m",  "period": "5d",  "label": "5min"},
    {"interval": "15m", "period": "5d",  "label": "15min"},
    {"interval": "30m", "period": "5d",  "label": "30min"},
    {"interval": "1h",  "period": "30d", "label": "1hour"},
    {"interval": "1d",  "period": "60d", "label": "1day"},
]


def _analyze_timeframe(df) -> int:
    if df.empty or len(df) < 5:
        return 0
    recent_close = df["Close"].iloc[-1]
    prior_close = df["Close"].iloc[-5]
    trend = 1 if recent_close > prior_close else -1
    recent_vol = df["Volume"].iloc[-3:].mean()
    avg_vol = df["Volume"].mean()
    return trend * 2 if recent_vol > avg_vol else trend


def get_signal_text(score: int) -> str:
    if score > 0:
        return "BUY"
    elif score < 0:
        return "SELL"
    return "NEUTRAL"


def score_commodity(bot_key: str, verbose: bool = False) -> dict:
    """Score a commodity across multiple timeframes.

    Returns:
        {"overall_score": int, "signal": "BUY"|"SELL"|"NEUTRAL",
         "live_price": float, "details": {label: score, ...}}
    """
    symbol = SYMBOLS.get(bot_key)
    if not symbol:
        return {"overall_score": 0, "signal": "NEUTRAL", "live_price": 0.0,
                "details": {}}

    t = yf.Ticker(symbol)
    details = {}
    total = 0
    live_price = 0.0

    for tf in TIMEFRAMES:
        try:
            df = t.history(period=tf["period"], interval=tf["interval"])
            s = _analyze_timeframe(df)
            details[tf["label"]] = s
            total += s
            if tf["label"] == "5min" and not df.empty:
                live_price = float(df["Close"].iloc[-1])
        except Exception as e:
            details[tf["label"]] = 0
            if verbose:
                print(f"[score] {symbol} {tf['label']}: {e}")

    signal = get_signal_text(total)
    if verbose:
        print(f"[score] {symbol}: {' | '.join(f'{k}={v:+d}' for k, v in details.items())}"
              f" => overall={total:+d} ({signal})")

    return {"overall_score": total, "signal": signal,
            "live_price": live_price, "details": details}


if __name__ == "__main__":
    for key in SYMBOLS:
        score_commodity(key, verbose=True)
        print()
