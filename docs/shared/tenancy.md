# Tenancy Decision Doc — Phase 0

**Revision 2.** Revision 1 proposed Postgres row-level security as the
isolation control. You have since directed **SQLite, strictly**. RLS does not
exist in SQLite, so that proposal is withdrawn and replaced — see Q3. Your
decisions are recorded in "Decisions taken" below; the remaining open
questions are at the end.

Citations are to this repository at the imported baseline (`58cc836`), which
is `sampathgoud42/tradier-desk-sam` @ `1cc6cec` unmodified.

---

## Decisions taken

| # | Decision | Effect |
|---|---|---|
| **D1** | Source is the `tradier-desk-sam` codebase, imported here as commit `58cc836`. | `D:\_projects\vidura-36-app` is not reachable from this remote container. See Finding 0. |
| **D2** | **SQLite, strictly.** Postgres is off the table. | RLS is impossible. Isolation moves to the application layer — Q3. Assurance is genuinely lower; stated plainly there. |
| **D3** | **`sampath` is the only customer** for this migration. | One tenant. The isolation defect below is currently theoretical, not live. |
| **D4** | `customers/` stays out of git. | Already true (`.gitignore:21`), verified with `git check-ignore`. |
| **D5** | Found API keys move to `customers/sampath/.env`. | Done — one key found. See `secret-relocation.md`. |

---

## Finding 0 — where the code came from

`vidura-36-app` contained exactly one file: `README.md`. Your local copy at
`D:\_projects\vidura-36-app` is on a Windows machine; this session runs in a
remote Linux container with no path to it.

The same project exists in full at `sampathgoud42/tradier-desk-sam` (646
files, byte-identical `README.md`). I imported it here as commit `58cc836`,
unmodified, as the pre-rebuild baseline to diff against.

**If your local copy has work that was never pushed to `tradier-desk-sam`,
this baseline is stale — push it and tell me.** Everything downstream
inherits this.

---

## Q1 — What is a tenant?

**Each operator is their own tenant, supplying their own broker credentials.
There is no B2B organisation layer.** Unambiguous from the code.

| Evidence | Where |
|---|---|
| `User` has `user_id`, `username`, `email`, `user_root_folder`. No org, team or parent. | `backend/app/models/user.py:22-36` |
| `tenant`, `organization`, `org_id`, `workspace` appear **zero times** in `backend/`. | grep over `backend/**/*.py` |
| Every credential is per-user, in that user's folder: Tradier sandbox+prod tokens and account ids, Kalshi key id + PEM. | `backend/app/services/credentials.py:71-92`, `113-163` |
| The login password is per-user — `customers/<user>/.sam`, plaintext, never in the DB. | `backend/app/services/credentials.py:95-110` |
| Feature entitlement is keyed by **username**, not by any group. | `worlds.json` |
| Only three tables carry an owner column, and it is `user_id`. | `models/trade.py:26`, `models/tradier.py:37`, `models/bot.py:18` |

The tenant axis and the user axis are the same axis, 1:1. With D3, there is
exactly one of them: `sampath`.

**Naming.** I will scope on `user_id` rather than introducing a `tenant_id`
alias. Revision 1 argued for the rename; with one operator, SQLite, and no org
layer on the roadmap, a second name for the same column is ceremony that the
Phase 3 evidence table would strike out. If B2B organisations ever appear,
that rename is a mechanical migration — cheaper than carrying the abstraction
now for a customer count of one.

---

## Q2 — Tenant resolution

### What happens today

Three parallel credential mechanisms, none of which resolves a tenant.

1. **Login session** — `POST /auth/login` verifies against the user's `.sam`
   file and creates an in-memory session bound to `user_id`
   (`api/v1/auth.py:92-105`; `services/sessions.py:94-102`).
2. **Shared API key** — `TBOT_API_KEY`, one fixed string attached to no user
   (`core/config.py:276`).
3. **GEX push token** — `TBOT_GEX_PUSH_TOKEN`, scoped to two ingest paths
   (`main.py:463-466, 494-497`).

The middleware `api_credential_guard` (`main.py:468-514`) checks that one of
these is valid, then calls `call_next`. **It never attaches the session to the
request.** The correct dependency exists — `current_session`
(`api/v1/auth.py:43-57`) — and is used in exactly one place, `/auth/me`
(`api/v1/auth.py:108-111`), which returns the caller their own session.

Every other endpoint takes the tenant **from the client**:

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

The effective mechanism is: **the client tells the server which tenant it is,
and the server believes it.**

