# Secret relocation — API keys moved out of source control

Full secret inventory is Phase 1. This covers the one credential found in
tracked source during Phase 0 and relocated on your instruction.

## What was found

A scan of all 646 tracked files (assigned-secret patterns, 24+ char literals,
embedded PEM blocks, credential-bearing URLs) found **exactly one** real
secret in source control:

| Key | Was at | Now at |
|---|---|---|
| `APININJAS_API_KEY` | `backend/app/core/config.py:234`, hardcoded as a field default | `customers/sampath/.env` (gitignored) |

Everything else that matched was a documentation placeholder:
`postgresql+psycopg://user:pw@host/db` (`config.py:42`, `.env.example:87`),
a PEM shape in a comment (`runtime/indicators/cb_btc_signal.py:28`), and
`PASTE_TOKEN` examples in `DEPLOY.md`. The two **tracked** bot config files
(`btc.env`, `kaslhi_sports.env`) carry no credentials — both say so in their
own headers, and the scan confirms it.

## What changed in code

`config.py:234` no longer carries a value:

```python
apininjas_api_key: str = ""
```

Per the brief's rule — *never default a secret* — there is no fallback value.
Empty means "not configured".

## Two things you need to know

**1. It is dead config.** `apininjas_api_key` is declared and read by
**nothing** — zero consumers anywhere in `backend/`, `runtime/`, `frontend/`
or `tests/`. The commodity path that presumably once used it now goes through
`FLASHALPHA_API_KEY`, which `runtime/super_research/gex_daily.py:45-49` reads
from `flashalpha.env` (gitignored, never committed, so not a leak).

The field is kept — empty — rather than deleted, so its removal goes through
the Phase 9 dead-code review with the rest. Emptying it changes no behavior,
because nothing read it.

**2. It is compromised and must be rotated.** Removing it from the working
tree does not remove it from history. The value is still in the git history of
both `vidura-36-app` and `tradier-desk-sam`, and `tradier-desk-sam` was
readable by anything with access to that repo. Per the brief's Phase 8 rule, a
credential that has been in source control is rotated, not migrated.

**Rotate it at api-ninjas.com and put the new value in
`customers/sampath/.env`.** The old value is in that file now only so the
current behavior is preserved byte-for-byte until you do; since nothing reads
it, you can rotate at your convenience with zero risk of breaking the desk.

## The customer credential file

`customers/sampath/.env` is the single per-operator credential file, matching
the existing contract in `backend/app/services/credentials.py:71-92, 113-163`.
It is gitignored (`.gitignore:21`) — verified with `git check-ignore` — so it
lives only on the machine that runs the desk. This container's copy is
ephemeral; recreate it on your own machine with:

```
APININJAS_API_KEY=<the rotated key>
```

alongside the Tradier and Kalshi keys already in that file.

## One design note, flagged not acted on

API Ninjas is an **application-level vendor key** — the same key would serve
every operator — whereas `customers/<user>/.env` is for **per-customer**
credentials. Putting it there means a second operator needs their own API
Ninjas key or a duplicated value.

You asked for it there "for now", and with a single operator (`sampath`) it
makes no practical difference. Phase 5 defines the two config axes properly
and will revisit it. Recording the trade-off here so it is a decision rather
than an accident.
