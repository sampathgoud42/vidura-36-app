# Tradier Bot

A standalone trading station — backend, web UI, signal engines, the Kalshi
bot scripts and the credentials, all inside this one folder. Copy the folder
to any machine with Python 3.12+ and Node 18+, run `setup`, and it works.
Nothing outside `tradier-bot/` is read at runtime.

It ships **three worlds**, all on one process and one port:

| world | route | what it is |
| --- | --- | --- |
| Tradier Platform | `/tradier-platform` | the options executor, boards and charts |
| 36 Trade Desk | `/36-trade-desk` | the same desk, laid out for a phone |
| Bot Station | `/bot-station` | mission control for the Kalshi bots |

It was extracted from the `vidura-world` (API) and `vidura-world-js` (SPA)
projects, where these were three of nine sites sharing a database, a
customers folder and a bot repo on another disk. Everything they touched
came with them — including every bot script the station launches, which now
live under `runtime/prediction-trade/`.

Prove that at any time:

```bash
.venv\Scripts\python tools\check_self_contained.py
```

---

## Quick start

```bash
setup.bat
```

```bash
start.bat
```

Open <http://127.0.0.1:8790/>. The desk and the API are the same port and
the same process — the API serves the built UI, so there is nothing to
configure and no second server to run. Swagger is at `/docs`.

| command | |
| --- | --- |
| `start.bat` | start detached |
| `start.bat --dev` | also run the Vite dev server on 5199 (hot reload, for UI work) |
| `stop.bat` | stop |
| `restart.bat` | stop, then start |
| `launch.bat` | start + Cloudflare tunnel, URL in a banner, window stays open |
| `start.bat --tunnel` | the same, for a terminal you are already in |
| `status.bat` | what is running, which database, paper or live, tunnel URL |
| `url.bat` | the current public tunnel URL, on its own (it changes each restart) |
| `doctor.bat` | prove this copy is self-contained |

`.sh` equivalents exist for Linux/macOS. Both are two-line wrappers around
`tools/appctl.py`, so start/stop behave identically on either OS.

To ship this to another machine, see **[DEPLOY.md](DEPLOY.md)**. To reach it
from outside your LAN, see **[TUNNEL.md](TUNNEL.md)**.

---

## What it does

**The executor.** You say "SPY call, 50% of the account, delta 0.25–0.50";
the service picks the contract off the chain, sizes it, buys, rests the
take-profit as a real order on the venue and monitors the stop-loss itself.
Many positions run side by side.

The TP/SL split matters: the take-profit is an order Tradier holds, so it
survives an API restart on its own. The stop-loss is a 10-second loop in
this process — `TBOT_TRADIER_MONITOR_INTERVAL_S` *is* the stop's reaction
time. Positions live in SQLite rather than memory for exactly that reason: a
restart with in-memory state would silently turn every open position into
"take-profit or ride to zero". When the stop fires it cancels the resting TP
before selling, so two sells can never stack.

**Two auto-traders**, both of which only ever hand work to the executor
above:

- `10min_intraday_move` — watches the SPY/QQQ/SPX opening-range level
  crosses produced by `runtime/stock-trade/levels_watcher.py`, requires the
  signal to still hold after a confirmation delay, and trades only inside
  the 08:30–09:30 CST window.
- `ab_signal_options` — takes A/B super-signals (LONG→call, SHORT→put) but
  does not buy on the signal. It samples the chosen contract's bid and buys
  only while that bid is holding up, never into a fade.

**Two boards.** A HOT scan ranking the top 100 names by Wilder DMI/ADX
trend strength, and an options-flow board surfacing unusual activity across
the large caps. Both are served from background sweeps, so a request returns
whatever snapshot exists rather than waiting on the venue.

**The signal engines** (`runtime/super_research/`) that feed the A/B
auto-trader, mirrored into SQLite continuously so the database is the
durable record.

---

## The Bot Station

