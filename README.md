# Vidura 36

A standalone trading station — backend, web UI, signal engines, the Kalshi
bot scripts and the credentials, all inside this one folder. Copy the folder
to any machine with Python 3.12+ and Node 18+, run `setup`, and it works.
Nothing outside `vidura-36-app/` is read at runtime.

Prove that at any time:

```bash
.venv\Scripts\python tools\check_self_contained.py
```

It ships **three worlds**, one process, one port:

| world | route | what it is |
| --- | --- | --- |
| Tradier Platform | `/tradier-platform` | the options executor, boards and charts |
| 36 Trade Desk | `/36-trade-desk` | the same desk, laid out for a phone |
| Bot Station | `/bot-station` | mission control for the Kalshi bots |

Three worlds, **two domains**. Tradier Platform and 36 Trades share one
backend: they call the same endpoints with the same parameters, and the only
differences are presentation. Bot Station is a genuine boundary — a different
venue, different instruments, and subprocess execution nothing else has.

---

## Quick start

```bash
setup.bat
```

```bash
start.bat
```

Open <http://127.0.0.1:8791/>.

The desk and the API are the same origin, so nothing has to be configured to
point one at the other.

### First run on a fresh machine

The database starts empty and **nobody can sign in until an operator exists**.
Creating the first one is a one-time call that refuses to run again once any
operator is present:

```bash
.venv\Scripts\python -c "import sys; sys.path.insert(0,'backend'); from app.tenancy import bootstrap; print(bootstrap.create_first_admin(slug='you', password='pick-a-real-one'))"
```

Then add that operator's venue keys through the API — no files, no restart:

```bash
curl -X POST http://127.0.0.1:8791/api/v1/tenants/<id>/credentials ^
  -H "X-API-Key: <your session token>" -H "Content-Type: application/json" ^
  -d "{\"venue\":\"tradier_sandbox\",\"secret\":{\"token\":\"...\",\"account_id\":\"...\"}}"
```

---

## Try it — the demo operator

| | |
| --- | --- |
| username | `demo` |
| password | `BankF@t1M` |

Sign in at <http://127.0.0.1:8791/> and all three worlds open with mock data
already on the boards: four positions (one venue-protected, one
monitored-only, one closed at target, one stopped out), eight bot trades
across four families — three of them deliberately *unclassified*, so the
ledger shows the real "belongs to neither LIVE nor PAPER" behaviour rather
than a tidied-up version — and a wellness profile.

Recreate or reset it at any time:

```bash
.venv\Scripts\python tools\seed_demo.py
```

### Why publishing this password is safe

**The demo operator has no venue credentials.** Not empty ones — none at all.
So it cannot reach Tradier or Kalshi even if the server is taken out of paper
mode, because there is nothing to authenticate with. It is also not an admin,
so it cannot create operators or list anyone's credentials.

What stops it seeing your data is not the password, it is tenant isolation.
Probed directly, with a position belonging to another operator:

| as demo | result |
| --- | --- |
| read another operator's position | `404` |
| read an id belonging to nobody | `404` — the same answer, so no oracle |
| close another operator's position | `404` |
| list positions | its own 4, never the other operator's |
| `GET /tenants` (admin surface) | `404` — hidden, not merely forbidden |
| reach a venue | `424` — no credential, cannot trade |

The demo account is the honest test of that claim rather than an exception
to it.

**One thing to be aware of:** the server binds `0.0.0.0` by default, so with
a published password anyone on your network can sign in as `demo`. That is
fine for what `demo` can do — nothing — but set `TBOT_V2_HOST=127.0.0.1` if
you would rather it were not reachable at all.

---

## Signing in

The desk asks for a password before it renders, and every `/api` call carries
the session token it returns in an `X-API-Key` header.

**The session decides which operator you are.** No request can name one:
there is no `user_id` parameter, no `?operator=` switch, and no way to ask
about another operator's data. Asking for a record that is not yours returns
*not found* rather than *forbidden*, because "forbidden" would confirm the
record exists.

