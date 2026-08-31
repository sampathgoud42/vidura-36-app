@echo off
REM Launch the desk on a public Cloudflare URL, show it, and KEEP THIS
REM WINDOW OPEN so the address stays on screen.
REM
REM Safe to double-click from Explorer: the desk and the tunnel are started
REM detached, so closing this window afterwards leaves them running.
setlocal
cd /d "%~dp0"
title Tradier Bot - launching...

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   No .venv here yet. Run setup.bat first.
  echo.
  pause
  exit /b 1
)

echo.
".venv\Scripts\python.exe" "%~dp0tools\appctl.py" launch
set RC=%ERRORLEVEL%
title Tradier Bot - running

echo.
if not "%RC%"=="0" (
  echo   Launch reported a problem ^(exit %RC%^). See var\api.out and var\tunnel.out.
  echo.
)
pause
endlocal