The frontend is not the problem — it stores the logged-in user's own id in
`localStorage` and echoes it back (`frontend/src/shared/viduraApi.js:165`,
~40 call sites at `:213-329`). **There is no user-picker anywhere in the UI.**

### What I propose

Unchanged by the SQLite decision:

- The bearer token in `X-API-Key` is the only thing that establishes identity.
  Keep the header name — invisible to the user, keeps the frontend diff to
  deletions only.
- One middleware resolves token → `user_id` into a request-scoped context. It
  is the only code allowed to decide who the caller is.
- **`user_id` is deleted from every request payload, query string and path.**
  Not on the wire means not forgeable.
- The shared `TBOT_API_KEY` cannot survive as-is — it authenticates as nobody
  and therefore as everybody. It becomes a per-operator machine token.
- The GEX push token is unchanged: path-scoped, tenant-less, writing only
  non-tenant market data.

---

## Q3 — Tenant propagation under SQLite

### What happens today

Nothing propagates. `get_db()` yields a plain unscoped session
(`core/database.py:45-51`). Services receive a `User` the endpoint looked up
from the client-supplied id. No mechanism makes an unscoped query fail; a
missing `WHERE user_id = ?` returns every tenant's rows and nothing complains.

### What RLS would have done, and why it is unavailable

Revision 1 proposed Postgres RLS with `SET LOCAL app.tenant_id`, so that a
forgotten filter in application code could not produce a cross-tenant read or
write — the *database* would refuse. **SQLite has no row-level security, no
roles, and no permission system at all.** Any process holding `var/app.db` can
read and write every byte of it. D2 therefore removes the possibility of
enforcing isolation below the application.

I raised this; you have decided SQLite. Proceeding, with the strongest control
SQLite admits and an honest statement of what it does not cover.

### Replacement: automatic scope injection in the ORM layer

Not "developers remember to filter" — that is what the current code does, and
it is why the defect exists. The mechanism must apply the filter whether or
not anyone remembered.

**1. Automatic read scoping.** A `do_orm_execute` event listener injects
`with_loader_criteria(Entity, lambda cls: cls.user_id == current_user_id())`
for every entity in the tenant-scoped registry. This covers every ORM SELECT
— including relationship loads, joins and lazy loads — without the query
author doing anything. A developer who writes `db.query(Trade).all()` gets the
scoped query regardless.

**2. Automatic write scoping.** A `before_flush` hook stamps `user_id` on
inserts from the request context, and refuses any update or delete whose
target row belongs to another user. This is the half that is easy to forget:
Revision 1's QE note about isolation tests that assert only on reads applies
here.

**3. Fail hard when there is no context.** `current_user_id()` raises
`NoTenantContext` when unset, rather than returning `None`. An unscoped query
therefore **errors** instead of quietly returning everything, or — worse —
quietly returning nothing, which reads like "no data" rather than "bug". This
is what makes Phase 6's unscoped-query test meaningful.

**4. Raw SQL is refused by default.** A `before_cursor_execute` hook inspects
statements for tenant-scoped table names and raises unless an explicit
`unscoped()` context manager is active. That escape hatch is used by exactly
the legitimate cross-tenant callers — the reconcile, fast-reconcile and
tradier-monitor loops (`main.py:195-343`), which iterate all users by design —
and every use of it is logged.

**5. CI keeps the registry honest.** A build check fails if any model carrying
`user_id` is absent from the scoped registry. Without this, table #12 is the
one that gets forgotten. This check matters *more* under SQLite than it would
have under RLS, because it is now the only thing standing between a new table
and an unscoped one.

### What this does not cover — stated plainly

This is application-level enforcement. It is bypassed by anything that does
not go through the ORM: a `sqlite3 var/app.db` shell, a script importing the
engine directly, a copy of the file, a backup, or a future maintainer using
raw SQL and adding their table to the `unscoped()` allowlist to make an error
go away.

Under Postgres RLS none of those bypass isolation. Under SQLite all of them
do. **That is a real reduction in assurance and it is the cost of D2.**

Two things make it an acceptable cost here, and I want both on the record
because they are the load-bearing assumptions:

- **There is one operator (D3).** With a single tenant there is no second
  tenant to leak to. The control is being built for correctness and for a
  future second operator, not to contain a live exposure.
- **The database is not shared with untrusted parties.** It is a file on the
  desk's own machine. Anyone who can open it already has the credential folder
  sitting next to it.

