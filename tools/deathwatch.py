"""Watch the running API and record exactly how it dies.

The desk has died silently many times: no traceback in var/api.out, no
Windows Error Reporting entry, no shutdown line - the log simply stops
mid-request and the tunnel starts answering 502. Every theory that could be
tested from the outside has been ruled out (no git or Claude hooks, no
enabled scheduled task, no Defender action, the managed Python runtime
untouched since June), so the remaining evidence has to be caught at the
moment it happens.

This attaches to the process that is ALREADY running and changes nothing
about how it runs. It only observes, then writes what it saw:

    exit code   the single most diagnostic fact. On Windows:
                  0            clean exit - something asked it to stop
                  1            Python raised (expect a traceback too)
                  0xC000013A   CTRL_C / CTRL_BREAK / console close
                  0x40010004   DBG_TERMINATE_PROCESS (an external kill)
                  0xC0000005   access violation (a native crash)
                  0xFFFFFFFF   TerminateProcess with -1
    context     the last heartbeat before death, so a memory climb or a
                machine going idle is visible rather than inferred
    aftermath   the tail of api.out and every System/Application event in
                the three minutes around it

Run it detached and leave it running:

    .venv\\Scripts\\python tools\\deathwatch.py &

It exits once it has recorded a death, so the log holds one clean incident
rather than a stream. Findings land in var/logs/deathwatch.log.
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "var" / "logs" / "deathwatch.log"
API_OUT = ROOT / "var" / "api.out"
HEARTBEAT_S = 30

# Windows NTSTATUS / exit codes worth naming, so the log reads as a finding
# rather than as a number someone still has to look up.
KNOWN_CODES = {
    0: "clean exit - something asked it to stop",
    1: "Python raised an exception (expect a traceback in api.out)",
    2: "Python could not start (bad argument / import error)",
    -1: "TerminateProcess(-1) - killed by another program",
    3221225786: "0xC000013A CTRL_C / CTRL_BREAK / console close",
    1073807364: "0x40010004 DBG_TERMINATE_PROCESS - an external kill",
    3221225477: "0xC0000005 access violation - a native crash",
    3221225725: "0xC0000409 stack buffer overrun",
    3221225495: "0xC0000017 out of memory",
}


def say(msg: str) -> None:
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8", errors="replace") as fh:
        fh.write(line + "\n")


def find_api() -> list:
    """Every python process serving this project, real interpreter first.

    The venv's python.exe here is a REDIRECTOR stub, not a copy: it holds no
    socket and burns no CPU, while the real interpreter under
    AppData/Local/Python does the serving. Both have to be watched, because
    which one dies first is itself the finding.
    """
    import psutil

    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info["cmdline"] or [])
            if "uvicorn" in cmd and "app.main:app" in cmd and str(ROOT) in cmd:
                out.append(p)
        except psutil.Error:
            continue
    # the one holding the listening socket is the real server
    def is_server(proc):
        try:
            return any(c.status == "LISTEN" for c in proc.net_connections(kind="inet"))
        except psutil.Error:
            return False
    out.sort(key=is_server, reverse=True)
    return out


def snapshot(procs) -> dict:
    import psutil

    rows = {}
    for p in procs:
        try:
            rows[p.pid] = {
                "rss_mb": round(p.memory_info().rss / 1e6, 1),
                "threads": p.num_threads(),
                "cpu_s": round(sum(p.cpu_times()[:2]), 1),
                "conns": len(p.net_connections(kind="inet")),
            }
        except psutil.Error:
            rows[p.pid] = {"gone": True}
    vm = psutil.virtual_memory()
    return {
        "procs": rows,
        "sys_mem_pct": vm.percent,
        "sys_avail_mb": round(vm.available / 1e6),
        "boot_age_h": round((time.time() - psutil.boot_time()) / 3600, 1),
    }


def aftermath(pid: int, code) -> None:
    say("")
    say("=" * 66)
    name = KNOWN_CODES.get(code, "unrecognised - look it up as an NTSTATUS")
    say(f"DEATH  pid {pid}  exit code {code}  ({name})")
    say("=" * 66)

    say("--- last 25 lines of var/api.out ---")
    try:
        for line in API_OUT.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]:
            say(f"    {line}")
    except OSError as exc:
        say(f"    (unreadable: {exc})")

    say("--- Windows events, the 5 minutes around it ---")
    ps = (
        "$e=(Get-Date).AddMinutes(-4); $l=(Get-Date).AddMinutes(1); "
        "Get-WinEvent -FilterHashtable @{LogName='System','Application'; "
        "StartTime=$e; EndTime=$l} -ErrorAction SilentlyContinue | "
        "Where-Object { $_.LevelDisplayName -in 'Error','Warning','Critical' -or "
        "$_.ProviderName -match 'Kernel-Power|Kernel-General|Power-Troubleshooter|"
        "Application Error|Windows Error Reporting|Defender|Restart' } | "
        "Select-Object -First 15 | ForEach-Object { "
        "'{0:HH:mm:ss} [{1}] {2} {3}' -f $_.TimeCreated, $_.LevelDisplayName, "
        "$_.ProviderName, ($_.Message -replace \"`r`n\",' ').Substring(0,"
        "[Math]::Min(160,$_.Message.Length)) }"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, timeout=120)
        for line in (r.stdout or "(none)").splitlines():
            if line.strip():
                say(f"    {line.strip()}")
    except Exception as exc:  # noqa: BLE001 - diagnostics must never raise
        say(f"    (event log query failed: {exc})")


def main() -> int:
    try:
        import psutil  # noqa: F401
    except ImportError:
        print("psutil is required")
        return 2

    procs = find_api()
    if not procs:
        say("no API process found - start it first")
        return 2

    pids = [p.pid for p in procs]
    say("")
    say(f"deathwatch armed on {pids} (server first) - heartbeat every {HEARTBEAT_S}s")
    say(f"  {json.dumps(snapshot(procs))}")

    last = None
    while True:
        for p in list(procs):
            if not p.is_running():
                code = None
                try:
                    code = p.wait(timeout=0)
                except Exception:  # noqa: BLE001
                    pass
                if last:
                    say(f"last heartbeat before death: {json.dumps(last)}")
                aftermath(p.pid, code)
                say("deathwatch done - one incident recorded")
                return 0
        last = snapshot(procs)
        time.sleep(HEARTBEAT_S)


if __name__ == "__main__":
    raise SystemExit(main())
