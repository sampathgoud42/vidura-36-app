<#
watchdog_btc60_fable5.ps1 - crash-recovery watchdog for bot_kalshi_btc60_fable5.py

Runs as its own detached process (NOT tied to any Claude Code session or
terminal window). Every WATCHDOG_INTERVAL_S, checks whether a python.exe
process running bot_kalshi_btc60_fable5.py is alive; if not, relaunches it
from this same directory so it picks up .env / kalshi_private.pem the same
way a manual launch would.

This does NOT restart the bot for performance reasons (losing streaks are
handled in-process by Learner._fast_check() - see the bot's own docstring).
It only recovers from crashes / unhandled exceptions, so "don't wait for me"
is covered for the failure mode that actually needs a process restart.

Start (detached, survives this terminal closing):
    Start-Process powershell -ArgumentList `
        "-NoProfile","-ExecutionPolicy","Bypass","-File","watchdog_btc60_fable5.ps1" `
        -WorkingDirectory $PSScriptRoot -WindowStyle Hidden

Stop: kill the powershell.exe process running this script (see
watchdog_btc60_fable5.log for its own PID at startup), or delete this file's
running instance via Task Manager - it does not manage its own lifecycle
beyond restarting the bot.
#>

$ErrorActionPreference = "SilentlyContinue"
$dir = $PSScriptRoot
Set-Location $dir

$LogFile = Join-Path $dir "watchdog_btc60_fable5.log"
$IntervalS = 30

function Write-Log($msg) {
    $line = "$(Get-Date -Format o)  $msg"
    Add-Content -Path $LogFile -Value $line
}

Write-Log "[WATCHDOG] started (PID $PID), watching bot_kalshi_btc60_fable5.py in $dir, interval ${IntervalS}s"

while ($true) {
    $proc = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*bot_kalshi_btc60_fable5.py*" }

    if (-not $proc) {
        Write-Log "[WATCHDOG] bot not running - relaunching"
        $p = Start-Process python -ArgumentList "bot_kalshi_btc60_fable5.py" `
            -WorkingDirectory $dir -WindowStyle Hidden -PassThru
        Start-Sleep -Seconds 5
        $alive = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
        if ($alive) {
            Write-Log "[WATCHDOG] relaunched OK (PID $($p.Id))"
        } else {
            Write-Log "[WATCHDOG] relaunch FAILED - will retry next cycle"
        }
    }

    Start-Sleep -Seconds $IntervalS
}
