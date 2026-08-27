"""btc_research configuration — the spy_research pipeline retargeted at BTC.

Differences from spy_research/config.py:
  * TICKER BTC-USD, asymmetric TP 80 / SL 50 points (reach +80 before a 50-pt
    drop within 30 min)
  * crypto trades 24×7 — entries are open ALL DAY (00:00–23:59 CST), the
    "session" is the full CST calendar day, and the pre-market levels are the
    OVERNIGHT range (00:00–09:00 CST) used as an intraday reference level
  * POC bin sized for a six-figure instrument
"""
from datetime import time

TICKER = "BTC-USD"
TZ = "America/Chicago"

# ── backtest session (CST) — 24×7: entries open all day ───────────────────────
ENTRY_OPEN = time(0, 0)       # crypto trades round the clock — no entry curfew
ENTRY_CLOSE = time(23, 59)
RTH_OPEN = time(0, 0)         # crypto: the whole day is the session
RTH_CLOSE = time(23, 59)
PREMARKET_OPEN = time(0, 0)   # "pre-market" = overnight range 00:00 → 09:00
PM_END = time(9, 0)

# ── trade rules ───────────────────────────────────────────────────────────────
# Point-based barriers are the canonical, documented design (README, backtest.py,
# research.py, the live provider btc60_research_signal_bot.py, and the committed
# ensemble all use these). TP_PCT/SL_PCT below are an alternate percent
# formulation used only by btc_intraday_bot's live-emit lines; both are kept so
# every consumer resolves. (Restored 2026-07-15: a partial percent migration had
# removed TP_POINTS/SL_POINTS and broke backtest.py + research.py + the regen.)
TP_POINTS = 80.0              # +80 BTC points target (backtest/research/provider)
SL_POINTS = 50.0              # 50-point adverse stop
TP_PCT = 0.25                 # +0.25% target — alternate (btc_intraday_bot emit)
SL_PCT = 0.25                 # 0.25% adverse stop — alternate
TP_BARS = 12                  # target must hit within 60 min (12 x 5m)
SL_BARS = 12                  # stop live the whole hold (symmetric race)

# ── indicators ────────────────────────────────────────────────────────────────
ATR_LEN = 14
MACD_FAST, MACD_SLOW, MACD_SIG = 12, 26, 9
DIV_LOOKBACK = 30
POC_BIN = 25.0                # $25 volume-profile bins

# ── research grid ─────────────────────────────────────────────────────────────
NOISE_KS = [0.6, 0.9, 1.2]
VOL_MULTS = [0.8, 1.2]
WINDOWS = {                              # 24×7 session buckets (CST)
    "full_day":   (time(0, 0), time(23, 59)),   # all day
    "asia_0_8":   (time(0, 0), time(8, 0)),     # overnight / Asia
    "us_8_16":    (time(8, 0), time(16, 0)),    # US session
    "eve_16_24":  (time(16, 0), time(23, 59)),  # evening / late
}
MIN_TRADES_PER_DAY = 1.0
MAX_COMBO_SIZE = 3
