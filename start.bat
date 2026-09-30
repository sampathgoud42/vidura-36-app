@echo off
REM Start Vidura - everything it needs, in order - and publish it at
REM https://vidura36.app
REM
REM   start.bat               set up a fresh copy, install what changed, build the
REM                           web app if it is out of date, start the API, and
REM                           open the tunnel
REM   start.bat --restart     stop everything first, then start it again
REM   start.bat --no-tunnel   keep it on this machine only (127.0.0.1:8791)
REM   start.bat --dev         also run the Vite dev server on 5199 (hot reload)
REM
REM stop.bat takes it all down. Status, the public URL and the audit are one
REM command each through tools\ - see README.md.
REM
REM Double-clicked from Explorer, the window stays open at the end so the result
REM can be read. From a console, PowerShell or a scheduled task it never waits.
setlocal
cd /d "%~dp0"
set "RC=0"

if exist ".venv\Scripts\python.exe" goto :run
echo.
echo   First start on this machine - setting Vidura up. This takes a few minutes.
echo.
where python >nul 2>&1
if errorlevel 1 (
  echo   Python 3.12+ is required and was not found on PATH.
  set "RC=1"
  goto :done
)
REM The system Python: this is the step that creates the virtualenv.
python "%~dp0tools\setup.py"
if errorlevel 1 (
  set "RC=1"
  goto :done
)

:run
".venv\Scripts\python.exe" "%~dp0tools\appctl.py" start %*
set "RC=%ERRORLEVEL%"

:done
REM Explorer runs a double-clicked script as  cmd /c ""...\start.bat" "  and that
REM is the only launch whose command line, quotes removed, ends in a space.
setlocal EnableDelayedExpansion
set "CL=!cmdcmdline:"=!"
if "!CL:~-1!"==" " pause
endlocal
endlocal & exit /b %RC%
