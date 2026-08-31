"""NIFTY_research configuration — the 0.25%/4h hunt on the volume-bearing
Nifty 50 ETF proxy NIFTYBEES.NS (tracks the Nifty 50 index 1:1 in percent terms; the
raw NSE index has no yfinance volume). Symmetric PERCENT target/stop +/-0.25%,
target within 4 hours, IST session, entries 09:30-14:00."""
from datetime import time

TICKER = "NIFTYBEES.NS"          # Nifty 50 ETF (volume-bearing proxy)
TZ = "Asia/Kolkata"

# ── session (IST) — entries 09:30-14:00; NSE cash 09:15-15:30 ─────────────────
ENTRY_OPEN = time(9, 30)
ENTRY_CLOSE = time(14, 0)
RTH_OPEN = time(9, 15)
RTH_CLOSE = time(15, 30)
PREMARKET_OPEN = time(9, 0)  # NSE pre-open 09:00-09:15 (thin; used for pm levels)

# ── trade rules — PERCENT, symmetric, 4-hour horizon ─────────────────────────
TP_PCT = 0.25                # +0.25% target
SL_PCT = 0.25                # 0.25% adverse stop
TP_BARS = 48                 # reach +0.25% within 4 hours (48 x 5m)
SL_BARS = 48                 # stop live the whole 4-hour hold (symmetric race)
# time-stop: flat at bar TP_BARS close if TP never hit; never past 15:30 IST

# ── indicators / custom-level params ─────────────────────────────────────────
ATR_LEN = 14
MACD_FAST, MACD_SLOW, MACD_SIG = 12, 26, 9
DIV_LOOKBACK = 30
POC_BIN = 0.1              # ETF price bin for the volume-profile histogram
ORB_MIN = 15                 # opening-range = first 15 min (09:15-09:30)
VWAP_BAND = 1.5              # VWAP sigma-band multiple for the custom bands

# ── research grid ─────────────────────────────────────────────────────────────
NOISE_KS = [0.0, 0.5, 0.8]           # allow k=0 (no range filter) — 0.25% is small
VOL_MULTS = [0.8, 1.2]               # volume must exceed m * 20-bar median
WINDOWS = {                          # entry sub-windows (IST)
    "full_0930_1400": (time(9, 30), time(14, 0)),
    "am_0930_1130":   (time(9, 30), time(11, 30)),
    "mid_1030_1300":  (time(10, 30), time(13, 0)),
}
MIN_TRADES_PER_DAY = 0.5     # target >= 1 signal every 2 days (>= 0.5/day)
MAX_COMBO_SIZE = 3
