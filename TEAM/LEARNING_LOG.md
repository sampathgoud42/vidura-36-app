# Learning Log

Newest first. One entry per run of the [Meta-Learning Loop](meta_learning_loop.md).

## Cycle 1 — 2026-10-11 — first automated review (`team.py review`)
Data: 152 settled trades; train = first 70% of each bot by time, holdout = last 30%.
Proposals (all pending operator approval):
- **P-0001 parley block 60–69c: PASS · RECOMMENDED.** Holdout: win 53.1%→64.0%, pnl −86.48→−31.38 (n 32→25). All data: win 65.7%→73.1%, pnl −117.58→−7.63
- P-0002 parley block 80–89c: PASS, below the 30-trade floor
- P-0003/4/5 parley hour blocks (00–03, 12–15, 16–19 CT): PASS, small holdout. Together they block half the clock, which risks overfitting
- P-0006 luck max 11 legs: FAIL (holdout −$4.94)
Not proposed: signal15 / combo15, too few trades (QA-R1). The signal15 losses are trades placed through the operator's signal form.
Re-test trigger: P-0001, if approved, after 30 parley trades: does `team.py status` show live win rate ≥ 70% (its backtest) and pnl ≥ 0?

## Cycle 0 — 2026-10-11 — desk-wide baseline
Data: `var/app-v2.db` → `bot_trade`, 190 rows (84 won, 68 lost, 37 not_found,
1 open), all live, 2026-08-30 → 2026-10-07. No live settled rows for btc15,
btc60 or the commodity bots.

Discrepancies:
- **parley/v2 overall**: n=103, win 67.0%, implied 70.7%, break-even 75.1%, pnl −107.66 → **MODEL** (it buys favourites without a q that beats the price)
- **parley 60–69c**: n=38, win 52.6% vs 64.2% implied, pnl −109.95 → **MODEL**. It is the whole loss on its own.
- parley 80–89c: n=25, win 72.0% vs 83.0% → MODEL (watch; below sample floor)
- **signal15/v1**: n=11, 2 wins, pnl −92.78, every 40–65c entry lost → MODEL + RISK (trend signal with no regime filter; hypothesis, not proven)
- combo15/v1: n=6, pnl −26.77 → too small, PAPER
- luck/v1 0–9c: n=10, 1 win, pnl −26.28 → MODEL (longshot bias)
- **Ledger**: 37/190 not_found (19%); parley 24.3% → **LEDGER**. Every win rate above is on a possibly biased subset.

Updates:
- QS-R4 added: parley no entries at 60–69c (quant_strategist.md)
- QS-R5 added: no buys < 10c unless edge_net ≥ 5c (quant_strategist.md)
- PM status table: parley PROBATION, signal15 SUSPENDED, combo15 PAPER (project_manager.md). **Proposed only; not wired into any bot.**
- BA-R3: desk TP15/SL30 and V7 TP20/SL40 both need a 66.7% hit rate (breakeven_accountant.md)
- New roles: Breakeven Accountant, Regime Sentinel, Ledger Reconciler, Sports & Parlay Specialist

Re-test triggers:
- QS-R4: after 30 more parley trades, re-check the 50–59c and 70–79c buckets still clear break-even
- PM signal15 SUSPENDED: restart only on paper, with RS-R1 regime tags on every entry, n ≥ 30

Open questions / telemetry gaps:
- No `q` recorded on any trade, so model Brier can't be computed yet (only the market's: ~0.22)
- No slip or adverse-fill telemetry (EX-R4/R5), so FILL can't be told apart from MODEL
- Why are 37 rows not_found? Reconciler to run LR-R1 against `/portfolio/settlements`
- `btc15/ENGINE.md` links `runtime/prediction-trade/kalshi/v7_engine.py`, which doesn't exist; the engine is `dmi_engine.py` (stale doc)
