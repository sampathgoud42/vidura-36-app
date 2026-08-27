# Shipping Tradier Bot to a new PC

The whole app is one folder. Copying it *is* the deployment — there is no
installer, no database server, no separate frontend host, and nothing to
register. This document is the full procedure, plus what to check when
something does not come up.

**Time:** about 10 minutes, most of it `pip install`.

---

## What the target PC needs

| | version | required? |
| --- | --- | --- |
| Python | 3.12 or newer | **yes** |
| Node.js | 18 or newer | no — only to rebuild the UI |
| Internet | outbound HTTPS | yes, for Tradier, Kalshi and market data |

Node is optional because the desk ships **pre-built** in `frontend/dist`,
and the API serves it. You only need Node if you intend to change the UI.

On Windows, install Python from python.org and tick **"Add python.exe to
PATH"**. Verify before you start:

```bash
python --version
```

---

## Step 1 — Copy the folder

Copy the entire `tradier-bot` folder to the new PC. Any location works;
nothing inside it hardcodes a path.

**Do not copy these** (they are machine-specific and get rebuilt):

```
.venv/                  Python virtualenv — built for the old machine's OS
frontend/node_modules/  npm packages
var/*.pid  var/*.out    stale process ids and logs
**/__pycache__/
```

Everything else must come across. In particular:

| folder | why it must ship |
| --- | --- |
| `customers/` | the Tradier tokens and account ids — **without it nothing can trade** |
| `var/app.db` | users, position history, signal history |
| `runtime/` | the signal engines and the level watcher |
| `frontend/dist/` | the pre-built desk (skip only if the target has Node) |
| `.env` | this machine's overrides, including the live-trading unlock |

A clean, correctly-filtered copy on Windows:

```bash
robocopy D:\_projects\tradier-bot E:\tradier-bot /MIR /XD .venv node_modules __pycache__ .pytest_cache .git /XF *.pid
```

On Linux/macOS:

```bash
rsync -a --exclude .venv --exclude node_modules --exclude __pycache__ --exclude '*.pid' tradier-bot/ /opt/tradier-bot/
```

> `customers/` and `.env` are in `.gitignore`. If you ship via git rather
> than a file copy, they will **not** be in the clone — copy those two by
> hand, over a channel you would trust with a brokerage token.

---

## Step 2 — Run setup

From inside the copied folder:

```bash
setup.bat
```

On Linux/macOS: `./setup.sh`

This creates `.venv`, installs the Python dependencies, creates `.env` from
`.env.example` if you did not bring one, rebuilds the desk if Node is
present, and finishes by running the self-containment audit.

It is safe to re-run at any time.

---

## Step 3 — Check the audit

Setup runs this for you; run it again whenever you want:

```bash
doctor.bat
```

It verifies six things, in the order a new machine tends to fail them:

- **ENV** — Python version, virtualenv, every dependency importable
- **PATHS** — every resolved setting points **inside this folder**
- **SOURCE** — no file references an absolute path outside it
- **DATA** — engines, credentials and database are present and readable, and
  no user reads credentials from outside this copy
- **BOTS** — every Bot Station script resolves inside this copy, and each
  operator has the Kalshi key id + `*.pem` the bots authenticate with
- **LAUNCHERS** — the `.bat`/`.sh` pairs exist, with the line endings each OS
  needs (LF for `.sh`, CRLF for `.bat`)
- **DESK** — a built UI exists for the API to serve

Its stricter companion resolves every bot's actual launch plan — working
directory, credential folder, ledger paths — not just the settings:

```bash
.venv\Scripts\python tools\check_self_contained.py
```

Exit code 0 means this copy needs nothing outside its own folder. `[warn]`
lines never fail the run — they flag an optional piece (no Node, no
flashAlpha key, a credential folder with no Tradier keys) that the desk
degrades gracefully without.

A healthy result on a fresh machine:

