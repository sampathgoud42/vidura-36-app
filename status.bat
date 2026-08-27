@echo off
REM What is running, where the data lives, and whether this copy is live.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo No .venv here yet - run setup.bat first. & exit /b 1)
".venv\Scripts\python.exe" "%~dp0tools\appctl.py" status %*
