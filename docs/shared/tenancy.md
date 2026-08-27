# Tenancy Decision Doc — Phase 0

Status: **awaiting approval**. Nothing in Phase 1+ starts until this is signed off.

Every claim below cites the file and line it came from. Citations are against
`sampathgoud42/tradier-desk-sam` @ `1cc6cec` — see Finding 0 for why.

---

## Finding 0 — the code is not in this repository

`sampathgoud42/vidura-36-app` contains exactly one file: `README.md` (388 lines).
No `backend/`, no `frontend/`, no `runtime/`, no tests.

The README describes a system that exists in full in
**`sampathgoud42/tradier-desk-sam`** — 646 files, and its `README.md` is
byte-identical to this repo's. I attached that repo read-only and cloned it to
`/home/user/tradier-desk-sam`. All Phase 0 evidence is from there.

**This needs your confirmation (Q1 below):** I am treating `tradier-desk-sam` as
the reference codebase and `vidura-36-app` as the destination for the rebuild.
If the real source of truth is a working copy that was never pushed, or one of
`vidura-world-py-api` / `vidura-world-js` / `38trades-py-claude`, tell me now —
every later phase inherits this choice.

---

## Q1 — What is a tenant?

**Answer: each end operator is their own tenant, supplying their own broker
credentials. There is no B2B organisation layer.** The evidence is unambiguous;
I am not asking you to adjudicate the *current* model.

| Evidence | Where |
|---|---|
| `User` has `user_id`, `username`, `email`, `user_root_folder`. No org, no team, no parent. | `backend/app/models/user.py:22-36` |
| The strings `tenant`, `organization`, `org_id`, `workspace` appear **zero times** in `backend/`. | grep over `backend/**/*.py` |
| Every credential is per-user, in that user's own folder: Tradier sandbox+prod tokens and account ids, Kalshi key id + PEM. | `backend/app/services/credentials.py:71-92`, `113-163` |
| The login password is per-user too — `customers/<user>/.sam`, plaintext, never in the DB. | `backend/app/services/credentials.py:95-110` |
| Feature entitlement is keyed by **username**, not by any group. | `worlds.json` |
| Only three tables carry an owner column (`trades`, `tradier_positions`, `bot_runs`) and it is `user_id`. | `models/trade.py:26`, `models/tradier.py:37`, `models/bot.py:18` |

So the tenant axis and the user axis are the same axis, 1:1. A "customer" is one
operator with one funded Tradier account and one funded Kalshi account.

**Design consequence.** I recommend naming the scope column `tenant_id` and
seeding exactly one tenant row per operator, rather than scoping on `user_id`
directly. That is a naming and typing decision, not a speculative entity: it
gives the enforcement layer (below) one thing to bind to, and it means a future
"two logins on one funded account" does not require touching every table. I am
**not** proposing an `organizations` table — no evidence supports one, and
Phase 3's evidence table would delete it.

**The one thing I cannot answer from code, and need from you (Q2 below):**
whether B2B orgs are on the roadmap. Zero code evidence either way. A separate
tenant table is cheap now and expensive to retrofit later.

---

## Q2 — Tenant resolution

### What happens today

There are **three** parallel credential mechanisms, and none of them resolves a
tenant.

1. **Login session.** `POST /auth/login` verifies the password against the
   user's `.sam` file and creates an in-memory session bound to `user_id`
   (`api/v1/auth.py:92-105`; `services/sessions.py:94-102`).
2. **Shared API key.** `TBOT_API_KEY` — one fixed string, not attached to any
   user (`core/config.py:276`).
3. **GEX push token.** `TBOT_GEX_PUSH_TOKEN`, scoped to exactly two ingest paths
   (`main.py:463-466, 494-497`).

The middleware `api_credential_guard` (`main.py:468-514`) checks that *one of
these is valid* and then calls `call_next`. **It never attaches the session to
the request.** There is a correct dependency for this — `current_session`
(`api/v1/auth.py:43-57`) — and it is used in exactly one place, `/auth/me`
(`api/v1/auth.py:108-111`), which returns the caller their own session.

Every other endpoint takes the tenant **from the client**, as a query parameter
or a body field:

```python
# backend/app/api/v1/tradier.py:540-541
class OpenRequest(BaseModel):
    user_id: str
    ...
# backend/app/api/v1/tradier.py:576-583
@router.post("/positions", operation_id="openTradierPosition")
def open_position(payload: OpenRequest, db: Session = Depends(get_db)) -> dict:
    user = _user_or_404(db, payload.user_id)   # trusts the caller
```

`user_id` is a client-supplied parameter on **~40 endpoints** across
`tradier.py`, `bots.py`, `desk36.py` and `worlds.py`.

