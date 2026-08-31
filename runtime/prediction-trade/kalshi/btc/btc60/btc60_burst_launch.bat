@echo off
rem ===========================================================================
rem  btc60_burst_launch.bat — launch the Kalshi BTC-60 bot (research-signal
rem  edition) with LIVE console logs (mirrored to btc60_burst_YYYYMMDD.log).
rem
rem  Two processes:
rem    1. btc60_research_signal_bot.py — the SIGNAL PROVIDER (super_research/
rem       btc_research playbook -> btc60_research_signal.json handoff). Started
rem       once, in its own window; runs 24x7 and survives the daily restart.
rem    2. bot_kalshi_btc60_burst.py — the KALSHI EXECUTOR. Consumes ONLY the
rem       handoff; relaunched here on exit code 42 (its 08:00 CST daily reset).
rem
rem  Usage:
rem      btc60_burst_launch.bat           -> LIVE trading (REAL MONEY)
rem      btc60_burst_launch.bat paper     -> paper trading (simulated fills)
rem
rem  Bankroll rules (btc60_burst_state.json):
rem    * first launch seeds $100; max 25%% of bankroll per trade
rem    * daily 08:00 America/Chicago reset: profit day -> keep 50%% of the
rem      profit in the bankroll, bank the other 50%%; loss day -> carry as-is.
rem ===========================================================================
setlocal
cd /d "%~dp0"
title Kalshi BTC-60 research-signal bot

if /i "%~1"=="paper" (
    set "DRY_RUN_MODE=TRUE"
    echo [launcher] PAPER mode
) else (
    set "DRY_RUN_MODE=FALSE"
    echo [launcher] *** LIVE MODE - REAL MONEY ***
)

set "PYTHONIOENCODING=utf-8"
set "BTC_RESTART_ON_RESET=1"

rem ── start the research signal provider in its own window (once) ────────────
echo [launcher] starting research signal provider...
start "BTC research signal provider" cmd /k "cd /d "%~dp0" && set PYTHONIOENCODING=utf-8 && python -u btc60_research_signal_bot.py --poll 60"

:run
python -u bot_kalshi_btc60_burst.py
rem exit code 42 = the bot performed its 08:00 CST daily bankroll reset and
rem asked for a fresh process (new day-stamped log). Relaunch in this console.
if %errorlevel%==42 (
    echo [launcher] 08:00 daily reset - relaunching executor for the new day...
    goto :run
)

echo.
echo [launcher] executor exited (%date% %time%)
echo [launcher] NOTE: the signal-provider window is still open - close it manually.
pause
endlocal
