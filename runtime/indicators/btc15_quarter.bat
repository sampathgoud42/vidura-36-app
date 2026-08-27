@echo off
rem btc15_quarter.bat [HOURS] - refresh btc-15 signal CSVs + dashboard.
rem   HOURS optional lookback (default 2 = past two hours; the signal script
rem   adds a 20-minute context pad). Both the schtask "btc15_signal_q15"
rem   (no arg) and bot_btc_15_2.py ("2") refresh at :02/:17/:32/:47.
rem   Full backfill when needed: python btc15_signal.py --days 30
rem 30s grace so the just-closed 1m candle is queryable on Coinbase; the fresh
rem quarter mark is inserted as a PENDING row (is_matched=NA) and resolves on
rem the run after its close@T+15 exists. Writes are UPSERTS - resolved history
rem is never degraded or lost.
set "HRS=%~1"
if "%HRS%"=="" set "HRS=2"
ping -n 31 127.0.0.1 >nul
cd /d "%~dp0"   rem vendored runtime: this script's own folder
echo ===== %date% %time% (hours=%HRS%) ===== >> btc15_quarter.log
python btc15_signal.py --hours %HRS% >> btc15_quarter.log 2>&1
python bake_btc15_dashboard.py >> btc15_quarter.log 2>&1
