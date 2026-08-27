@echo off
REM Print the desk's current public tunnel URL, and nothing else.
REM Quick-tunnel hostnames are random and change on every restart.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo No .venv here yet - run setup.bat first. & exit /b 1)
".venv\Scripts\python.exe" "%~dp0tools\appctl.py" url %*
