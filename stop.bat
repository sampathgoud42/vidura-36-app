@echo off
REM Stop Vidura: the tunnel first, so vidura36.app never points at a desk that
REM is shutting down, then the dev server, then the API.
REM
REM Bots are NOT stopped: each is a separate process holding positions of its
REM own - stop them from the Bot Station. Take-profits rest at the venue and
REM keep working while the desk is down; the stop-loss monitor does not (see
REM DEPLOY.md, "What stopping does and does not do").
REM
REM Only ever signals processes started from THIS folder, so an unrelated app on
REM the machine is never touched.
setlocal
cd /d "%~dp0"
set "RC=0"

if not exist ".venv\Scripts\python.exe" (
  echo No .venv here yet - nothing to stop.
  goto :done
)
".venv\Scripts\python.exe" "%~dp0tools\appctl.py" stop %*
set "RC=%ERRORLEVEL%"

:done
REM Double-clicked from Explorer: keep the window open (see start.bat).
setlocal EnableDelayedExpansion
set "CL=!cmdcmdline:"=!"
if "!CL:~-1!"==" " pause
endlocal
endlocal & exit /b %RC%
