"""coin_research configuration — the 0.40%/4h deep hunt on COIN.
Symmetric PERCENT target/stop +/-0.40% within 4 hours (48 x 5m bars).
Desk-wide session rule: signals only AFTER 08:45 CST; TP must hit BEFORE
14:35 CST (25 min before close) — outcomes truncate at the deadline."""
from datetime import time

TICKER = "COIN"
TZ = "America/Chicago"

# ── session (CST) ─────────────────────────────────────────────────────────────
ENTRY_OPEN = time(8, 45)     # signals may appear only after 8:45 AM CST
ENTRY_CLOSE = time(14, 0)    # last entry 2:00 PM CST
RTH_OPEN = time(8, 30)
RTH_CLOSE = time(15, 0)
TP_DEADLINE = time(14, 35)   # TP must hit before 2:35 PM CST (hard truncation)
PREMARKET_OPEN = time(3, 0)  # extended-hours bars before RTH open

# ── trade rules — PERCENT, symmetric, 4-hour horizon ─────────────────────────
TP_PCT = 0.4                # +0.40% target
SL_PCT = 0.4                # 0.40% adverse stop
TP_BARS = 48                 # reach +/-0.40% within 4 hours (48 x 5m)
SL_BARS = 48                 # stop live the whole hold (symmetric race)
# time-stop: flat at bar TP_BARS close or at TP_DEADLINE, whichever is first

# ── indicators / custom-level params ─────────────────────────────────────────
ATR_LEN = 14
MACD_FAST, MACD_SLOW, MACD_SIG = 12, 26, 9
DIV_LOOKBACK = 30
POC_BIN = 0.25              # $ bin for the volume-profile histogram
ORB_MIN = 15                 # opening-range = first 15 min (08:30-08:45 CST)
VWAP_BAND = 1.5              # VWAP sigma-band multiple for the custom bands

# ── research grid ─────────────────────────────────────────────────────────────
NOISE_KS = [0.0, 0.5, 0.8]           # allow k=0 (no range filter) — 0.40% is small
VOL_MULTS = [0.8, 1.2]               # volume must exceed m * 20-bar median
WINDOWS = {                          # entry sub-windows (CST), all >= 08:45
    "full_0845_1400": (time(8, 45), time(14, 0)),
    "am_0845_1130":   (time(8, 45), time(11, 30)),
    "mid_1030_1300":  (time(10, 30), time(13, 0)),
    "pm_1130_1400":   (time(11, 30), time(14, 0)),
}
MIN_TRADES_PER_DAY = 2.0     # report threshold; the A-book union maximizes freq
MAX_COMBO_SIZE = 3