`/bot-station` is mission control for the **Kalshi** bots — a different
venue and a different risk model from the Tradier desk, which is why it is
its own world rather than another panel.

Seven bot families, sixteen selectable engines, every script vendored under
`runtime/prediction-trade/kalshi/`:

| bot | cadence | versions (default first) |
| --- | --- | --- |
| `btc15` | 15m | **v2**, v3, v4, v5 |
| `btc60` | 60m | **fable5**, burst |
| `sports` | live match | **main**, v1, v2 |
| `parley` | live match | **v1** |
| `gold15` | 15m | **v2**, v1 |
| `silver15` | 15m | **v2**, v1 |
| `oil15` | 15m | **v2**, v1 |

Each one is launched as a **subprocess**, not imported: they are long-lived
scripts with their own event loops, and one bot crashing must not take the
API with it. `bot_manager` builds the argv, working directory and
environment per family — the btc15 engines resolve their `.env` and PEM from
the working directory, btc60 takes `BTC_CUSTOMERS_DIR`/`BTC_CUSTOMER`, and
the sports family takes the customer name as `argv[1]` — and pins every
output path into `customers/<user>/`, so two operators never collide on a
shared file.

Three guards are applied on every launch, whatever the request or the
operator's shell said:

- `HALT_MACHINE_SHUTDOWN=FALSE` — a bot halt may never power off the host.
- `DO_NOT_BUY_IF_PORTFOLIO_BELOW=0` and `TARGET_PORTFOLIO_PCT=0` — the
  Kalshi account is **shared** by every bot, so a floor or profit target on
  its joint value let one bot's drawdown silently stop the others. Risk is
  expressed per bot, as a bankroll plus a target on that bankroll.
- A start refuses outright if a copy of that bot is already running,
  including one this API never launched. Two bots on one account corrupted a
  live ledger once. Pass `kill_existing=true` to deliberately take over.

**Paper is the default and paper is enforced.** `mode="paper"` forces
`DRY_RUN_MODE` / `MAIN_PAPER` / `PARLEY_PAPER` / `BOTGOLD_DRY_RUN` /
`BOTSILVER_DRY_RUN` to the simulated side, and a paper run is refused if the
customer's own `.env` contradicts it. `mode="live"` is refused entirely
while the server is `paper_only`.

The station also carries the **trade ledger**: each bot writes CSVs into
`customers/<user>/trade_history/`, which are mirrored into SQLite on every
read (TTL-guarded), reconciled hourly against Kalshi fills and settlements
for rows the exchange has finished but the bot never closed, and shown as
the event log, the win record and the portfolio curve.

Smoke-test the whole thing without placing an order:

```bash
.venv\Scripts\python tools\paper_smoke_bots.py --all-versions
```

That starts each engine in paper, holds it alive, tails its log, stops it
and confirms nothing was left behind.

---

## Layout

```
tradier-bot/
├── backend/app/          FastAPI application
│   ├── api/v1/           auth, tradier, bots, kalshi, trades, super,
│   │                     levels, users, desk36, worlds
│   ├── core/             config, database, path safety
│   ├── models/           TradierPosition, BotRun, Trade, User, signals
│   └── services/         tradier_client, tradier_bot, auto_trade,
│                         hot_scan, options_flow, quotes, levels,
│                         super_research, gex, earnings, credentials,
│                         bot_manager, bot_launcher, bot_registry,
│                         kalshi_client, ingest, reconcile, trades
├── frontend/src/sites/   tradier/, desk36/, botstation/  (one per world)
├── runtime/
│   ├── super_research/   signal engines + per-ticker research folders
│   ├── NIFTY_research/   referenced by super_research.config (india)
│   ├── BANKNIFTY_research/
│   ├── stock-trade/      levels_watcher.py + its state and crossings CSV
│   ├── indicators/       commodity_dmi + the BTC signal helpers the bots
│   │                     and the station's live DMI readout import
│   └── prediction-trade/ every Kalshi bot script the station launches
│       ├── kalshi/btc/           btc15 + btc60 engines and their signal pkg
│       ├── kalshi/sports/        multi-sport + parlay bots, tracked config
│       ├── kalshi/commodities/   gold15, silver15, oil15
│       └── sports/               the tennis + baseball models they import
├── customers/<user>/     per-user credentials  ← SECRETS, gitignored
├── var/                  app.db + logs
├── tests/                pytest suite
└── tools/                setup, start/stop, doctor, the self-contained
                          audit and the paper smoke test
```