**If either stops being true — a second paying operator, or this database
moving somewhere multi-tenant — revisit D2 before that happens, not after.**
That is the trigger condition, and it belongs in the Phase 10 sign-off.

---

## Q4 — Isolation model

**Shared tables, `user_id` column, ORM-enforced scope. One SQLite file.**

### The schema-per-world question is now moot

Revision 1 proposed Postgres schemas per world (`shared`, `trading`,
`bot_station`) with the tenant axis as a column, so the two axes could not
multiply. **SQLite has no schemas.** `ATTACH DATABASE` gives a namespace
prefix across separate files, but SQLite does not support foreign keys across
attached databases — which kills it immediately, since both domains need FKs
into the user table.

So the world boundary moves out of the database and into code: one file, one
namespace, world separation by module boundary and a table-name prefix
convention. Phase 3 will settle the naming.

This is a simplification, and it removes the combinatorial-explosion risk the
brief warned about by removing one of the two axes entirely. The cost is that
the world boundary is now enforced only by convention and code review — worth
noting, but far less serious than the tenant boundary, because a world
boundary violation is a design smell rather than a data breach.

### Schema-per-tenant is still refused

For the same reason as Revision 1: the brief's customer Onboarding Contract
requires adding a customer to be zero deploys, zero file changes, zero schema
changes. Under SQLite, database-per-tenant would mean a file per customer and
a migration run per file — every future migration becomes an N-times loop that
can half-fail, leaving customers on different schema versions. With shared
tables, onboarding is one `INSERT`.

### The second isolation axis nobody wrote down

Isolation is enforced in **two** places today, not one: the database
(`user_id` columns) **and the filesystem** (`customers/<username>/`, with the
root stored as an absolute path in `users.user_root_folder`,
`models/user.py:29`). The filesystem half is guarded by `_check_root_allowed`
(`api/v1/users.py:17-39`), which can be disabled with `TBOT_ALLOW_ANY_ROOT`
(`core/config.py:301`), and by a boot-time migration that silently repoints
roots (`core/database.py:171-241`).

Revision 1 proposed collapsing this into the database by moving credentials
into an encrypted store. **Under D2 + D5 that is now partly reversed**: the
credential file stays on disk at `customers/sampath/.env`, because that is
where you have directed keys to live and because SQLite offers no better
place. The two axes remain. Phase 5 will decide whether encrypting credentials
at rest inside SQLite is worth it, or whether — with one operator on their own
machine — the filesystem is honestly the right home. I lean toward the latter
and will argue it there rather than assume it here.

---

## Q5 — Blast radius

### Today: there is no scope at all

Not a hypothetical about a forgotten `WHERE`. A reachable sequence:

1. Sign in as any valid operator, or hold `TBOT_API_KEY`.
2. `GET /api/v1/users` returns **every** user — `user_id`, `username`, `email`
   and `user_root_folder` — unscoped (`api/v1/users.py:49-52`).
3. `POST /api/v1/tradier/positions` with another operator's `user_id` and
   `live: true` (`api/v1/tradier.py:540, 576-584`).

Step 3 loads that operator's **production** Tradier token and account id from
their folder (`services/credentials.py:149-152`) and places a real order on
their funded account, with their money. The same substitution works for
`/positions/{id}/close`, `/positions/sweep`, `/autotrade/start`, every
`/bots/*/start`, and the whole trade ledger.

`paper_only` defaults true in code (`core/config.py:270`) and would blunt
this, but the README states this machine's `.env` carries
`TBOT_PAPER_ONLY=false`.

**With D3 this is currently theoretical**: one operator means no second
account to reach. It is a latent defect that becomes live the moment a second
operator is registered — which is a one-`INSERT` operation with no review
gate. That is why it is still worth fixing now.

### After the proposed design

An ORM query reaching the data layer without a user context raises
`NoTenantContext` — loud, logged, caught by the Phase 6 unscoped-query test. A
query with the wrong user returns zero rows and cannot write.

What prevents regression, in descending order of how much I trust each:

1. The CI registry check — a new tenant-scoped table cannot ship unscoped.
2. Automatic injection — the filter applies whether or not anyone remembered.
3. The Phase 6 isolation suite: two seeded users, every read **and write**
   path, including lists, search, exports, aggregates, counts and error
   messages. Direct-ID access as the wrong user must return **404, not 403** —
   403 confirms the record exists.

Note the ordering has changed from Revision 1. Under RLS the database was the
control and the tests were the check. Under SQLite the tests and CI *are* the
control, because nothing below the application enforces anything.

---

## Deliberately NOT tenant-scoped

