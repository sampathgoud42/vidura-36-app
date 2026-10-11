# TEAM — Kalshi multi-persona trading desk

This folder is the operating manual for the Kalshi side of vidura-36. Each file
is one persona: its mandate, its numbered rules, and a code stub. The rules are
numbered (`PM-R3`, `QS-R2`, …) so the Meta-Learning Loop can amend them by ID
and the changelog stays traceable.

**Review → propose → backtest → approve → enforce.**

```bash
python TEAM/team.py review          # personas review the ledger; writes proposals + TEAM/reviews/<date>_review.md
python TEAM/team.py list            # pending proposals (* = RECOMMENDED)
python TEAM/team.py show P-0001     # evidence + train / holdout / all backtest
python TEAM/team.py approve P-0001  # -> TEAM/rules/active.json v(N+1); enforced on the next order
python TEAM/team.py status          # active rules, gate hits, live results since approval
python TEAM/team.py retire P-0001   # or: rollback N
```

Nothing reaches a live trade without an `approve`. The gate
(`backend/app/domains/botstation/team_gate.py`) covers parley, luck, combo15
and signal15. The runtime 15-minute bots (btc15, btc60, commodities) aren't
gated yet because the ledger has no live trades from them to backtest.

## Roster

| # | File | Persona | Owns |
|---|---|---|---|
| 1 | [project_manager.md](project_manager.md) | Risk & Strategy Orchestrator | sizing, halts, which bots/markets may trade |
| 2 | [data_engineer.md](data_engineer.md) | Data & Feed Specialist | order books, spot feeds, staleness, ledger inputs |
| 3 | [quant_strategist.md](quant_strategist.md) | Signal & Probability Architect | `q` (true prob), edge, BUY/SELL/HOLD |
| 4 | [execution_bot.md](execution_bot.md) | Trade Executor | limit placement, fills, sell_guard, shards |
| 5 | [qa_backtester.md](qa_backtester.md) | Continuous Optimizer | post-mortems, calibration, promotion/demotion |
| 6 | [breakeven_accountant.md](breakeven_accountant.md) | Fee & Payoff Accountant | break-even win rate, fees, payoff asymmetry |
| 7 | [regime_sentinel.md](regime_sentinel.md) | Regime & Event Sentinel | trend/chop state, macro calendar blackouts |
| 8 | [ledger_reconciler.md](ledger_reconciler.md) | Ledger Truth Keeper | `bot_trade` integrity, `not_found` rows, settlements |
| 9 | [sports_parlay_specialist.md](sports_parlay_specialist.md) | Sports & Parlay Specialist | leg probabilities, correlation, combo pricing |

Roles 6–9 were added for this project specifically. Why each one exists is in
its own file, and every reason traces back to a number in the Cycle 0 audit.

## The loop

```
Data Engineer ──► Quant Strategist ──► Project Manager ──► Execution Bot
      ▲               (q, edge)         (size / veto)        (orders)
      │                                                         │
      └──── Meta-Learning Loop ◄── QA Backtester ◄── Ledger Reconciler
               (meta_learning_loop.md)   (calibration)     (truth)
```

- [meta_learning_loop.md](meta_learning_loop.md): the mandatory procedure that runs after every cycle
- [LEARNING_LOG.md](LEARNING_LOG.md): one entry per run of the loop, newest first
- [scripts/postmortem.py](scripts/postmortem.py): read-only calibration report over `var/app-v2.db`

```bash
python TEAM/scripts/postmortem.py
```
