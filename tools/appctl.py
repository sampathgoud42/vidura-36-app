"""Start, stop and inspect Vidura — one control surface, both OSes.

start.bat/start.sh and stop.bat/stop.sh in the project root are thin wrappers
around this; they are the only launchers the root carries. Everything real
happens here on purpose: the previous Windows launcher shelled out to
PowerShell + CIM to find its own process, which has no Linux twin and could
not be tested from the same place. This module does the same job with the
standard library, so every command behaves identically wherever the folder is
copied.

    python tools/appctl.py start      # everything: deps, web app, API, tunnel,
                                      # and the edge's copy of the web app
    python tools/appctl.py start --restart   # stop, then start
    python tools/appctl.py start --no-tunnel # keep it on this machine
    python tools/appctl.py start --dev       # + Vite dev server on 5199
    python tools/appctl.py start --foreground
    python tools/appctl.py stop
    python tools/appctl.py status
    python tools/appctl.py url        # just the public URL

Processes are tracked by a pid file per service under var/. A pid file is
never trusted on its own: the pid is verified to still be alive AND to still
be this project's process before anything is signalled, so a recycled pid
belonging to something unrelated can never be killed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
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
# after the desk had been switched over, so `start` started a server the
# tunnel was not pointing at and `status` reported the running desk as
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
# readiness: what `start` brings up to date before the API starts
# --------------------------------------------------------------------------
# Each step compares timestamps and does nothing when nothing changed, so an
# ordinary start costs a few stat() calls. After a pull that moved a
# dependency or the web app's source, the same `start` is what catches up --
# which is the difference between "start" and "start whatever happens to be on
# disk".

FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist-v2"

# Marks the last time requirements.txt was installed into THIS virtualenv. It
# lives inside .venv so a rebuilt environment starts without one.
REQUIREMENTS_STAMP = ROOT / ".venv" / ".requirements.stamp"

# What a build is made from. Anything here newer than the build means the web
# app the API is serving is not the one in the source tree.
BUILD_INPUTS = (FRONTEND / "src", FRONTEND / "public", FRONTEND / "index.html",
                FRONTEND / "package.json", FRONTEND / "package-lock.json",
                FRONTEND / "vite.config.js", FRONTEND / "tailwind.config.js",
                FRONTEND / "postcss.config.js")


def _newest(paths) -> float:
    newest = 0.0
    for p in paths:
        if p.is_file():
            newest = max(newest, p.stat().st_mtime)
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    newest = max(newest, f.stat().st_mtime)
    return newest


def _npm() -> str | None:
    from shutil import which

    return which("npm.cmd" if IS_WINDOWS else "npm") or which("npm")


def ensure_python_deps() -> str:
    """pip install, if requirements.txt changed since it was last installed.

    Never an upgrade: a requirement that is already satisfied is left alone,
    so this is a no-op against a running API rather than files swapped out
    from under it. Returns 'current', 'installed' or 'failed'.
    """
    req = ROOT / "requirements.txt"
    if REQUIREMENTS_STAMP.is_file() and \
            REQUIREMENTS_STAMP.stat().st_mtime >= req.stat().st_mtime:
        return "current"
    # flush: the child writes straight to the same output, and a buffered
    # line would otherwise land after everything the child printed
    print("Python   installing dependencies (requirements.txt changed)...", flush=True)
    rc = subprocess.call([str(venv_python()), "-m", "pip", "install", "-r", str(req),
                          "-q", "--disable-pip-version-check"], cwd=str(ROOT))
    if rc != 0:
        print("Python   dependency install FAILED - see the output above")
        return "failed"
    REQUIREMENTS_STAMP.touch()
    return "installed"


def _ensure_node_deps(npm: str) -> bool:
    """npm install, if package-lock.json changed since node_modules was made.

    npm leaves its own record of an install in node_modules/.package-lock.json;
    it is touched after a successful run so an install that changed nothing
    is not repeated on every start.
    """
    lock = FRONTEND / "package-lock.json"
    marker = FRONTEND / "node_modules" / ".package-lock.json"
    if marker.is_file() and (not lock.is_file()
                             or marker.stat().st_mtime >= lock.stat().st_mtime):
        return True
    print("Web app  installing its dependencies (package-lock.json changed)...", flush=True)
    rc = subprocess.call([npm, "install", "--prefix", str(FRONTEND),
                          "--no-audit", "--no-fund"], cwd=str(ROOT))
    if rc != 0:
        print("Web app  dependency install FAILED - see the output above")
        return False
    if marker.is_file():
        os.utime(marker)
    return True


def ensure_web_app(dev: bool = False) -> None:
    """Build the web app into dist-v2, if the source is newer than the build.

    dist-v2 is gitignored, so a `git pull` brings new web-app source without a
    new build -- and the API would go on serving the old bundle while
    reporting a healthy start, a new world or panel simply absent from it.

    Never fatal. A failed build leaves the previous one in service -- vite
    writes nothing until the bundle compiles -- and with no build at all the
    API still runs, still trades and still answers /docs. Losing the UI must
    not cost the trading.

    `dev` (start --dev) skips a rebuild that would only be stale again at the
    next save: the dev server serves the source as it changes. A first build
    still runs, so the API has a web app at all.
    """
    index = DIST / "index.html"
    built_at = index.stat().st_mtime if index.is_file() else 0.0
    if built_at and _newest(BUILD_INPUTS) <= built_at:
        return
    if dev and built_at:
        print("Web app  --dev: not rebuilding - the dev server on 5199 serves the "
              "current source; the API on 8791 serves the last build")
        return
    npm = _npm()
    if npm is None:
        print("Web app  npm not found - "
              + ("serving the existing build" if built_at
                 else "no web app until Node 18+ is installed"))
        return
    if not _ensure_node_deps(npm):
        return
    print("Web app  building "
          + ("(its source is newer than the build)..." if built_at else "(first build)..."),
          flush=True)
    rc = subprocess.call([npm, "run", "build", "--prefix", str(FRONTEND)], cwd=str(ROOT))
    if rc != 0:
        print("Web app  build FAILED - "
              + ("the previous build stays in service" if built_at
                 else "the API runs with no web app"))
        return
    print("Web app  built into frontend/dist-v2")


# --------------------------------------------------------------------------
# the edge: vidura36.app's web app, served from Cloudflare (edge/, TUNNEL.md)
# --------------------------------------------------------------------------
# The first deploy is a deliberate act -- `npm --prefix edge run deploy`, after
# `npx wrangler login` in edge/ -- and it leaves a record of the build it
# published. From then on `start` keeps the edge on the current build: a build
# that only this machine served would leave vidura36.app loading yesterday's
# web app against today's API. `npm --prefix edge run delete` takes the Worker
# down and the record with it, and `start` leaves the edge alone after that.

EDGE = ROOT / "edge"
EDGE_RECORD = VAR / "edge.deployed"


def build_fingerprint() -> str | None:
    """sha256 over dist-v2: each file's relative path, then its bytes.

    edge/scripts/deployed.mjs computes the same thing for `npm run deploy`;
    the two have to agree byte for byte, so change them together.
    """
    if not (DIST / "index.html").is_file():
        return None
    h = hashlib.sha256()
    for rel, path in sorted((p.relative_to(DIST).as_posix(), p)
                            for p in DIST.rglob("*") if p.is_file()):
        h.update(rel.encode("utf-8") + b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def edge_record() -> str | None:
    """The build the edge was last given, or None if it was never deployed."""
    try:
        return json.loads(EDGE_RECORD.read_text(encoding="utf-8")).get("build") or None
    except (OSError, ValueError, AttributeError):
        return None


def _wrangler() -> Path | None:
    exe = EDGE / "node_modules" / ".bin" / ("wrangler.cmd" if IS_WINDOWS else "wrangler")
    return exe if exe.is_file() else None


def ensure_edge(args) -> None:
    """Put the current build on the edge, if the edge is in use and behind.

    Never fatal, and never interactive: the desk is up either way, and the
    edge keeps serving the build it has until a deploy succeeds.
    """
    wrangler = _wrangler()
    if wrangler is None:
        return                          # the edge's tooling is not on this machine
    last = edge_record()
    if last is None:
        print("Edge     not deployed - vidura36.app is served through the tunnel "
              "alone (first deploy: TUNNEL.md)")
        return
    current = build_fingerprint()
    if current is None:
        return
    if current == last:
        print("Edge     vidura36.app serves this build from Cloudflare's edge")
        return
    if args.dev or not args.tunnel:
        why = "--dev" if args.dev else "--no-tunnel"
        print(f"Edge     not updated ({why}) - vidura36.app still serves the previous build")
        return
    # Asked first: with no login, a deploy opens a browser to log in, which is
    # no part of starting a desk. whoami never prompts (and exits 0 either way).
    try:
        who = subprocess.run([str(wrangler), "whoami"], cwd=str(EDGE),
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", stdin=subprocess.DEVNULL, timeout=60)
        signed_in = "not authenticated" not in (who.stdout + who.stderr).lower()
    except (OSError, subprocess.TimeoutExpired):
        signed_in = False
    if not signed_in:
        print("Edge     not updated - Wrangler is not logged in here "
              "(npx wrangler login, in edge/); vidura36.app still serves the previous build")
        return
    print("Edge     publishing this build to vidura36.app...", flush=True)
    try:
        rc = subprocess.call([str(wrangler), "deploy", "--env="], cwd=str(EDGE),
                             stdin=subprocess.DEVNULL, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Edge     deploy could not run ({exc}) - vidura36.app still serves "
              "the previous build")
        return
    if rc != 0:
        print("Edge     deploy FAILED - vidura36.app still serves the previous build "
              "(see above)")
        return
    EDGE_RECORD.write_text(json.dumps({
        "build": current,
        "deployed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }) + "\n", encoding="utf-8")
    print("Edge     vidura36.app now serves this build")


# The signal desk: a separate project (vidura-super-signals) whose loopback
# service feeds Super Signals, the best pair and both signal strategies. This
# app never starts it -- it runs on its own task -- but a desk that comes up
# without it shows those panels offline, so start says so plainly.
SIGNALS_URL = os.environ.get("TBOT_SUPER_SIGNALS_URL", "http://127.0.0.1:8792")


def signals_answering() -> bool:
    url = SIGNALS_URL.rstrip("/") + "/api/session"
    try:
        # no proxy from the environment: the service is on loopback
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=3) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def report_signals() -> None:
    if signals_answering():
        print(f"Signals  the signal desk answers on {SIGNALS_URL}")
    else:
        print(f"Signals  the signal desk is NOT answering on {SIGNALS_URL} - Super "
              "Signals and the best pair\n         show offline until it runs "
              "(task Vidura_SignalAgents_API, project vidura-super-signals)")


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_start(args) -> int:
    py = venv_python()
    if not py.is_file():
        print(f"No virtualenv at {py}\nSet this copy up first:  "
              f"{'start.bat' if IS_WINDOWS else './start.sh'} does it on its first "
              f"run, or: python tools/setup.py")
        return 1

    # Dependencies and the web app first, so the API starts against what is
    # actually in the source tree, and serves the current web app from its
    # very first request.
    deps = ensure_python_deps()
    if deps == "failed":
        return 1
    ensure_web_app(dev=args.dev)

    if args.foreground:
        if running_pid("api"):
            print("The API is already running in the background. Stop it first.")
            return 1
        print(f"Vidura API on http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
        return subprocess.call(_api_cmd(args.port), cwd=str(ROOT), env=_api_env(args.port))

    pid = running_pid("api")
    if pid:
        print(f"API      already running (pid {pid}) on port {args.port}")
        if deps == "installed":
            print("         it loads the new dependencies on its next start:  "
                  f"{'start.bat' if IS_WINDOWS else './start.sh'} --restart")
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
            print("Desk     skipped - frontend/node_modules missing "
                  "(python tools/setup.py installs it)")
        else:
            npm = "npm.cmd" if IS_WINDOWS else "npm"
            dpid = _spawn("desk", [npm, "run", "dev", "--prefix", "frontend"],
                          dict(os.environ))
            print(f"Desk     pid {dpid}  http://127.0.0.1:{DESK_PORT} (dev, hot reload)")
    elif desk_built:
        print(f"Desk     http://127.0.0.1:{args.port}/   (served by the API)")
    else:
        print("Desk     no web app build - the API runs without one "
              "(install Node 18+, then start again)")

    report_signals()

    if args.tunnel:
        _start_tunnel(args.port)

    # Last, so the edge only ever gets a build whose API is already up.
    ensure_edge(args)

    print(f"Docs     http://127.0.0.1:{args.port}/docs")

    public = tunnel_url() if args.tunnel and running_pid("tunnel") else None
    stop = "stop.bat" if IS_WINDOWS else "./stop.sh"
    print()
    print(f"Vidura is up{'' if public else ' on this machine only'}.")
    if public:
        print(f"  anywhere      {public}")
    print(f"  this machine  http://127.0.0.1:{args.port}/")
    print(f"  stop it       {stop}")
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

    # Deliberately not "everything": a bot is a separate process with
    # positions of its own, and stopping the desk must never be the same act
    # as abandoning them (see _terminate). Say so, so nobody assumes otherwise.
    print("Bots     left running - a bot holds its own positions; stop it "
          "from the Bot Station")
    # Not this machine's to stop: the web app stays up on Cloudflare, and its
    # sign-in says the desk is offline until the next start.
    if edge_record():
        print("Edge     still serves the web app at vidura36.app; its sign-in says "
              "the desk is offline")
    return 0


def cmd_status(args) -> int:
    print(f"project  {ROOT}")
    venv = venv_python()
    print(f"venv     {'ok' if venv.is_file() else 'MISSING - the first start sets it up'}")

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

    if _wrangler() is not None:
        last = edge_record()
        if last is None:
            print("Edge     not deployed - vidura36.app is served through the tunnel alone")
        elif last == build_fingerprint():
            print("Edge     serving this build at vidura36.app")
        else:
            print("Edge     serving an older build - the next start publishes this one")
    print(f"Signals  {'answering' if signals_answering() else 'NOT answering'} "
          f"on {SIGNALS_URL}")
    return 0


def cmd_url(args) -> int:
    """Print just the public URL, nothing else.

    Quick-tunnel hostnames are random and change on every restart, so the
    one thing that choice costs is having to look the current one up. This
    makes that a single command whose output can be piped or copied without
    picking it out of a status block.
    """
    if running_pid("tunnel") is None:
        print(f"no tunnel running - start it with:  "
              f"{'start.bat' if IS_WINDOWS else './start.sh'}", file=sys.stderr)
        return 1
    url = tunnel_url()
    if not url:
        print(f"tunnel is running but published no URL yet - see "
              f"{log_file('tunnel')}", file=sys.stderr)
        return 1
    print(url)
    return 0


def cmd_restart(args) -> int:
    cmd_stop(args)
    time.sleep(1.0)
    return cmd_start(args)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Start, stop and inspect Vidura.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action",
                    choices=["start", "stop", "restart", "status", "url"])
    # `start --restart` rather than a restart launcher of its own: the root
    # carries start and stop, and a restart is the one of those done twice.
    ap.add_argument("--restart", action="store_true",
                    help="with start: stop everything first, then start it again")
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
    if args.action == "start" and args.restart:
        return cmd_restart(args)
    return {"start": cmd_start, "stop": cmd_stop, "restart": cmd_restart,
            "status": cmd_status, "url": cmd_url}[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
