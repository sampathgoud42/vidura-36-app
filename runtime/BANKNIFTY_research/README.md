# BANKNIFTY_research — Nifty Bank 5m 0.30%/4h Super-Signals (PERCENT)

Deep signal hunt on the **Nifty Bank** index via its volume-bearing ETF
proxy **BANKBEES.NS** (the raw NSE index has no yfinance volume; the ETF
tracks it 1:1 in percent terms, so a +0.30% ETF move = a +0.30% index move).
IST session (NSE cash 09:15-15:30).

**Target:** reach **+/-0.30%** in the trade direction **before** a 0.30% adverse
move, **within 4 hours** (48 x 5m bars). Entries **09:30-14:00 IST**. Enter next
5m bar open; symmetric stop live the whole hold; flat at bar 48 (time-stop) and
never past 15:30 IST.

    python research.py    # 57-session grid -> results/all_configs.csv + REPORT.md
    python iterate.py     # precision stacks + greedy ensemble -> results/ensemble.csv
    python banknifty_intraday_bot.py --once / --backfill-today / (live loop, poll 60s)

## Custom price + volume layer (this hunt's additions)
- **Custom levels:** opening-range (ORB, first 15 min) high/low, VWAP sigma-bands
  (+/-1.5 sigma of typical-price-vs-VWAP), prior-day POC / floor pivots / S1-R1.
- **Custom volume:** relative volume (rvol vs 20-bar median), rising-volume flag,
  cumulative volume delta (CVD) + slope, MFM volume-delta surge/dump.
- **Custom signals** (blocks combining a price event with volume confirmation):
  `orb_break_up/dn(_v)`, `vwap_reclaim_v`, `rvol_thrust_up/dn`, `above/below_vwap_v`,
  `vwap_lo_bounce` / `vwap_hi_reject`, `cvd_up/dn(_v)`, `mom_ignite_up/dn`,
  `rsi_thrust_up/dn`. These carry most of the surviving A-book edge.

## A-book = the precision union (results/abook_ensemble.csv)
Book label rule (assigned at bot load): **TP-before-SL > 95% -> A, else B.** The
hardcoded `A_BOOK` is a compact, diverse union of near-perfect families
(30 trades, 0 stops, **100% TP-before-SL**,
**0.53/day** over 57 sessions). `results/ensemble.csv` holds a
trimmed B-book tier (~88-92% TP-before-SL). See REPORT.md for the full verdict.

FOLDER-LEVEL ONLY: not registered in super_research.config, no schedule, not in
the web UI. Backend research bot.
