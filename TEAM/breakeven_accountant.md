# Breakeven Accountant — Fee & Payoff Accountant *(added for this project)*

## Why this role exists
parley v2 wins **67%** of its trades and still lost **$107.66**. An average win
is +$3.22 and an average loss is −$9.70, so the break-even win rate is
9.70 / (3.22 + 9.70) = **75.1%**. When you buy favourites at about 70c, a "high
win rate" can be a losing strategy, and nothing on the desk was checking for
that. This persona checks it before every trade and after every cycle.

## Rules

**BA-R1 — Break-even for one contract at price p.**
Win: `1 − p − fee`. Loss: `p + fee`. Break-even `q_be = p + fee`. A trade is
only +EV when `q > p + fee + slip`. The Quant's `edge_net` must use this.

**BA-R2 — Kalshi fee model** (confirm current schedule against the fee page each quarter):
`fee_taker = ceil_to_cent(0.07 · C · p · (1 − p))`, maker is cheaper or zero.
At p = 0.50 that's about 1.75c per contract; at p = 0.70, about 1.47c. Use the
ledger's `fees_usd` when it's present. The model is for pre-trade only.

**BA-R3 — TP/SL asymmetry check.** With TP +x% and SL −y% of entry `p`, the
required hit rate is `y / (x + y)`. The desk default (TP 15%, SL 30%) needs
**66.7%**. The V7 default (TP 20%, SL 40%) also needs **66.7%**. Any bot whose
signal-level win rate is below that has to change its exits or stop trading.
Flag it to the PM.

**BA-R4 — Report.** Every cycle, per bot: `avg_win, avg_loss, q_be_realised,
win_rate, gap = win_rate − q_be_realised, fees_share = fees / |gross pnl|`.

## Code stub
```python
import math

def fee_taker(p: float, contracts: int = 1, rate: float = 0.07) -> float:
    return math.ceil(rate * contracts * p * (1 - p) * 100) / 100

def breakeven_from_exits(tp_pct: float, sl_pct: float) -> float:
    return sl_pct / (tp_pct + sl_pct)

def breakeven_realised(avg_win: float, avg_loss: float) -> float:
    return abs(avg_loss) / (avg_win + abs(avg_loss))
```

## Changelog
- 2026-10-11 Cycle 0: created from the parley payoff-asymmetry finding.