### Where the money lives

`customers/<username>/` holds one operator's credentials:

| file | contents |
| --- | --- |
| `.env` | `TRADIER_SANDBOX_*` and `TRADIER_PROD_*` (URI, token, account id), Kalshi keys |
| `.sam` | login password, plaintext, compared timing-safely |
| `*.pem` | Kalshi private key |

Sandbox and production are **separate key names on purpose** — the sandbox
is a different venue with its own token, so a paper session cannot reach the
live account by a flag being misread.

Credentials are parsed into a dict and never loaded into `os.environ`, so
one user's secrets cannot leak into another's subprocess.

`customers/` and `.env` are gitignored. Keep it that way.

---

## Signing in

The desk asks for a password before it renders, over the Vidura World hero.

The password is **not stored in this project**. It is the operator's own
`customers/<username>/.sam` — the single-line plaintext file the 38trades
apps have always used — compared timing-safely, with a fixed one-second
penalty on every failure and a five-minute lockout after ten. Adding an
operator is a filesystem operation, not a migration: drop a folder under
`customers/` with a `.sam` and the broker keys, register the user, done.
Nothing about the password ever enters the database.

Login gates the **API**, not just the screen. A successful sign-in returns a
session token that every `/api` call must carry in `X-API-Key`; without that
the login would be decorative, since the desk binds `0.0.0.0` and can place
real orders. Only `/health`, `/docs`, `/auth/status`, `/auth/login` and the
static UI are reachable without one.

Sessions live in memory, so **a restart signs everyone out**. That is the
intended trade: a machine left running overnight cannot be walked up to and
used. They otherwise last 12 hours (`TBOT_SESSION_TTL_S`).

For scripts and cron, which cannot type a password, set `TBOT_API_KEY` and
send that in the same header instead. To turn the gate off entirely on a
throwaway localhost session, `TBOT_LOGIN_REQUIRED=false`.

```bash
curl -s -X POST http://127.0.0.1:8790/api/v1/auth/login -H "Content-Type: application/json" -d "{\"username\":\"sampath\",\"password\":\"...\"}"
```

## The 0DTE gamma feed

SPY 0DTE dealer gamma comes from getgamma.io, whose option chain the server
cannot fetch — the vendor blocks it. So the data is **pushed in** by a
bookmarklet running on the dashboard tab, where the session is already
authenticated. The server never calls getgamma; that is the design, not a
workaround.

```bash
python tools\make_bookmarklet.py
```

That reads `tools/gex0dte_bookmarklet.js`, injects this machine's port and
push token, and writes a one-line `javascript:` URL to
`var/gex0dte_bookmarklet.txt`. Save it as a bookmark, open the getgamma
dashboard, click once to start (it pushes immediately, then every five
minutes) and again to stop.

It authenticates with **`TBOT_GEX_PUSH_TOKEN`** — not the login, and not
`TBOT_API_KEY`. That token opens exactly two paths,
`POST /super/gex0dte/refresh` and `/heartbeat`, and nothing else. It runs on
a third-party page belonging to a desk that can place real orders, so the
worst case for a leaked push token is poisoned gamma data rather than a
trade. Rotate it by changing the line in `.env`, restarting, and rebuilding.

## Safety

