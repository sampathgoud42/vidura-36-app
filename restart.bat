@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo No .venv here yet - run setup.bat first. & exit /b 1)
".venv\Scripts\python.exe" "%~dp0tools\appctl.py" restart %*
