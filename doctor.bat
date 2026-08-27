@echo off
REM Prove this copy is self-contained: paths, sources, data, desk.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "%~dp0tools\doctor.py" %*
) else (
  python "%~dp0tools\doctor.py" %*
)