Sessions live in memory. A restart signs everyone out, which is deliberate:
a desk that can place real orders should not sit unlocked on a machine nobody
is at. The cost is retyping a password after a deploy — see
[safe shutdown](#safe-shutdown) before you restart during market hours.

Two hours of no keyboard or pointer input also signs you out.

---

## Safety

This desk places real orders. The guarantees below are structural — they are
constraints and locks, not conventions somebody has to remember.

### A duplicate order cannot be expressed

Every money-moving request carries an idempotency key, written to the
database **before** the venue is called, under a uniqueness constraint. A
double-tap or a retry after a timeout returns the *first* order rather than
placing a second. A client that sends no key is still covered: the server
fingerprints the request and absorbs the repeat.

On top of that, before anything reaches the venue:

- a cross-process lease is taken on the contract, so two workers cannot both
  proceed (an in-process lock does not span workers, and two have run here);
- your own open positions are checked, and buying a contract you already hold
  is refused by name — pass `allow_add` to do it deliberately;
- the venue is asked whether a working order already exists, because our own
  records can be wrong;
- after placing, the venue is re-read: an unexpected second order is
  cancelled and the position flagged for review.

### Every stop-loss rests at the venue

A take-profit **and** a stop are placed as resting orders. If this process
dies, both survive. The previous build kept the stop as a threshold watched
by a Python loop — so a crash left live positions with an armed profit-taker
and no downside protection, silently.

Belt and braces on top of that:

- the in-process monitor still watches, and now runs its first pass
  immediately on startup rather than after a delay;
- if a venue refuses the stop leg, the position is marked
  `stop_protection: monitored_only` and says so — failing to rest a stop is
  acceptable, failing *quietly* is not;
- `/readiness` reports how long ago the risk monitor last completed a sweep,
  **per operator**, and new entries are refused while it is stale. Opening a
  position nobody is watching the stop for is worse than not trading.

### Refuse, never clamp

Every risk parameter is validated before the venue is touched, and an invalid
one is refused with the arithmetic that produced the refusal. Nothing is
silently adjusted into range: a clamped stop is a stop you did not choose and
would never be told about.

### Paper is the default

`TBOT_PAPER_ONLY=true` refuses live trading outright rather than downgrading
it silently. Sandbox is the default venue for every call that does not name
one, so reaching the real account is always a deliberate act.

---

## Customers

Each operator is a tenant with their own venue credentials. Adding one is
**three runtime writes** — no file, no migration, no deploy, no restart:

| | |
| --- | --- |
| `POST /api/v1/tenants` | the operator |
| `POST /api/v1/tenants/{id}/credentials` | their venue keys, encrypted |
| `PUT /api/v1/tenants/{id}/worlds` | which tiles they may open |

Credentials are sealed with **envelope encryption**: a per-record data key,
itself wrapped by a master key from the environment. Rotating the master key
re-wraps the small keys and never touches a secret, so a re-key cannot
corrupt one. Each ciphertext is bound to its owner, so a row copied into
another operator's record fails to decrypt rather than quietly working.

A credential is never returned by any endpoint — not masked, not partially.
You can see that one exists and when it changed, and nothing else.

Passwords are **hashed with Argon2id**, not encrypted. A venue key has to be
reversible because the system presents it to a broker; a password only needs
comparing, so hashing keeps the master key out of its blast radius entirely.

---

## The Bot Station

`/bot-station` is mission control for the **Kalshi** bots. Seven families,
sixteen selectable engines, every script vendored under
`runtime/prediction-trade/kalshi/`:

| bot | cadence | versions (default first) | signal source |
| --- | --- | --- | --- |
| `btc15` | 15m | **v2**, v3, v4, v5 | own engine |
| `btc60` | 60m | **fable5**, burst | own engine |
| `sports` | live match | **main**, v1, v2 | own engine |
| `parley` | live match | **v1** | own engine |
| `gold15` | 15m | **v2**, v1 | GLD via Tradier |
| `silver15` | 15m | **v2**, v1 | SLV via Tradier |
| `oil15` | 15m | **v2**, v1 | USO via Tradier |

Each is launched as a **subprocess**, not imported: they are long-lived
scripts with their own event loops, and one crashing must not take the API
with it.

### Every field is editable

Per launch, individually or for several bots at once:

| group | fields |
| --- | --- |
| Per trade | take-profit %, stop-loss %, contracts |
| Bankroll | bankroll, halt on bankroll gain %, halt on bankroll loss % |
| Schedule | trade from, trade until, blackout windows (CST) |

Take-profit and stop-loss are **per model**, not per bot: btc15 v2 and v5 are
different engines with different risk profiles, so one number would be wrong
for at least one of them. Values resolve in four layers — bot default, model
default, shared options, per-bot override.

`POST /api/v1/bots/launch` starts several at once from one place. An unknown
bot refuses the whole batch before anything starts; a failure after that
point does not abandon the rest, and the response says exactly which started.
There is no rollback for an order already placed, so an honest partial beats
a pretend all-or-nothing.

### Guards on every launch

- **One running instance per (operator, bot).** Two bots on one account
  corrupted a live ledger once.
- `HALT_MACHINE_SHUTDOWN=FALSE` — a bot halt may never power off the host.
- Risk is **per bot**, never account-wide. The Kalshi account is shared, so a
  floor on its joint value let one bot's drawdown stop the others.
- The subprocess environment is built from an **allowlist**, so it cannot
  inherit credentials from the API process. A denylist is only as good as its
  last update, and the failure there is one operator's bot signing with
  another operator's key.

### Commodity signals

Inside **08:30–15:00 CST, Monday to Friday**, gold, silver and oil read their
DMI from Tradier bars on the ETF that tracks each underlying, at 1m / 2m / 5m.
Kalshi publishes no price series to compute an indicator from, so the ETF
stands in — and it goes through the *same* indicator the desk uses, so the
board and the bot agree about what the market is doing.

Tradier serves 1min, 5min and 15min natively; 2min is folded from 1min bars,
grouped by clock time so a gap in the feed cannot silently shift the buckets.

Outside that window those ETFs are shut, so the futures engine answers
instead — and **every row says which source produced it**. A gold signal at
7pm from futures is not the same number as one from a closed ETF.

### Adding a bot

One config entry and one adapter class. It needs no endpoint, no migration,
no shared-library edit and no change to any dispatch switch — the eight
operations are keyed by bot, and the launch form renders itself from the
bot's own declared options. A test proves this by onboarding a throwaway bot
and asserting no shared module was touched.

---

## Configuration

Every setting is a `TBOT_`-prefixed environment variable, or a line in the
project-root `.env`. See `.env.example` for the full list with dummy values.

The ones that matter most:

| variable | what it does |
| --- | --- |
| `TBOT_PAPER_ONLY` | `true` refuses live trading outright. Default `true`. |
| `TBOT_ENCRYPTION_MASTER_KEY` | **required** once customers exist — see below |
| `TBOT_DATABASE_URL_OVERRIDE` | full SQLAlchemy URL; empty uses `var/app.db` |
| `TBOT_V2_PORT` / `TBOT_V2_HOST` | where the app listens |

### The master key

Generate one per environment and never reuse it across environments:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**If this key is lost, every stored customer credential is unrecoverable.**
There is no recovery path and deliberately no backdoor. Back it up where you
back up nothing else. Startup fails loudly rather than defaulting it, because
a generated key would silently make every existing credential unreadable.

---

## Database and migrations

SQLite, with the schema managed by Alembic:

```bash
.venv\Scripts\alembic upgrade head
```

The app runs this itself on startup and **refuses to serve** if the schema is
not current — an application on a half-migrated database answers, and the
answers are wrong.

`tools/import_profile.py` profiles what would migrate from an older install;
`tools/import_dry_run.py` imports into a throwaway database and reconciles by
reading the result back, touching nothing real.

---

## Tests

```bash
.venv\Scripts\python -m pytest tests/rebuild -q
```

| suite | what it protects |
| --- | --- |
| `test_tenant_isolation.py` | two operators with look-alike data; every read and write path; a guard that fails when a new endpoint has no isolation test |
| `test_contract.py` | the frozen API surface, and that **no endpoint anywhere can accept a tenant selector** |
| `test_execution_safety.py` | the seven guards, including a concurrent burst of six buys yielding one position |
| `test_onboarding.py` | a throwaway bot and a runtime-created customer, performed rather than asserted |
| `test_sensitive_data.py` | credentials absent from responses, logs, errors and `repr` |
| `test_stop_loss_durability.py` | both exit legs resting; one filling cancels the other |
| `test_migration.py` | migrate from empty, rollback, no model drift, one head |

---

## Safe shutdown

Before stopping the app or deploying:

1. **Check for open positions.** A restart is a financial event, not just an
   availability one, if anything is open and only monitored.
   ```bash
   .venv\Scripts\python -c "import sqlite3;print(sqlite3.connect('var/app-v2.db').execute(\"select id,occ_symbol,status,stop_protection from position where status in ('pending','open')\").fetchall())"
   ```
2. **Check for bot subprocesses.** They are detached, so stopping the API
   does not stop them.
   ```powershell
   Get-CimInstance Win32_Process -Filter "Name like '%python%'" | Where-Object { $_.CommandLine -like '*prediction-trade*' }
   ```
3. Positions whose `stop_protection` is `venue_resting` are safe — the venue
   holds both legs. Anything `monitored_only` loses its stop when the process
   stops.
4. Bots do **not** auto-resume on startup. Restarting them is explicit.

---

## Layout

```
backend/app/
  api_v2/          the HTTP edge: routers, and the ONE place a tenant is resolved
  domains/
    trading/       market data, execution, risk  (Tradier)
    botstation/    registry, lifecycle, ledger   (Kalshi)
  tenancy/         operators, credentials, world access
  platform/        db, security, migrations — no domain knowledge
  core/            settings
backend/migrations/  Alembic
frontend/src/      the three worlds
runtime/           vendored signal engines and bot scripts
customers/<name>/  per-operator credentials (gitignored, never committed)
var/               database, logs, backups (gitignored)
docs/rebuild/      the design record for this rebuild
```

Dependency direction is enforced: `api → domains → tenancy → platform`, and
the two domains may never import each other.

---

## Staying self-contained

```bash
.venv\Scripts\python tools\check_self_contained.py
```

It resolves every configured path, every bot script, and the working
directory and pinned paths for **every operator × bot × version** launch
combination, then scans every source file and comment for a path naming
another location on this machine. Exit code 0 means nothing in this project
points outside it.
