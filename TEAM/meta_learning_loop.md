# Meta-Learning Loop (mandatory after every cycle, backtest, or simulation)

## Procedure

**0. Measure.** `python TEAM/team.py review`. Every persona reviews the ledger,
proposes versioned rules, and backtests each one on a time-based holdout.
`python TEAM/scripts/postmortem.py` gives the raw calibration table. The Ledger Reconciler runs first. If LR-R3 breaks, stop here and fix
the ledger.

**1. Identify discrepancies.** List every cell (bot × 10c bucket) where
- realised win rate − implied price < −5 pts, or
- realised win rate < realised break-even (BA-R4), or
- avg slip > 1c, or adverse-fill share > 40% (EX-R4/R5).

**2. Isolate the variable.** Tag each discrepancy with one QA-R3 cause:
`DATA · MODEL · FILL · RISK · LEDGER`. If the evidence can't support a single
cause, the tag is `UNKNOWN` and the action is *collect the missing telemetry*,
not change a rule.

**3. Self-update.** For each tagged discrepancy that clears QA-R1's sample floor:
- Edit the owning persona's file. Change or add one numbered rule, and put the
  evidence (n, gap, PnL) in the rule text.
- Add a line to that file's Changelog.
- Add an entry to [LEARNING_LOG.md](LEARNING_LOG.md) using the template below.

**4. Guardrails on self-update.**
- Rules reach live trades **only** through `team.py approve P-xxxx` (operator
  only). That publishes a new ruleset version to `TEAM/rules/active.json`, and
  the gate (`backend/app/domains/botstation/team_gate.py`) enforces it on the
  next order: parley, luck and combo15 at `engine.place_combo`, and signal15 at
  `signal_trade.place`. Never edit `runtime/` bot code or `builtin.py` from this loop.
- Approve only RECOMMENDED proposals by default. PASS without RECOMMENDED means
  the sample is too small to tell a real effect from noise.
- After approval, `team.py status` shows gate hits and the bot's live results
  since that rule went in. A rule whose live results are worse than its
  backtest after 30 trades gets retired (`team.py retire`) or rolled back
  (`team.py rollback N`).
- Change one rule per cause per cycle, so the next cycle can tell what worked.
- Every new rule has a **re-test trigger**: the condition under which QA
  re-judges it, e.g. "after 30 more trades outside the band."
- A rule that fails its re-test is reverted. The reversion is logged, not deleted.

## LEARNING_LOG entry template
```
## Cycle N — YYYY-MM-DD — <scope>
Data: <rows, date range, live/paper>
Discrepancies:
  - <bot/bucket>: n=, win=, implied=, b/even=, pnl=  → cause: <TAG>
Updates:
  - <RULE-ID> <added|changed|reverted>: <one line>   (file)
Re-test triggers:
  - <RULE-ID>: <condition>
Open questions / telemetry gaps:
  - ...
```
