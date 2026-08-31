# Running the full trading stack on Cloud Run

This is the deployment that keeps trading enabled in the cloud. It is not the
default the app ships with, and the differences matter — read *Why this is
delicate* before the first live deploy.

Firebase **App Hosting cannot run this.** App Hosting builds Next.js and
Angular; this backend is Python/FastAPI. The container goes to **Cloud Run**,
and Firebase Hosting optionally sits in front of it for the CDN and a nicer
domain (`firebase.json` is already wired for that).

---

## Why this is delicate

The app ships with a **cloud profile** that deliberately disables trading.
`get_settings()` turns `cloud_mode` on automatically whenever `PORT` is set,
which Cloud Run always does. In that mode every execution endpoint answers
503 — buy, close, sweep, move-TP, auto-trade, the market stream and the
desk36 DMI board — and the background TP/SL monitor never starts.

That guard exists for real reasons. This deployment turns it off with
`TBOT_CLOUD_MODE=false`, which means **you** now have to satisfy what it was
protecting:

**1. Exactly one monitor may run.**
`_tradier_loop` watches open positions and fires stop-losses. Two copies means
two resting sells on one holding — a short position waiting to happen, which
is what `test_a_second_monitor_pass_does_not_stack_another_sell` exists to
prevent and what the app warns about at startup. So:

- Cloud Run is pinned `--min-instances=1 --max-instances=1`. Do not raise
  max-instances. Autoscaling this service is not a performance win, it is a
  second trader.
- **Stop the local instance** before the cloud one starts trading:
  `python tools/appctl.py stop`. A laptop still running `appctl` is a second
  monitor on the same Tradier account, and neither one knows about the other.

**2. The database cannot be ephemeral.**
Cloud Run's filesystem is wiped on every restart and redeploy. Position state
lives in the database; losing it while positions are open leaves **live
Tradier positions that nothing is managing a stop-loss for**, and no record
that they exist. That is why this runs on Postgres, not SQLite.

**3. CPU must not be throttled.**
Cloud Run throttles CPU between requests by default. The monitor loop runs
*between* requests. `--no-cpu-throttling` (always-allocated CPU) is required,
and it is what makes this cost money continuously — roughly a small always-on
instance, billed 24/7, plus Cloud SQL.

**4. The Bot Station does not run here — and `TBOT_CLOUD_MODE=false` does
not change that.**
Turning cloud mode off re-enables the Tradier executor, which is a loop
inside this process. The Bot Station is different in kind: it launches
Kalshi bots as **separate long-lived processes** that hold locks, keep
in-memory session state and write ledgers to disk. A Cloud Run container is
recycled without warning and its filesystem is wiped, so a bot there would
be killed mid-position with its ledger gone.

So leave `/bots/*/start`, `/stop`, `/kill` and `/reconcile` refused (`503`,
from `require_local_runtime`). The station itself still **renders** in the
cloud and still shows the ledger, the win record, the portfolio curve and
every past run — those are database reads and they keep working. Run the
bots on a machine you control, pointed at the same Postgres, and the cloud
desk will show what they did.

---

## One time: project, database, secrets

