@echo off
REM One-time setup on a fresh machine. Uses the SYSTEM python: this is the
REM step that CREATES the virtualenv, so it cannot use one.
cd /d "%~dp0"
where python >nul 2>&1 || (echo Python 3.12+ is required and was not found on PATH. & exit /b 1)
python "%~dp0tools\setup.py" %*
