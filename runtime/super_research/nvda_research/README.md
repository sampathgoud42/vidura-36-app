# nvda_research — NVDA 5m 0.30%/4h Super-Signals (PERCENT, custom price+volume)

Deep hunt on NVDA: reach **+/-0.30%** before a 0.30% adverse move, **within
4 hours** (48 x 5m bars). **Desk session rule: signals only AFTER 8:45 AM CST;
the TP must hit BEFORE 2:35 PM CST** (25 min before close — outcomes truncate
there). Entries 08:45-14:00 CST, next-bar-open entry, symmetric stop.

    python research.py    # grid -> results/all_configs.csv + REPORT.md
    python iterate.py     # stacks + greedy ensemble -> results/ensemble.csv
    python nvda_intraday_bot.py --once / --backfill-today / (live loop)

Custom layer: ORB (first 15 min) levels, VWAP sigma-bands, rvol, CVD+slope,
RSI(14), momentum-ignition — blocks pair a price event with volume confirmation.

**A-book** = compact precision union (7 families, 1 LONG + 6 SHORT): 21 trades,
0 stops, **100.0% TP-before-SL @ 0.35/day** over 60
sessions (results/abook_ensemble.csv). B-book = trimmed results/ensemble.csv.
Book rule at bot load: TP-before-SL > 95% -> A, else B.

Live: super_signal_bot.py --category etf|stock spawns nvda_intraday_bot.py
--once each cycle -> nvda_intraday_signals.csv -> central ledgers -> desk.