So the effective resolution mechanism today is: **the client tells the server
which tenant it is, and the server believes it.**

The frontend is not the problem — it stores the logged-in user's own id in
`localStorage` and echoes it back (`frontend/src/shared/viduraApi.js:165`, and
~40 call sites at `:213-329`). There is **no user-picker anywhere in the UI.**
That fact does the PO work below.

### What I propose

**Exactly one mechanism, resolved once, at the edge.**

- The bearer token in `X-API-Key` is the *only* thing that establishes identity.
  Keep the header name — it is invisible to the end user and keeps the frontend
  diff to deletions only.
- One middleware resolves token → `tenant_id`, and puts it in a request-scoped
  context. It runs before routing, and it is the only code in the system allowed
  to decide who the caller is.
- **`user_id` is deleted from every request payload, query string and path.**
  A parameter that names the tenant cannot exist on the wire; if it is not on
  the wire, it cannot be forged.
- The shared `TBOT_API_KEY` **cannot survive in its current form** — it is a
  credential that authenticates as nobody and therefore, under the new model,
  as everybody. It becomes per-tenant machine tokens: same header, same
  transport, issued and revoked per tenant at runtime.
- The GEX push token stays exactly as it is: path-scoped, tenant-less, and it
  writes only to non-tenant market data (see "Deliberately not tenant-scoped").

---

## Q3 — Tenant propagation

### What happens today

Nothing propagates. `get_db()` yields a plain unscoped session
(`core/database.py:45-51`). Services receive a `User` object that the endpoint
looked up from the client-supplied id. There is no mechanism — none — that
would make an unscoped query fail. A missing `WHERE user_id = ?` returns every
tenant's rows and nothing complains.

### What I propose: Postgres Row-Level Security, as the load-bearing control

**Mechanism.** The app connects as a role that is *not* the table owner and does
**not** have `BYPASSRLS`. Every tenant-scoped table gets
`ENABLE ROW LEVEL SECURITY` **and** `FORCE ROW LEVEL SECURITY`, with a policy of
the shape:

