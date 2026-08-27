@echo off
REM Start the Tradier Bot (detached). Desk and API share port 8790.
REM   start.bat          API + built desk
REM   start.bat --dev    also run the Vite dev server on 5199 (hot reload)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo No .venv here yet - run setup.bat first. & exit /b 1)
".venv\Scripts\python.exe" "%~dp0tools\appctl.py" start %*
