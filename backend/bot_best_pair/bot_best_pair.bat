@echo off
REM Start the best-pairs bot: the daily report's best ticker + signal pairs,
REM auto-traded on Tradier by a process of its own. Runs until Ctrl-C.
REM
REM   backend\bot_best_pair\bot_best_pair.bat           trade
REM   backend\bot_best_pair\bot_best_pair.bat --check   check the setup, trade nothing
REM
REM Settings: bot_best_pair.env beside this script. The database, the master
REM key and paper-only come from the project .env, shared with the desk, so the
REM bot and the desk see the same positions and never trade the same signal.
setlocal
cd /d "%~dp0..\.."
set "RC=0"
if not exist ".venv\Scripts\python.exe" (
  echo No .venv here yet - run setup.bat first.
  set "RC=1"
  goto :done
)
set "PYTHONPATH=%CD%\backend;%PYTHONPATH%"
".venv\Scripts\python.exe" -m bot_best_pair %*
set "RC=%ERRORLEVEL%"

:done
REM Opened by double-click, the window would close on a refusal before the
REM reason could be read. From a console that is already open, no pause.
if not "%RC%"=="0" (echo %cmdcmdline% | find /i "%~nx0" >nul && pause)
endlocal & exit /b %RC%