Requires the **Blaze** plan and `gcloud`
(https://cloud.google.com/sdk/docs/install).

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  secretmanager.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

### Postgres

```bash
gcloud sql instances create tradier-db \
  --database-version=POSTGRES_16 --tier=db-f1-micro --region=us-central1
gcloud sql databases create tradier --instance=tradier-db
gcloud sql users set-password postgres --instance=tradier-db --prompt-for-password
```

### Secrets

Credentials are files, not environment variables — on purpose. The
credentials module never loads a token into `os.environ`, so one user's
secrets cannot leak into another user's subprocess. Cloud Run mounts Secret
Manager entries as files, which preserves that exactly and needs no code
change.

Create them from the folder you already have. **Run these yourself** — they
carry live trading tokens and the desk password:

```bash
gcloud secrets create tbot-sampath-env --data-file=customers/sampath/.env
gcloud secrets create tbot-sampath-sam --data-file=customers/sampath/.sam
printf 'postgresql+psycopg://postgres:PASSWORD@/tradier?host=/cloudsql/PROJECT:us-central1:tradier-db' \
  | gcloud secrets create tbot-db-url --data-file=-
```

### Move the ledger

Dry run first — it reports what it would copy and touches nothing:

```bash
python tools/migrate_to_postgres.py --target "postgresql+psycopg://..." --dry-run
```

Then run it for real without `--dry-run`. It refuses to write into a database
that already holds rows unless you pass `--force`, so a repeat run cannot
silently double the ledger. Sequences are reset afterwards, or the next
insert would collide with a copied primary key.

---

## Deploy

**First deploy on paper.** `paper_only` defaults to true; leave it that way
until you have watched the container open, manage and close a sandbox
position end to end.

```bash
gcloud run deploy tradier-bot \
  --source . \
  --region=us-central1 \
  --min-instances=1 --max-instances=1 \
  --no-cpu-throttling \
  --memory=2Gi --cpu=1 \
  --timeout=300 \
  --add-cloudsql-instances=PROJECT:us-central1:tradier-db \
  --set-env-vars=TBOT_CLOUD_MODE=false,TBOT_SUPER_AUTO_SYNC=false,TBOT_PAPER_ONLY=true \
  --set-secrets=/app/customers/sampath/.env=tbot-sampath-env:latest,/app/customers/sampath/.sam=tbot-sampath-sam:latest,TBOT_DATABASE_URL_OVERRIDE=tbot-db-url:latest \
  --no-allow-unauthenticated
```

Notes on the flags that are not obvious:

- `TBOT_CLOUD_MODE=false` — set *explicitly*. `get_settings()` only
  auto-enables cloud mode when the variable is absent, so this is the
  supported escape hatch rather than a hack.
- `TBOT_SUPER_AUTO_SYNC=false` — the vendored signal engines under `runtime/`
  are spawned as subprocesses and expect a working tree, not a container.
  Leaving this on makes the container try to run them every 60 seconds.
- `--no-allow-unauthenticated` — start closed. This service can place real
  trades; open it up only once you have decided how it is fronted.
- Two secrets land as files in the same directory. If Cloud Run rejects that
  pairing in your region, mount one secret containing both files as a single
  volume instead.

### Going live

Only after a clean paper run, and only with the local instance stopped:

```bash
python tools/appctl.py stop          # on the PC — no second monitor
gcloud run services update tradier-bot --region=us-central1 \
  --update-env-vars=TBOT_PAPER_ONLY=false
```

### Firebase Hosting in front (optional)

```bash
npm --prefix frontend run build
firebase deploy --only hosting
```

`firebase.json` serves the SPA from the CDN and rewrites `/api/**` to the
Cloud Run service, so the browser sees one origin. Read the `_comment` block
in that file first: Hosting rewrites cap at 60 seconds and a cold DMI scan is
allowed 120, so the DI readings can 504 on a cold load. The Cloud Run URL
serves the same SPA with no such ceiling.

---

## Verifying

```bash
gcloud run services describe tradier-bot --region=us-central1 \
  --format='value(status.url)'
gcloud run services logs read tradier-bot --region=us-central1 --limit=50
```

Check in this order:

1. `/health` answers.
2. The desk's positions list shows the **same rows it showed locally** — that
   confirms the Postgres copy landed.
3. The venue badge reads what you expect. Remember the desk now defaults to
   **live** on a browser that has never opened it.
4. Logs show the Tradier monitor loop starting. If they do not, `cloud_mode`
   is still on and nothing is managing your stop-losses.
5. Only one instance is serving: `--max-instances=1` in the describe output.

## Rolling back

```bash
gcloud run services update-traffic tradier-bot --region=us-central1 --to-revisions=PREVIOUS=100
```

To abandon the cloud deployment entirely: scale it to zero
(`--min-instances=0 --max-instances=0`), then restart the PC instance with
`python tools/appctl.py start --tunnel`. Point
`TBOT_DATABASE_URL_OVERRIDE` at the same Postgres if you want to keep the
ledger the cloud run built, or migrate it back before restarting on SQLite —
do not run both against different databases with positions open.
