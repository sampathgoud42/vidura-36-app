@echo off
rem commodity15_quarter.bat [HOURS] - refresh gold/silver/oil 15-min signal CSVs.
rem   HOURS optional lookback (default: uses --days 5 for full window).
rem   The bot scheduler calls this at :02/:17/:32/:47 each hour.
set "HRS=%~1"
cd /d "%~dp0"
echo ===== %date% %time% (hours=%HRS%) ===== >> commodity15_quarter.log
if "%HRS%"=="" (
    python commodity15_signal.py >> commodity15_quarter.log 2>&1
) else (
    python commodity15_signal.py --hours %HRS% >> commodity15_quarter.log 2>&1
)
