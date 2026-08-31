@echo off
REM Start the desk (detached) and publish it at https://vidura36.app
REM
REM   start.bat              API + built desk + the public tunnel
REM   start.bat --no-tunnel  keep it local on 127.0.0.1:8791 only
REM   start.bat --dev        also run the Vite dev server on 5199 (hot reload)
REM
REM The tunnel is ON by default: this project has a NAMED Cloudflare tunnel on
REM its own domain, so publishing is how it normally runs. It used to be an
REM opt-in flag, which meant this script brought the desk up with no public
REM address while still reporting success.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo No .venv here yet - run setup.bat first. & exit /b 1)
".venv\Scripts\python.exe" "%~dp0tools\appctl.py" start %*
