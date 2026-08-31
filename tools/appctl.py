"""Start, stop and inspect the Tradier Bot — one control surface, both OSes.

The .bat and .sh files in the project root are two-line wrappers around this.
Everything real happens here on purpose: the previous Windows launcher shelled
out to PowerShell + CIM to find its own process, which has no Linux twin and
could not be tested from the same place. This module does the same job with
the standard library, so `start`/`stop`/`status` behave identically wherever
the folder is copied.

    python tools/appctl.py start      # API (serves the built desk) detached
    python tools/appctl.py start --dev    # + Vite dev server on 5199
    python tools/appctl.py start --foreground
    python tools/appctl.py stop
    python tools/appctl.py status
    python tools/appctl.py restart
    python tools/appctl.py url        # just the public tunnel URL
    python tools/appctl.py launch     # start + tunnel, URL in a banner

Processes are tracked by a pid file per service under var/. A pid file is
never trusted on its own: the pid is verified to still be alive AND to still
be this project's process before anything is signalled, so a recycled pid
belonging to something unrelated can never be killed.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAR = ROOT / "var"
IS_WINDOWS = os.name == "nt"

def _load_dotenv() -> None:
    """Fold the project .env into this process's environment.

    The app itself reads .env through pydantic-settings, which never touches
    os.environ — so a launcher that only looked at os.environ would silently
    ignore TBOT_PORT there and start the server on a different port from the
    one .env configured. An already-exported variable still wins, so a
    one-off `set TBOT_PORT=...` overrides the file.

    Hand-parsed rather than using python-dotenv: this module has to work
    under a bare interpreter (before the venv exists) as well as inside it.
    """
    env_file = ROOT / ".env"
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv()

# 8791 and api_v2. The control scripts pointed at the old app on 8790 long
# after the desk had been switched over, so `start.bat` started a server the
# tunnel was not pointing at and `status.bat` reported the running desk as
# "stopped (port is in use by something else)".
API_PORT = int(os.environ.get("TBOT_PORT", "8791"))
DESK_PORT = int(os.environ.get("TBOT_DESK_PORT", "5199"))

# A Windows console defaults to cp1252, and a redirected stdout raises there
# rather than mangling. Paths printed below can contain anything.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # pragma: no cover
    pass


def venv_python() -> Path:
    return ROOT / (".venv/Scripts/python.exe" if IS_WINDOWS else ".venv/bin/python")


# --------------------------------------------------------------------------
# cloudflare tunnel
# --------------------------------------------------------------------------

# Where the public URL is remembered between commands, so `status` can print
# it without re-reading a log that rotates.
URL_FILE = VAR / "tunnel.url"

# The tunnel definition lives with the project, not in the operator's home
# directory. See named_tunnel() for why.
TUNNEL_DIR = ROOT / "runtime" / "tunnel"
TUNNEL_CONFIG = TUNNEL_DIR / "config.yml"

CLOUDFLARED_CANDIDATES = [
    Path(r"C:/Program Files (x86)/cloudflared/cloudflared.exe"),
    Path(r"C:/Program Files/cloudflared/cloudflared.exe"),
    Path("/usr/local/bin/cloudflared"),
    Path("/usr/bin/cloudflared"),
]


def cloudflared() -> Path | None:
    from shutil import which

    found = which("cloudflared")
    if found:
        return Path(found)
    for c in CLOUDFLARED_CANDIDATES:
        if c.is_file():
            return c
    return None


def named_tunnel() -> str | None:
    """The configured named tunnel, if the operator set one up.

    A quick tunnel is handed a RANDOM hostname that changes every restart,
    which is fine for a demo and useless for a bookmark. A named tunnel
    (cloudflared tunnel login && ... route dns) keeps one hostname forever.
    Set TBOT_TUNNEL_NAME, or leave a config.yml where cloudflared expects
    it, and this uses that instead.
    """
    name = os.environ.get("TBOT_TUNNEL_NAME", "").strip()
    if name:
        return name
    # The PROJECT's config first. Everything this app needs lives in one
    # folder, and a tunnel definition in %USERPROFILE% is a reference outside
    # it: invisible to anyone reading the repo, left behind when the project
    # is copied, and still there after it is deleted. The home location stays
    # as a fallback so an existing setup keeps working.
    for cfg in (TUNNEL_CONFIG, Path.home() / ".cloudflared" / "config.yml"):
        if not cfg.is_file():
            continue
        try:
            for line in cfg.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("tunnel:"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return None


def tunnel_hostname() -> str | None:
    """The hostname a named tunnel publishes, from the project config.

    A named tunnel never prints its hostname the way a quick tunnel does --
    it does not need to discover one -- so scraping the log for it finds
    nothing. The ingress rules already say what it is.
    """
    if not TUNNEL_CONFIG.is_file():
        return None
    try:
        for line in TUNNEL_CONFIG.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("- hostname:"):
                host = stripped.split(":", 1)[1].strip()
                if host:
                    return f"https://{host}"
    except OSError:
        pass
    return None


def tunnel_url(wait_s: float = 0) -> str | None:
    """The public URL, scraped from cloudflared's own output.

    Quick tunnels only announce their hostname in the log, so there is
    nothing else to read it from. A named tunnel already knows its
    hostname, so that is recorded at start instead of parsed.
    """
    import re

    # A named tunnel knows its hostname up front; only a quick tunnel has to
    # be told what it was given.
    host = tunnel_hostname()
    if host:
        return host

    deadline = time.time() + wait_s
    pattern = re.compile(r"https://[a-z0-9][a-z0-9.-]*\.trycloudflare\.com")
    while True:
        try:
            text = log_file("tunnel").read_text(encoding="utf-8", errors="replace")
            hits = pattern.findall(text)
            if hits:
                url = hits[-1]
                URL_FILE.write_text(url, encoding="utf-8")
                return url
        except OSError:
            pass
        if time.time() >= deadline:
            break
        time.sleep(0.5)
    try:
        return URL_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def pid_file(service: str) -> Path:
    return VAR / f"{service}.pid"


def log_file(service: str) -> Path:
    return VAR / f"{service}.out"


# --------------------------------------------------------------------------
# process identity
# --------------------------------------------------------------------------

def _cmdline(pid: int) -> str:
    """Best-effort command line of *pid*, '' when it cannot be read.

    Used to confirm a pid still belongs to THIS project before signalling
    it. psutil is a dependency of the app, but this must also work in a
    bare interpreter during setup, so its absence is not fatal.
    """
    try:
        import psutil

        return " ".join(psutil.Process(pid).cmdline())
    except Exception:
        return ""


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WINDOWS:
        # No signal 0 on Windows: ask the process table instead.
        try:
            import psutil

            return psutil.pid_exists(pid)
        except Exception:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True,
            ).stdout
            return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError) as exc:
        return isinstance(exc, PermissionError)  # exists, not ours to signal


def owner_file(service: str) -> Path:
    return VAR / f"{service}.owner"


def running_pid(service: str) -> int | None:
    """The live pid for *service*, or None. Clears a stale pid file.

    A pid alone is not proof: the OS recycles them, and killing whatever
    inherited one is exactly the kind of surprise this project should not
    spring. So each spawn records a marker string that must still appear in
    the process\'s command line.

    The marker is per-service because they do not look alike. The API and
    the dev server run out of this folder, so their own paths identify
    them. cloudflared runs from Program Files and mentions this project
    nowhere -- for that one the marker is what it was pointed AT (the local
    URL, or the named tunnel), which is what makes it our tunnel rather
    than some other app\'s.
    """
    pf = pid_file(service)
    try:
        pid = int(pf.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if not _alive(pid):
        pf.unlink(missing_ok=True)
        owner_file(service).unlink(missing_ok=True)
        return None

    try:
        marker = owner_file(service).read_text(encoding="utf-8").strip()
    except OSError:
        marker = str(ROOT)            # pid file from before markers existed

    cmd = _cmdline(pid)
    # An unreadable command line is not proof of anything, so it is accepted;
    # a readable one without the marker means the pid was reused.
    if cmd and marker and marker.replace("/", os.sep) not in cmd.replace("/", os.sep):
        pf.unlink(missing_ok=True)
        owner_file(service).unlink(missing_ok=True)
        return None
    return pid


def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def pids_listening_on(port: int) -> list[int]:
    """Whoever is actually holding the port.

    The API launcher is not the process that listens -- it starts a child
    which does, so the pid in var/api.pid is one step removed from the socket.
    Stopping the launcher alone therefore leaves the port held, which is why
    `stop` began reporting "port is still in use" and the next `start` came up
    beside a server nobody was tracking.

    Found by port rather than by walking the process tree, because the tree
    also contains the BOTS, and those must survive a server restart. The
    holder of the API port is the API by definition; a bot never listens on
    it.
    """
    if not IS_WINDOWS:
        out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                             capture_output=True, text=True).stdout
        return [int(x) for x in out.split() if x.strip().isdigit()]
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                         capture_output=True, text=True).stdout
    found: list[int] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[3].upper() != "LISTENING":
            continue
        local = parts[1]
        if local.rsplit(":", 1)[-1] != str(port):
            continue
        if parts[4].isdigit():
            pid = int(parts[4])
            if pid > 0 and pid not in found:
                found.append(pid)
    return found


# --------------------------------------------------------------------------
# spawning
# --------------------------------------------------------------------------

def _spawn(service: str, cmd: list[str], env: dict[str, str],
           marker: str = "") -> int:
    """Launch detached, with output appended to var/<service>.out.

    *marker* is the substring that later proves a pid is still this
    process; it defaults to the project root, which suits anything launched
    from inside the folder. See running_pid.
    """
    VAR.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {}
    if IS_WINDOWS:
        # Detached + new process group: the server outlives the shell that
        # started it, and Ctrl-C in that shell does not take it down.
        kwargs["creationflags"] = 0x00000008 | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    with open(log_file(service), "a", encoding="utf-8", errors="replace") as out:
        out.write(f"\n=== {service} started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        out.flush()

        def _go(extra: int = 0):
            flags = dict(kwargs)
            if extra:
                flags["creationflags"] = flags["creationflags"] | extra
            return subprocess.Popen(
                cmd, cwd=str(ROOT), env=env, stdout=out,
                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                close_fds=True, **flags,
            )

        # The console flags above are only half of "outlives the shell". A
        # process also inherits its creator's JOB OBJECT, and a job that kills
        # on close takes every member with it however detached they are --
        # which is how the desk kept going down on its own when the window
        # that started it was closed or recycled. Breakaway is the only flag
        # that leaves the job, and a job may refuse it, so it is attempted and
        # dropped rather than assumed. _spawn_detached in lifecycle.py does
        # the same for bots.
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        if IS_WINDOWS:
            try:
                proc = _go(CREATE_BREAKAWAY_FROM_JOB)
            except OSError:
                proc = _go()
        else:
            proc = _go()
    pid_file(service).write_text(str(proc.pid), encoding="utf-8")
    owner_file(service).write_text(marker or str(ROOT), encoding="utf-8")
    return proc.pid


def _api_env(port: int) -> dict[str, str]:
    env = dict(os.environ)
    # backend/ on the path so `app.api_v2.server` resolves; cwd is the project
    # root, which is where .env and every project-relative default live.
    env["PYTHONPATH"] = str(ROOT / "backend") + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("TBOT_V2_PORT", str(port))
    env.setdefault("TBOT_V2_HOST", os.environ.get("TBOT_HOST", "0.0.0.0"))
    env.setdefault("TBOT_DATABASE_URL_OVERRIDE", "sqlite:///./var/app-v2.db")
    return env


def _api_cmd(port: int) -> list[str]:
    """Start api_v2 through its own entry point rather than bare uvicorn.

    The entry point migrates the database and then REFUSES to serve if it is
    not at head, which is the property worth keeping: a server answering from
    a schema nobody migrated is how a deploy half-works. `uvicorn app.main:app`
    skipped all of that and started the retired application besides.
    """
    return [str(venv_python()), "-m", "app.api_v2.server"]


def wait_healthy(port: int, timeout: float = 45.0) -> dict | None:
    """Poll /health until the API answers. Returns its payload, or None."""
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(0.5)
    return None


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_start(args) -> int:
    py = venv_python()
    if not py.is_file():
        print(f"No virtualenv at {py}\nRun setup first:  "
              f"{'setup.bat' if IS_WINDOWS else './setup.sh'}")
        return 1

    if args.foreground:
        if running_pid("api"):
            print("The API is already running in the background. Stop it first.")
            return 1
        print(f"Tradier Bot API on http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
        return subprocess.call(_api_cmd(args.port), cwd=str(ROOT), env=_api_env(args.port))

    pid = running_pid("api")
    if pid:
        print(f"API already running (pid {pid}) on port {args.port}")
    elif port_busy(args.port):
        # Something else owns the port. Starting anyway would produce a
        # server that fails to bind but keeps running every background loop
        # — the exact failure the app warns about at startup.
        print(f"Port {args.port} is already in use by another process.\n"
              f"Stop it, or start on a different port:  TBOT_PORT=8792")
        return 1
    else:
        pid = _spawn("api", _api_cmd(args.port), _api_env(args.port))
        health = wait_healthy(args.port)
        if health is None:
            print(f"API did not come up within 45s - see {log_file('api')}")
            return 1
        mode = "LIVE TRADING" if not health.get("paper_only") else "paper only"
        print(f"API      pid {pid}  http://127.0.0.1:{args.port}   [{mode}]")

    desk_built = (ROOT / "frontend" / "dist-v2" / "index.html").is_file()
    if args.dev:
        dpid = running_pid("desk")
        if dpid:
            print(f"Desk     pid {dpid}  http://127.0.0.1:{DESK_PORT} (dev)")
        elif not (ROOT / "frontend" / "node_modules").is_dir():
            print("Desk     skipped - frontend/node_modules missing (run setup)")
        else:
            npm = "npm.cmd" if IS_WINDOWS else "npm"
            dpid = _spawn("desk", [npm, "run", "dev", "--prefix", "frontend"],
                          dict(os.environ))
            print(f"Desk     pid {dpid}  http://127.0.0.1:{DESK_PORT} (dev, hot reload)")
    elif desk_built:
        print(f"Desk     http://127.0.0.1:{args.port}/   (served by the API)")
    else:
        print("Desk     not built - run `npm run build` in frontend/, "
              "or start with --dev")

    if args.tunnel:
        _start_tunnel(args.port)

    print(f"Docs     http://127.0.0.1:{args.port}/docs")
    return 0


def _start_tunnel(port: int) -> None:
    """Publish the desk through Cloudflare, so it is reachable off-LAN."""
    exe = cloudflared()
    if exe is None:
        print("Tunnel   cloudflared not installed "
              "(winget install Cloudflare.cloudflared)")
        return

    pid = running_pid("tunnel")
    if pid:
        url = tunnel_url()
        print(f"Tunnel   pid {pid}  {url or '(url unknown - see var/tunnel.out)'}")
        return

    name = named_tunnel()
    env = dict(os.environ)
    if name:
        cmd = [str(exe), "tunnel", "--no-autoupdate"]
        if TUNNEL_CONFIG.is_file():
            # Explicit, so cloudflared cannot silently fall back to a config
            # in the home directory that says something different from the
            # one committed here.
            cmd += ["--config", str(TUNNEL_CONFIG)]
            cert = TUNNEL_DIR / "cert.pem"
            if cert.is_file():
                env["TUNNEL_ORIGIN_CERT"] = str(cert)
        cmd += ["run", name]
    else:
        # Quick tunnel: no account needed, but Cloudflare assigns a random
        # hostname that is gone the moment this process is.
        cmd = [str(exe), "tunnel", "--no-autoupdate",
               "--url", f"http://127.0.0.1:{port}"]

    # A stale log would let the previous run's hostname be scraped as if it
    # were this one's.
    log_file("tunnel").unlink(missing_ok=True)
    URL_FILE.unlink(missing_ok=True)

    # What identifies OUR cloudflared among any others on the machine.
    marker = name if name else f"http://127.0.0.1:{port}"
    pid = _spawn("tunnel", cmd, env, marker=marker)
    if name:
        host = tunnel_hostname()
        if host:
            URL_FILE.write_text(host, encoding="utf-8")
            print(f"Tunnel   pid {pid}  {host}  (named tunnel '{name}')")
        else:
            print(f"Tunnel   pid {pid}  named tunnel '{name}' (stable hostname)")
        return

    url = tunnel_url(wait_s=25)
    if url:
        print(f"Tunnel   pid {pid}  {url}")
        print("         ^ PUBLIC. Anyone with this link reaches your sign-in "
              "page.\n         Quick-tunnel URLs change on every restart; see "
              "TUNNEL.md for a stable one.")
    else:
        print(f"Tunnel   pid {pid}  started, but no URL yet - "
              f"see {log_file('tunnel')}")


def _terminate(pid: int, label: str, *, tree: bool = True) -> bool:
    """Ask the process to exit, then insist. True when it is gone.

    The graceful half only really exists on POSIX. A Windows process started
    DETACHED has no console, so there is nothing for CTRL_BREAK to be
    delivered through — it is attempted anyway (harmless, and it does work
    for a foreground start) and then taskkill finishes the job. That is the
    normal path on Windows, not a fault, so the short grace period keeps it
    from looking like one.

    ``tree`` decides whether the process's descendants go with it, and the
    API must be stopped with ``tree=False``. Bots are launched BY the API, so
    on Windows they are its children in the process table, and `taskkill /T`
    walks that table: stopping the app with /T reached past the API and
    killed every live bot — silently, since the bot rows still said running
    and the desk had already printed "stopped". Restarting the app is a
    routine act; flattening live positions is not, and one must never be the
    other. DETACHED_PROCESS does not prevent this. It detaches the console,
    not the parent link, which is the thing /T actually follows.

    Everything else keeps the tree. The dev desk is a node server that
    spawns its own workers, and those are strays the moment it exits.

    Being terminated abruptly is safe here: SQLite runs in WAL mode and
    recovers on the next open, and no exit state lives only in memory. What
    it does NOT do is close positions — see `stop` in DEPLOY.md.
    """
    graceful = not IS_WINDOWS
    try:
        if IS_WINDOWS:
            try:
                os.kill(pid, signal.CTRL_BREAK_EVENT)
            except (OSError, AttributeError, ValueError):
                pass
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        pass

    # POSIX gets a real chance to unwind; Windows gets a token one.
    for _ in range(30 if graceful else 8):
        if not _alive(pid):
            return True
        time.sleep(0.2)

    if graceful:
        print(f"  {label} ignored SIGTERM, killing pid {pid}")
    try:
        if IS_WINDOWS:
            cmd = ["taskkill", "/PID", str(pid), "/F"]
            if tree:
                cmd.insert(-1, "/T")
            subprocess.run(cmd, capture_output=True)
        else:
            # POSIX needs no equivalent guard: SIGKILL to a pid is just that
            # pid, and lifecycle gives each bot its own session anyway.
            os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    for _ in range(15):
        if not _alive(pid):
            return True
        time.sleep(0.2)
    return not _alive(pid)


def cmd_stop(args) -> int:
    stopped = 0
    for service, label in (("tunnel", "Tunnel"), ("desk", "Desk"), ("api", "API")):
        pid = running_pid(service)
        if pid is None:
            print(f"{label:8} not running")
            continue
        # The API is stopped alone; its children are the live bots.
        if _terminate(pid, label, tree=(service != "api")):
            pid_file(service).unlink(missing_ok=True)
            owner_file(service).unlink(missing_ok=True)
            print(f"{label:8} stopped (pid {pid})")
            stopped += 1
        else:
            print(f"{label:8} FAILED to stop (pid {pid})")
            return 1
    URL_FILE.unlink(missing_ok=True)

    # The launcher is gone; the process it started may still hold the socket.
    # Clear it explicitly rather than reporting it as somebody else's app --
    # it is ours, and leaving it running means the next start silently races
    # a server that is already there.
    if stopped and port_busy(args.port):
        for pid in pids_listening_on(args.port):
            if _terminate(pid, f"API:{pid}", tree=False):
                print(f"{'API':8} released port {args.port} (pid {pid})")
        if port_busy(args.port):
            print(f"note: port {args.port} is still in use - another app "
                  f"is on it")
    return 0


def cmd_status(args) -> int:
    print(f"project  {ROOT}")
    venv = venv_python()
    print(f"venv     {'ok' if venv.is_file() else 'MISSING - run setup'}")

    pid = running_pid("api")
    if pid:
        health = wait_healthy(args.port, timeout=3)
        if health:
            mode = "LIVE TRADING" if not health.get("paper_only") else "paper only"
            print(f"API      running (pid {pid})  port {args.port}  [{mode}]")
            # /health does not report a database path, so this printed
            # "database None" on every run. The path the server was actually
            # told to use is the honest answer.
            db_url = os.environ.get("TBOT_DATABASE_URL_OVERRIDE",
                                    "sqlite:///./var/app-v2.db")
            print(f"database {health.get('database') or db_url}")
        else:
            print(f"API      pid {pid} alive but /health is not answering "
                  f"on {args.port} - see {log_file('api')}")
    else:
        busy = " (port is in use by something else)" if port_busy(args.port) else ""
        print(f"API      stopped{busy}")

    dpid = running_pid("desk")
    print(f"Desk     {'running (pid %d) port %d' % (dpid, DESK_PORT) if dpid else 'not running as a dev server'}")
    tpid = running_pid("tunnel")
    if tpid:
        url = tunnel_url()
        print(f"Tunnel   running (pid {tpid})  {url or '(url unknown)'}")
        print("         PUBLIC - reachable from anywhere")
    else:
        print(f"Tunnel   not running"
              f"{'' if cloudflared() else ' (cloudflared not installed)'}")

    # dist-v2, which is what api_v2 actually serves. This reported on
    # frontend/dist -- the RETIRED app's build -- so it said "the API serves
    # it" about a directory the API does not look at, and would have said the
    # UI was fine with dist-v2 missing entirely.
    built = ROOT / "frontend" / "dist-v2" / "index.html"
    print(f"build    {'frontend/dist-v2 present - the API serves it' if built.is_file() else 'frontend/dist-v2 MISSING - no UI'}")
    return 0


def cmd_url(args) -> int:
    """Print just the public URL, nothing else.

    Quick-tunnel hostnames are random and change on every restart, so the
    one thing that choice costs is having to look the current one up. This
    makes that a single command whose output can be piped or copied without
    picking it out of a status block.
    """
    if running_pid("tunnel") is None:
        print("no tunnel running - start it with:  start.bat --tunnel",
              file=sys.stderr)
        return 1
    url = tunnel_url()
    if not url:
        print(f"tunnel is running but published no URL yet - see "
              f"{log_file('tunnel')}", file=sys.stderr)
        return 1
    print(url)
    return 0


def _to_clipboard(text: str) -> bool:
    """Best-effort copy. Never fails the launch over a missing utility."""
    tools = ([["clip"]] if IS_WINDOWS
             else [["pbcopy"], ["xclip", "-selection", "clipboard"], ["xsel", "-ib"]])
    for tool in tools:
        try:
            proc = subprocess.run(tool, input=text, text=True,
                                  capture_output=True, timeout=5)
            if proc.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def cmd_launch(args) -> int:
    """Bring the desk up on a public URL and show it, big.

    Same work as `start --tunnel`, presented for someone who double-clicked
    an icon rather than typed a command: the URL is the answer they came
    for, so it gets a frame of its own and lands on the clipboard. The
    wrapper keeps the window open afterwards.
    """
    rc = cmd_start(args)
    if rc != 0:
        return rc

    url = tunnel_url()
    print()
    if not url:
        print("  The desk is up locally, but the tunnel published no URL.")
        print(f"  Look at {log_file('tunnel')} for why.")
        print(f"  Locally it is on http://127.0.0.1:{args.port}/")
        return 1

    bar = "=" * (len(url) + 8)
    print(f"  {bar}")
    print(f"     {url}")
    print(f"  {bar}")
    print()
    print("  Open that from any device, anywhere. Sign in with your")
    print("  operator password.")
    print()
    if _to_clipboard(url):
        print("  (copied to your clipboard)")
    print()
    print("  This window can be closed - the desk keeps running.")
    print("  To take it down:   stop.bat")
    print("  To see it again:   url.bat")
    return 0


def cmd_restart(args) -> int:
    cmd_stop(args)
    time.sleep(1.0)
    return cmd_start(args)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Start/stop the Tradier Bot.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action",
                    choices=["start", "stop", "restart", "status", "url",
                             "launch"])
    ap.add_argument("--dev", action="store_true",
                    help="also run the Vite dev server (hot reload) on 5199")
    # The tunnel is ON by default. This project has a NAMED tunnel on its own
    # domain, so publishing is the normal way it runs, not an extra -- and an
    # opt-in flag meant `start.bat` quietly brought the desk up with no public
    # address while everything else reported success.
    #
    # --no-tunnel is the way to keep it local, and it is the flag that has to
    # be typed deliberately, because that is the choice worth being explicit
    # about on a desk that is meant to be reachable.
    ap.add_argument("--tunnel", action="store_true",
                    help="publish through Cloudflare (default; kept for scripts)")
    ap.add_argument("--no-tunnel", dest="no_tunnel", action="store_true",
                    help="keep the desk local — do NOT publish it")
    ap.add_argument("--foreground", action="store_true",
                    help="run the API in this terminal instead of detaching")
    ap.add_argument("--port", type=int, default=API_PORT,
                    help=f"API port (default {API_PORT}, or $TBOT_PORT)")
    args = ap.parse_args()
    # Resolved once, here, so every command sees the same answer.
    args.tunnel = not args.no_tunnel

    VAR.mkdir(parents=True, exist_ok=True)
    return {"start": cmd_start, "stop": cmd_stop, "restart": cmd_restart,
            "status": cmd_status, "url": cmd_url,
            "launch": cmd_launch}[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