```
PATHS
  [ ok ] database   var\app.db
  [ ok ] runtime    runtime
  [ ok ] customers  customers
  [ ok ] levels     runtime\stock-trade
  [ ok ] paper-only: every order goes to the Tradier sandbox
SOURCE
  [ ok ] no external absolute paths in 455 scanned files
BOTS
  [ ok ] 16 bot script(s) across 7 families, all vendored here
  [ ok ] customers/sampath: Kalshi key + private key
```

---

## Step 4 — Decide paper or live

**A fresh copy is paper-only.** `paper_only` defaults to true *in code*, so
every client is pinned to Tradier's sandbox — its own token, its own
account. A machine that is misconfigured in every other way still cannot
spend real money.

Live trading requires one deliberate line in `.env`:

```
TBOT_PAPER_ONLY=false
```

The audit and `start` both announce which mode you are in:

```
API      pid 11564  http://127.0.0.1:8790   [LIVE TRADING]
```

If you copied `.env` from a machine that had live unlocked, **the new PC is
live too**. Delete that line unless you meant it.

---

## Step 5 — Start it

```bash
start.bat
```

```
API      pid 11564  http://127.0.0.1:8790   [paper only]
Desk     http://127.0.0.1:8790/   (served by the API)
Docs     http://127.0.0.1:8790/docs
```

Open <http://127.0.0.1:8790/>. The desk and the API are the same port and
the same process — the page fetches `/api/v1` on its own origin, so there is
nothing to configure.

You will be asked to sign in. The operator is the username in the database
(`sampath` by default) and the password is that operator's
`customers/<username>/.sam`, which shipped with the copy — so if the folder
came across, the password came with it. Nothing to set up.

The sign-in screen states whether the machine is in paper or live mode
before you type. Read it.

| command | what it does |
| --- | --- |
| `start.bat` | start detached; survives closing the terminal |
| `start.bat --dev` | also run the Vite dev server on 5199 (hot reload, for UI work) |
| `stop.bat` | stop it |
| `restart.bat` | stop, then start |
| `status.bat` | what is running, which database, paper or live |
| `doctor.bat` | the audit |

`.sh` equivalents exist for Linux/macOS (`./start.sh`, …). Both are two-line
wrappers around `tools/appctl.py`, so behaviour is identical on either OS.

To run in the foreground with logs in the terminal:

```bash
.venv\Scripts\python tools\appctl.py start --foreground
```

---

## Step 6 — Confirm it actually works

Health, and which database it opened:

```bash
curl http://127.0.0.1:8790/health
```

Every other endpoint needs a session, so sign in first and keep the token:

```bash
curl -s -X POST http://127.0.0.1:8790/api/v1/auth/login -H "Content-Type: application/json" -d "{\"username\":\"sampath\",\"password\":\"YOUR_PASSWORD\"}"
```

Then, with the `token` from that response, check the users came across:

```bash
curl -H "X-API-Key: PASTE_TOKEN" http://127.0.0.1:8790/api/v1/users
```

And with a `user_id` from that list, the real proof — a live call to Tradier
using the shipped broker credentials:

```bash
curl -H "X-API-Key: PASTE_TOKEN" "http://127.0.0.1:8790/api/v1/tradier/venue?user_id=PASTE_USER_ID"
```

A response naming your sandbox and/or live account ids means the deployment
is complete for the Tradier side.

For the **Bot Station**, the proof is a bot that actually runs. This starts
each engine in paper, holds it alive, tails its log and stops it — no order
reaches the exchange:

```bash
.venv\Scripts\python tools\paper_smoke_bots.py --all-versions
```

`PASS: 16 bot/version launch(es) ran in paper` means the vendored scripts,
the Kalshi credentials and the process control all work on this machine. A
bot that dies on import shows as `EXITED EARLY` with the traceback in its
tail.

For scripts that run unattended, set `TBOT_API_KEY=<something-long>` in
`.env` and send that in `X-API-Key` instead — it needs no login and does not
expire.

---

## Ports

| port | what |
| --- | --- |
| 8790 | API **and** desk |
| 5199 | Vite dev server, only with `start --dev` |

Change the API port for one run — `cmd`:

```bash
set TBOT_PORT=8791
```

or PowerShell (note: PowerShell 5.1 has no `&&`, so run the two lines
separately):

```bash
$env:TBOT_PORT='8791'
```

then `start.bat`. Permanently, put `TBOT_PORT=8791` in `.env`.

`start` refuses to launch if the port is already taken rather than starting
a server that fails to bind but keeps running every background loop.

### Reaching it from another machine

The API binds `0.0.0.0`, so `http://<this-pc-ip>:8790/` works across the LAN
once the firewall allows it. The login gate already covers this: every
`/api` call needs a session, so a browser on the LAN gets the sign-in screen
rather than a working desk.

That gate is only as good as the `.sam` password behind it, so use a real
one before exposing the port. Note also that the traffic is plain HTTP —
fine on a home LAN, not fine across anything you do not control. For that,
put it behind a reverse proxy with TLS.

---

## Running it automatically

**Windows — start at logon.** Task Scheduler → Create Task:

- General → *Run whether user is logged on or not* is **not** needed; the
  desk is a UI, so "run only when logged on" is usually right
- Triggers → *At log on*
- Actions → Start a program → Program: `D:\tradier-bot\start.bat`,
  Start in: `D:\tradier-bot`

`start.bat` is idempotent — if it is already running, it says so and exits 0.

**Linux — systemd.** `/etc/systemd/system/tradier-bot.service`:

```ini
[Unit]
Description=Tradier Bot
After=network-online.target

[Service]
Type=exec
WorkingDirectory=/opt/tradier-bot
Environment=PYTHONPATH=/opt/tradier-bot/backend
ExecStart=/opt/tradier-bot/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8790
Restart=on-failure
User=tradier

[Install]
WantedBy=multi-user.target
```

Use `ExecStart` directly rather than `start.sh`: systemd wants to own the
process, and `start.sh` detaches.

---

## What stopping does and does not do

`stop` ends the API process. It does **not** close positions.

That is not a bug, but you have to know it:

- **Take-profits keep working.** A TP is a real resting sell order on
  Tradier. It survives the app being stopped, and the machine being off.
- **Stop-losses do not.** The SL is a 10-second monitor inside this process.
  While the app is stopped, nothing is watching it.

So an open position with the app stopped is "take-profit, or ride it". Close
your positions before a long shutdown, or accept that exposure knowingly.
On restart the monitor picks the positions back up from the database — which
is exactly why they are stored there rather than in memory.

---

## Moving an app that has already been running

Same copy, one thing worth understanding: `var/app.db` records each user's
credential folder as an absolute path, pointing at wherever the app was
first set up.

On every boot, the API repoints any user whose stored root is **outside this
project** at the matching folder under this copy's `customers/`:

```
app.migrate INFO user sampath: credential folder repointed
            D:/_projects/tradier-bot/customers/sampath -> ...\ship-test\customers\sampath
```

Note that it does this whether or not the old path still resolves. That
matters more than it sounds: run a copy on the same machine as the original
— which is exactly what testing a deployment looks like — and the old path
resolves perfectly while the copy quietly trades using the *original*
folder's tokens. `doctor` fails on that case specifically:

```
[FAIL] user 'sampath' reads credentials from OUTSIDE this project: D:/...
```

If no folder of that name exists in this copy, it logs a warning and leaves
the row alone rather than guessing. Copy the missing folder into
`customers/` and restart.

The one exception is `TBOT_ALLOW_ANY_ROOT=true`, which turns the migration
off entirely — that flag means you have taken responsibility for pointing
roots wherever you like.

---

## Troubleshooting

**`python` is not recognised** — Python is not on PATH. Re-run the installer
and tick "Add python.exe to PATH", or call it by full path.

**`start` says the port is in use** — something else owns 8790. `status`
distinguishes the two cases ("stopped (port is in use by something else)").
Use `TBOT_PORT=8791`, or stop the other app.

**The API does not come up within 45s** — read `var/api.out`. The most
common cause on a fresh machine is a dependency that failed to install; re-run
setup and watch for errors.

