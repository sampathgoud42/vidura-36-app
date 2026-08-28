@echo off
REM Stop the Tradier Bot. Only ever signals processes started from THIS
REM folder, so an unrelated app on the machine is never touched.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo No .venv here yet - nothing to stop. & exit /b 0)
".venv\Scripts\python.exe" "%~dp0tools\appctl.py" stop %*