```sql
CREATE POLICY tenant_isolation ON trading.positions
  USING      (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

The edge middleware opens the transaction and issues
`SET LOCAL app.tenant_id = '<uuid>'` as its first statement.

**Why `SET LOCAL` and not `SET`:** `SET LOCAL` is scoped to the transaction, so
a pooled connection handed back to the pool cannot carry the previous request's
tenant into the next one. With plain `SET` and PgBouncer in front, that is
precisely how you leak. This is the single most important implementation detail
in this document.

**Why `current_setting()` with no `missing_ok` default:** when the GUC is unset,
`current_setting('app.tenant_id')` raises SQLSTATE 42704 rather than returning
NULL. An unscoped query therefore **errors** instead of quietly returning zero
rows. Phase 6 requires a test that unscoped access "fails hard rather than
returning everything" — this is what makes that test pass, and a policy written
with `current_setting(..., true)` would silently return an empty set instead,
which is a much worse failure because it looks like "no data" rather than "bug".

**Why RLS rather than a repository base class.** The brief offers both. A
repository base class that refuses unscoped queries is enforced *by developers
staying inside it*: it is bypassed by raw SQL, by an ORM escape hatch, by a
background job written in a hurry, by a psql session during an incident, and by
the next person who does not know the rule. RLS is enforced by the database,
below every one of those paths. Given that the failure mode here is one
operator trading on another operator's funded account, the control has to sit
below the application, not inside it.

I still want the repository base class — as defence in depth and for fast
feedback in tests — but RLS is what the design leans on.

**Cost, stated plainly:** this makes **Postgres mandatory** and ends SQLite.
Today SQLite is the default and Postgres is an override
(`core/config.py:40-44`, `304-316`). SQLite has no RLS, so "runs anywhere with
nothing outside the folder" — which the README calls "the whole point of this
project" — no longer holds for the database. This is the biggest thing Phase 0
takes away, and it is a genuine loss for the local-development story. Mitigation
is a containerised Postgres in the local run (Phase 5 `run-local.md`). Flagged
as Q3 for your approval because it contradicts a stated project value.

**Background jobs.** The reconcile, tradier-monitor, fast-reconcile and
super-sync loops (`main.py:195-343`) iterate every user by design. They are
legitimately cross-tenant. They must **not** get a bypass role. They loop
tenants and open one `SET LOCAL`-scoped transaction *per tenant*, so a bug in a
loop leaks one tenant into nothing, and the same policy covers them.

---

## Q4 — Isolation model, and how the two axes compose

**Recommendation: shared tables, `tenant_id` column, RLS. Schema-per-*world*.
Never schema-per-tenant.**

### The composition question the brief asks about

The brief warns that schema-per-world × schema-per-tenant is a combinatorial
explosion. It would be — so the design does not put both axes in schemas:

| Axis | Represented as | Grows when | Count |
|---|---|---|---|
| **World / domain** | Postgres schema | code is deployed | fixed, small (2–3) |
| **Tenant** | a column + RLS policy | a customer signs up | unbounded, runtime |

3 schemas × N tenants = **3 schemas**. There is no explosion, because the tenant
axis never becomes a DDL object. That is the whole reason for the split.

Proposed schemas (subject to Phase 1 confirming the domain hypothesis):

- `shared` — tenants, users, credentials, and non-tenant market data. **Owns the
  user/tenant tables**, answering the brief's "which schema owns the user
  tables" question. Both domains hold FKs into it; cross-schema FKs are fine
  within one Postgres database.
- `trading` — Tradier Platform + 36 Trade Desk (one domain, two clients —
  Phase 1 will prove or disprove this).
- `bot_station` — Kalshi.

### Why not schema-per-tenant or database-per-tenant

Both are disqualified by the brief's own customer Onboarding Contract, which
requires adding a customer to be **zero deploys, zero file changes, zero schema
changes**. Schema-per-tenant makes onboarding a DDL operation and makes every
future migration an N-times loop that can half-fail, leaving tenants on
different schema versions. Database-per-tenant is the same, worse, plus a
connection pool per tenant. With shared tables, onboarding a customer is one
`INSERT` — which is exactly what the contract demands.

### The second isolation axis nobody wrote down

Today isolation is enforced in **two** places, not one: the database
(`user_id` columns) **and the filesystem** (`customers/<username>/`, with the
per-user root stored as an absolute path in `users.user_root_folder`,
`models/user.py:29`). The filesystem half is guarded by `_check_root_allowed`
(`api/v1/users.py:17-39`), which can be switched off entirely with
`TBOT_ALLOW_ANY_ROOT` (`core/config.py:301`), and by a boot-time migration that
silently repoints roots (`core/database.py:171-241`).

Moving credentials into the encrypted store (Phase 5) **collapses this second
axis into the first**. That is a large simplification and I want it called out
as a deliberate goal, not a side effect: after the rebuild there is exactly one
thing to get right, not two.

---

## Q5 — Blast radius

### Today: a single missing scope is not the risk. There is no scope at all.

This is not a hypothetical about a future forgotten `WHERE` clause. The current
system has a live, reachable cross-tenant path, and I can state it as a
sequence:

1. Sign in as any valid operator, or hold `TBOT_API_KEY`.
2. `GET /api/v1/users` returns **every** user — `user_id`, `username`, `email`
   and `user_root_folder` — with no scoping whatsoever
   (`api/v1/users.py:49-52`).
3. `POST /api/v1/tradier/positions` with another operator's `user_id` and
   `live: true` (`api/v1/tradier.py:540, 576-584`).

Step 3 loads that operator's **production** Tradier token and account id from
their folder (`services/credentials.py:149-152`) and places a real order on
their funded account, with their money. The same substitution works for
`/positions/{id}/close`, `/positions/sweep`, `/autotrade/start`, every
`/bots/*/start`, and the entire trade ledger.

The only thing standing between any authenticated operator and every other
operator's funded brokerage account is that nobody has typed a different
`user_id`. `paper_only` defaults true in code (`core/config.py:270`) and would
blunt this — but the README states this machine's `.env` carries
`TBOT_PAPER_ONLY=false`.

I am reporting this as the current state, not as an accusation: the system was
built as a single-operator desk and the README is honest about that. It becomes
a severe finding *because* the brief states the target is multi-tenant. **It
also means the rebuild is not merely a refactor — it is the fix.**

Related, and separate: `apininjas_api_key` is hardcoded with a real-looking
value in source control (`core/config.py:234`). Under Phase 8's rule that is
**compromised and must be rotated, not migrated.** Full secret sweep is Phase 1.

### After the proposed design

A query that reaches the database without a tenant context raises 42704 and
returns a 500 — loud, logged, and caught by the Phase 6 unscoped-query test. A
query with the *wrong* tenant returns zero rows and cannot write, because
`FORCE ROW LEVEL SECURITY` applies `WITH CHECK` to writes as well as reads.

What prevents it reaching production, in order of how much I trust each:

1. RLS — a bug in application code cannot produce a cross-tenant read or write.
2. The Phase 6 tenant-isolation suite, per the brief: two seeded tenants, every
   read and write path, including lists, search, exports, aggregates, counts and
   error messages. Direct-ID access as the wrong tenant must return **404, not
   403** — 403 confirms the record exists.
3. A CI check that fails the build on a new tenant-scoped table without an RLS
   policy. Without this, table #40 is the one that gets forgotten.
4. The repository base class, as defence in depth.

---

## Deliberately NOT tenant-scoped

This boundary has to be explicit, or the Phase 6 isolation tests will be written
against the wrong target and will either fail correctly-designed code or pass
over a real leak.

`super_signals`, `daily_snapshots`, `gex0dte_hourly` and `pusher_heartbeats`
(`models/super_research.py:17, 50, 71, 106`) have **no owner column today, and
should not gain one.** They are market data — signal engine output, SPY dealer
gamma, index snapshots. The same numbers for everyone; not customer data; no
confidentiality interest. They live in `shared` and are readable by any
authenticated tenant.

The line: **market observations are global; positions, orders, ledgers, bot runs
and credentials are tenant-scoped.** If a future table is not obviously on one
side, it is tenant-scoped until argued otherwise.

---

## Consequences you are also approving

1. **Postgres becomes mandatory; SQLite is dropped.** Contradicts the project's
   self-contained value. (Q3)
2. **`user_id` leaves the wire on ~40 endpoints.** Requires a frontend diff in
   the same change set — deletions in `viduraApi.js` only. Phase 4 owns it.
3. **`TBOT_API_KEY` becomes per-tenant tokens.** Breaks any existing script or
   cron using the shared key. No UI impact.
4. **Per-customer credentials leave the filesystem** for the encrypted store,
   collapsing two isolation axes into one.
5. **The `.sam` plaintext password file goes away.** It is a plaintext password
   on disk. Phase 8 must determine the target hash and will **stop and ask**
   rather than guess — flagged now because it is the one migration that can
   lock every operator out of their own desk.

---

## Four-role review

**Architect.** Tenant as a column with RLS is the only model that satisfies the
zero-DDL customer-onboarding contract. Cost of change is low: one policy per
table, mechanical, CI-enforceable. The real architectural win is deleting the
filesystem isolation axis.

**Product Owner.** No user-visible change, and I can be specific rather than
hopeful about that: the frontend has no user-picker and already sends only the
logged-in user's own id from `localStorage` (`viduraApi.js:165`). Every operator
is already, in practice, operating exactly one account — their own. Removing
`user_id` from the wire removes a capability **no screen exposes**. Constraint
#1 holds.
*Caveat I want you to confirm (Q4):* if you have ever used the shared
`TBOT_API_KEY` plus a hand-typed `user_id` to operate another operator's desk —
from a script, curl, or Swagger — that workflow dies here. It is invisible to
the UI, so I cannot detect it from code.

**Quality Engineer.** What breaks silently is a new table added without a
policy — hence the CI check, which I rate above the tests themselves. Second
silent breakage: `SET` instead of `SET LOCAL` under a pooled connection, which
tests on a single connection will never catch; the isolation suite must run
through the real pool. Third: an isolation test that seeds two tenants but
asserts only on reads.

**Ops.** RLS is invisible day-to-day until an incident, when the on-call psql
session sees an empty table and concludes the data is gone. `incident-runbook.md`
must open with "how to query as a tenant". A break-glass `BYPASSRLS` role should
exist, be separately credentialed, and be audited — I would rather have one that
is logged than have someone invent one under pressure. Master-key loss makes
every customer credential unrecoverable; that sentence goes in `secrets.md`
verbatim, per the brief.

**Where the roles disagree.** Architect and Ops want RLS; the README's stated
value — a folder you copy anywhere and run — wants SQLite. **They cannot both
win.** I have recommended RLS because the risk it controls is one customer
trading on another customer's money. But this is your call, and it is Q3.

---

## Decisions I need before Phase 1

| # | Question | My recommendation |
|---|---|---|
| **Q1** | Is `tradier-desk-sam` @ `1cc6cec` the reference codebase, with `vidura-36-app` as the rebuild destination? | Yes — READMEs are byte-identical. |
| **Q2** | Are B2B organisations (several logins under one funded account) on the roadmap? | If unsure, say so — I will use `tenant_id` 1:1 with the operator and keep an `organizations` table out until evidence exists. |
| **Q3** | Approve dropping SQLite and requiring Postgres, accepting the loss of the copy-the-folder-and-run property for the DB? | Yes. RLS is the control; SQLite cannot provide it. Local dev gets a containerised Postgres. |
| **Q4** | Has anyone ever driven another operator's account via `TBOT_API_KEY` + a hand-typed `user_id`? | If yes, tell me — it is a real workflow that this design removes, and I would need to replace it deliberately. |
| **Q5** | Confirm the tenant-scoped / global split above (market data global; positions, ledgers, bot runs, credentials tenant-scoped). | As written. |

**STOP — Phase 0 output complete, awaiting approval.**