`paper_only` defaults to **true in code**, which pins every client to
Tradier's sandbox. A fresh copy of this folder therefore cannot place a real
order, no matter what else is misconfigured. The sign-in screen states which
mode it is in before you type anything.

This machine's `.env` carries `TBOT_PAPER_ONLY=false` — the deliberate live
unlock carried over from the workstation this was extracted from. Delete
that line to go back to paper.

If the API is reachable beyond localhost, set `TBOT_API_KEY` and every
`/api` request must carry it in the `X-API-Key` header.

---

## Configuration

Every field in `backend/app/core/config.py` maps to an environment variable
named `TBOT_<FIELD_NAME>`; `.env` in this folder is read at startup. See
`.env.example` for the ones worth knowing about.

**Every default path points inside this folder** — that is the property that
makes the project relocatable, so prefer moving the folder over overriding
paths.

Legacy `VIDURA_*` names are still accepted, so a machine that already ran
the original app keeps working without edits.

### Relocating

Just move or copy the folder; there is nothing to edit. `user_root_folder`
is stored per user as an absolute path, and on every boot a user whose
folder no longer resolves is repointed at the matching folder under this
project's `customers/`. If no folder of that name exists locally the row is
left alone and a warning is logged — a wrong path you can see beats a
silently reassigned credential folder.

### Ports

8790 serves both the API and the desk. 5199 is the Vite dev server, and only
exists under `start --dev`; it is 5199 rather than Vite's usual 5173 so this
can run alongside the project it came from.

`start` refuses to launch when the port is already taken, rather than
producing a server that fails to bind but keeps running every background
loop. `stop` only ever signals processes launched from this folder — it
verifies each recorded pid is still alive *and* still this project's
process, so a recycled pid or an unrelated `uvicorn app.main:app` elsewhere
on the machine is never touched.

---

## Tests

```bash
.venv\Scripts\python -m pytest
```

356 pass, 51 xfail. One is expected to fail:
`test_gex0dte.py::test_refresh_without_a_payload_tries_the_vendor_and_reports_the_block`
asserts that getgamma.io blocks a server-side fetch; when the vendor
answers instead, it fails. It fails identically in the project this was
extracted from — it is a live-network assertion, not a defect here.

The 51 xfails are all `test_sports_firesell.py`. It guards an unconditional
6c/98c exit band that the vendored sports bots no longer define — the same
51 cases fail in the project this came from. The file is kept as the record
of the rule; delete the `pytestmark` at the top the moment the band is put
back and it starts guarding again.

Bots are not covered by pytest — a subprocess that authenticates against a
live exchange is not a unit test. They have their own paper smoke test:

```bash
.venv\Scripts\python tools\paper_smoke_bots.py --all-versions
```

---

## Staying self-contained

The extraction is **finished**. This folder is now the source of truth: the
`extract_*` / `vendor_*` scripts that pulled code from `vidura-world`,
`vidura-world-js` and the old bot repo have been retired, because a re-sync
would now delete the Bot Station rather than update it. Fix things here.

What replaces them is an audit that proves the property those scripts
existed to establish:

```bash
.venv\Scripts\python tools\check_self_contained.py
```

It checks three things and fails on any of them:

1. **Settings** — database, customers, runtime, levels, super, var and log
   directories all resolve inside this folder.
2. **Launch plans** — for every user × bot × version, the working directory
   and every path the subprocess is handed (`*_CSV`, `*_DIR`, `*_LOG_PATH`,
   `*_SECRETS`) land inside this folder. A script being vendored is not
   enough; a bot handed an outside credential folder is still coupled.
3. **Sources** — no file, comment or doc names another checkout on this
   machine.

Portable illustrations (`/home/app/data/app.db`, `C:\Users\you\...`) are
deliberately not flagged: they document what an override looks like on some
other host and resolve to nothing here. Add `no-outside-ref-ok` to a line
that genuinely has to name an outside path.

Run it after any change that touches paths, and alongside:

```bash
doctor.bat
```
