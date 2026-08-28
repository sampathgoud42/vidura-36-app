@echo off
REM Tradier Bot desk (Vite dev server) on http://127.0.0.1:5199
REM The API must be running too: ..\run.bat
cd /d "%~dp0"
if not exist "node_modules" (
  echo Installing frontend dependencies ...
  call npm install || exit /b 1
)
call npm run dev