This boundary must be explicit or Phase 6's tests will be written against the
wrong target — failing correct code, or passing over a real leak.

`super_signals`, `daily_snapshots`, `gex0dte_hourly` and `pusher_heartbeats`
(`models/super_research.py:17, 50, 71, 106`) have **no owner column today and
should not gain one.** They are market data — signal output, SPY dealer gamma,
index snapshots. The same numbers for everyone; no confidentiality interest.

The line: **market observations are global; positions, orders, ledgers, bot
runs and credentials are scoped.** A future table that is not obviously on one
side is scoped until argued otherwise.

---

## Consequences of the decisions above

1. **SQLite stays; isolation is application-level only.** Lower assurance than
   RLS, accepted under D2, acceptable while D3 holds. Trigger condition for
   revisiting is written into Q3.
2. **`user_id` leaves the wire on ~40 endpoints.** Frontend diff in the same
   change set — deletions in `viduraApi.js` only. Phase 4 owns it.
3. **`TBOT_API_KEY` becomes a per-operator token.** Breaks scripts using the
   shared key. No UI impact.
4. **Credentials stay on the filesystem** at `customers/sampath/.env`. Phase 5
   revisits encryption-at-rest.
5. **The `.sam` plaintext password persists for now.** It is a plaintext
   password on disk. Phase 8 must determine the target hash and will **stop
   and ask** rather than guess — it is the one migration that can lock the
   operator out of their own desk.
6. **Flyway is now questionable.** The brief mandates it. Flyway is a JVM tool
   with community-tier SQLite support, against a Python/FastAPI project whose
   natural fit is Alembic. Raising it here because D2 sharpens it; the
   decision belongs to Phase 3.

---

## Four-role review

**Architect.** With one operator and SQLite, the design collapses pleasantly:
no schemas, no tenant table, no envelope encryption, one scoping registry and
one middleware. The main risk is that automatic ORM injection is invisible —
someone will eventually add a raw query and widen the `unscoped()` allowlist
to silence an error. The allowlist must be short, logged, and reviewed.

**Product Owner.** No user-visible change, and I can be specific rather than
hopeful: the frontend has no user-picker and already sends only the logged-in
user's own id from `localStorage` (`viduraApi.js:165`). Removing `user_id`
from the wire removes a capability **no screen exposes**. Constraint #1 holds.
*Still needs your confirmation (Q-A below):* whether any script or curl
workflow uses `TBOT_API_KEY` plus a hand-typed `user_id`. Invisible to the UI,
so undetectable from code.

**Quality Engineer.** The test suite is no longer a check on the control — it
*is* the control. That raises the bar: isolation tests must cover writes, not
just reads, and must run through the real session factory rather than a
hand-built session, or they will validate a code path production never takes.
The existing suite (356 pass, 51 xfail per the README) needs a Phase 1 audit
for what it actually asserts.

**Ops.** SQLite removes the RLS operational trap Revision 1 worried about —
an on-call psql session seeing an empty table. It replaces it with a different
one: `var/app.db` is a single file that is the entire system of record for
open positions. `TBOT_TRADIER_MONITOR_INTERVAL_S` is the stop-loss reaction
time, so a corrupted or locked database is a **financial** event. Backup,
WAL-checkpoint and restore procedures move up in priority for Phase 5's
`database.md`.

**Where the roles disagree.** Revision 1's disagreement — Architect and Ops
wanting RLS versus the project's copy-the-folder-and-run value — is resolved
by D2 in favour of the latter. The residual disagreement is narrower: QE
argues that making tests the sole isolation control is fragile for a system
that moves real money; Architect and PO argue that with one operator on one
machine the exposure is theoretical and the simplicity is worth more. I have
written the trigger condition into Q3 so that this is revisited on evidence
(a second operator) rather than on memory.

---

## Still open

| # | Question | My recommendation |
|---|---|---|
| **Q-A** | Has any script, curl or Swagger workflow ever driven the desk with `TBOT_API_KEY` plus a hand-typed `user_id`? | If yes, tell me — this design removes it, and I would replace it deliberately rather than break it silently. |
| **Q-B** | Does your local `D:\_projects\vidura-36-app` contain work not in `tradier-desk-sam`? | If yes, push it — baseline `58cc836` is stale and every later phase inherits it. |
| **Q-C** | Confirm the scoped/global split (market data global; positions, ledgers, bot runs, credentials scoped). | As written. |

**Phase 0 output complete. Approve, and Phase 1 (read-only extraction) starts.**
