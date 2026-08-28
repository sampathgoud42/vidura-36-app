"""Register (or remove) an auto-start entry for the desk + tunnel.

    python tools/autostart.py install     # start at logon
    python tools/autostart.py remove
    python tools/autostart.py status

Windows: a Scheduled Task that runs `start.bat --tunnel` at logon.
Linux/macOS: prints the systemd unit or launchd plist to install, rather
than writing into a system directory behind your back.

Deliberately opt-in and never run by setup: this starts a desk that can
place real orders and publishes it to the internet. That should be a
decision someone made on purpose, on the day they made it.

`start` is idempotent, so a task that fires when the desk is already up
just reports it and exits 0.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = os.name == "nt"
TASK_NAME = "TradierBotDesk"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # pragma: no cover
    pass


def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True)


def win_install(tunnel: bool) -> int:
    start = ROOT / "start.bat"
    if not start.is_file():
        print(f"missing {start}")
        return 1
    # /RL LIMITED, not HIGHEST: nothing here needs admin, and a task that
    # runs elevated is a bigger thing to have firing automatically.
    cmd = f'"{start}"' + (" --tunnel" if tunnel else "")
    r = _schtasks("/Create", "/TN", TASK_NAME, "/TR", cmd,
                  "/SC", "ONLOGON", "/RL", "LIMITED", "/F")
    if r.returncode != 0:
        print("failed to register the task:")
        print((r.stderr or r.stdout).strip())
        return r.returncode
    print(f"registered scheduled task '{TASK_NAME}'")
    print(f"  runs at logon: {cmd}")
    print(f"  working dir  : {ROOT}")
    if tunnel:
        print("  the tunnel starts with it - the desk will be PUBLIC from boot")
    print(f"\nremove with:  python tools/autostart.py remove")
    return 0


def win_remove() -> int:
    r = _schtasks("/Delete", "/TN", TASK_NAME, "/F")
    if r.returncode != 0:
        print((r.stderr or r.stdout).strip() or "no such task")
        return 0
    print(f"removed scheduled task '{TASK_NAME}'")
    return 0


def win_status() -> int:
    r = _schtasks("/Query", "/TN", TASK_NAME, "/FO", "LIST")
    if r.returncode != 0:
        print(f"auto-start is NOT registered (no task '{TASK_NAME}')")
        return 0
    for line in r.stdout.splitlines():
        if line.split(":")[0].strip() in ("TaskName", "Status", "Task To Run",
                                          "Next Run Time", "Last Run Time"):
            print("  " + line.strip())
    return 0


SYSTEMD = """[Unit]
Description=Tradier Bot desk
After=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory={root}
ExecStart={root}/start.sh{tunnel}
ExecStop={root}/stop.sh
User={user}

[Install]
WantedBy=multi-user.target
"""


def posix_install(tunnel: bool) -> int:
    print("Install this as a user service, then enable it:\n")
    print(f"  # ~/.config/systemd/user/tradier-bot.service")
    print(SYSTEMD.format(root=ROOT, user=os.environ.get("USER", "youruser"),
                         tunnel=" --tunnel" if tunnel else ""))
    print("  systemctl --user daemon-reload")
    print("  systemctl --user enable --now tradier-bot")
    print("  loginctl enable-linger $USER   # so it runs without you logged in")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["install", "remove", "status"])
    ap.add_argument("--no-tunnel", action="store_true",
                    help="start the desk at logon but NOT the public tunnel")
    args = ap.parse_args()
    tunnel = not args.no_tunnel

    if not IS_WINDOWS:
        if args.action == "install":
            return posix_install(tunnel)
        print("On this OS, manage it with systemctl --user "
              "{status,disable} tradier-bot")
        return 0

    return {"install": lambda: win_install(tunnel),
            "remove": win_remove,
            "status": win_status}[args.action]()


if __name__ == "__main__":
    sys.exit(main())