**The desk loads but every panel is empty** — the API is up (the page came
from it) but the calls are failing. Open the browser console. A 401 means
the session expired — reload and sign in again. A 404 on `/api/v1/...` means
the page was served by something other than the API — clear the saved base
with `?api=off`.

**Signed out for no apparent reason** — sessions are in memory, so any
restart of the API ends them. Expected after `restart.bat`, a reboot, or a
crash. Just sign in again.

**"Incorrect username or password" with the right password** — the operator
name must match a user in the database (`/api/v1/users` lists them, or check
`doctor`), and the password is that user's `customers/<name>/.sam`, not
their `.env`. If the folder did not ship, `doctor` says so.

**"Too many failed attempts"** — ten consecutive failures locks that
username for five minutes. Wait it out, or restart the API, which clears the
counters along with the sessions.

**Locked out entirely** — set `TBOT_LOGIN_REQUIRED=false` in `.env` and
restart to get in without a password, then fix the `.sam` and turn it back
on.

**"User ... not found" on every Tradier call** — the desk defaults to
operator `sampath`. If your database uses a different username, pick it with
`?operator=<name>` once; it is remembered.

**Tradier calls return 424** — the credential folder for that user has no
usable `.env`. `doctor` names the folder and what it is missing.

**A `.sh` script fails with `bad interpreter: /usr/bin/env sh^M`** — the
file picked up CRLF endings, usually by being edited on Windows or cloned
with `core.autocrlf=true`. `.gitattributes` pins this, but to repair a copy:

```bash
python tools/fix_line_endings.py
```

**HOT / options-flow boards are empty** — normal for the first few minutes.
Both are served from background sweeps; they answer instantly with whatever
snapshot exists and fill in once the first sweep lands.

**Level crosses show "watcher not running"** — the watcher is a separate
process; start it from the desk's LVL CROSS panel. Exactly one instance may
run per folder: it appends to that folder's `day_trade.csv` and dedupes
against its own `levels_state.json`, so a second one duplicates crossings.

**A bot refuses to start: "N process(es) already running outside this
API"** — a copy of that bot is alive that this API never launched (an orphan
from a previous instance, or a manual run). Two bots on one Kalshi account
corrupt the ledger, so the start is refused rather than doubled. Stop the
stray, or start with `kill_existing=true` to take it over deliberately.

**A bot exits immediately with "no .env in the current directory"** — that
operator's `customers/<name>/` has no `.env`, so the bot cannot find its
Kalshi key or PEM. `doctor` names it under **BOTS**.

**A bot starts but never trades** — check `mode`. In paper it prices against
the live book and simulates fills; that is working, not stuck. The log line
`DRY_RUN=True` / `PAPER TRADING MODE` says which it is.

---

## Verifying a shipped copy end to end

Run these on the new PC, in order. The audit must exit clean, `start` must
report a pid, and health must answer:

```bash
doctor.bat
```

```bash
start.bat
```

```bash
curl http://127.0.0.1:8790/health
```

Then prove the launch plans, which `doctor` only checks loosely:

```bash
.venv\Scripts\python tools\check_self_contained.py
```

For a deeper check, the test suite runs offline apart from one case:

```bash
.venv\Scripts\python -m pytest
```

356 pass, 51 xfail.
`test_gex0dte.py::test_refresh_without_a_payload_tries_the_vendor_and_reports_the_block`
asserts that getgamma.io blocks a server-side fetch; when the vendor answers
instead, it fails. It fails identically in the project this was extracted
from — a live-network assertion, not a problem with your copy. The xfails are
`test_sports_firesell.py`, explained in README.

Finally, the Bot Station — the one part pytest cannot cover, because a bot is
a subprocess authenticating against a live exchange:

```bash
.venv\Scripts\python tools\paper_smoke_bots.py --all-versions
```

Paper only: every launch forces the simulated side and no order reaches the
exchange. `PASS: 16 bot/version launch(es) ran in paper` completes the
deployment.
