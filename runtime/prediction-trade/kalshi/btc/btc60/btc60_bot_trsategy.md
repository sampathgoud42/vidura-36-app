# BTC-60 Bot Strategy — "BURST-COMMITTEE" (v1, 2026-07-10)

Design document for the next-generation Kalshi BTC hourly (KXBTCD) bot,
built from: (a) forensic mining of every fable5 live/paper trade log,
(b) a 4-phase signal research program over 46 days of BTC-USD 5-minute
candles (13,265 bars), and (c) external research on short-horizon BTC
predictability.  All research scripts and reports live in this folder.

---

## 1. Executive summary

* The old fable5 strategy ("buy the 72-80c favorite, TP +16% / SL -20%")
  is **structurally -EV**: across 185 logged trades (live + 2 paper runs)
  it won ~55% vs the ~67% breakeven its payoff shape requires.
  Live bankroll went **$100 → $40.39 in 3 days**.
* Four phases of backtesting show that **no static 5-minute signal predicts
  a ±$100/30-min BTC move with 80%+ first-touch accuracy across regimes**.
  Phase-1 found combos at "100%" over 12 days; over 46 days every one of
  them collapsed to 48-64%.  (This matches the external literature:
  ultra-short BTC direction is near-random unconditionally; edge is
  conditional and regime-dependent.)
* What DOES survive 46 days and weekly walk-forward folds is a small
  **committee of 5 signals at 54-64% first-touch accuracy** with real
  information content (up to **+$117 mean / +$98 median forward 30-min
  drift** for the best member) firing a combined ~8-11×/day before
  de-duplication.
* A 55-64% edge prints money on Kalshi **only with a payoff shape that
  needs <55% to break even**.  The new bot therefore buys **near-the-money
  (~45-55c) contracts** in the signal direction — roughly symmetric
  payoff — instead of overpaying for 72-80c favorites, and exits on
  repricing or a 30-minute time-stop, never at settlement.
* Accuracy is **maximized adaptively, not statically**: a weekly
  self-recalibration reweights committee members by trailing 7-day
  accuracy and disables members that fall under breakeven.  This is the
  honest answer to "keep researching until 99%": chase the regime, don't
  curve-fit a fantasy constant.

---

## 2. What the logs taught us (forensics)

Data: `btc60_fable5_trade_history*.csv` (live + paper, from this folder
plus an earlier standalone btc15 checkout that no longer feeds anything
here), day logs, watchdog logs.  185 trades total,
2026-07-01 → 2026-07-10.

| Finding | Evidence | Design consequence |
|---|---|---|
| Overall WR ~55% vs 66.7% breakeven | all 3 datasets independently | payoff shape must break even ≤55% |
| YES side is the black hole | live YES: 52.7% WR, -$54.72; paper YES: 43-46% WR, all of the drawdown | direction must come from the signal, not from "spot vs strike favorite" |
| NO side ≈ breakeven-positive | 61-64% WR everywhere | short/mean-down edge is real on this tape |
| Catastrophic settlement exits | 6 live exits at ≤5c = -$36 (over half the live loss) | hard 30-min time-stop; NEVER hold into final 5 min; watchdog + lock kept |
| Worst hours 16-23 UTC | live: 36.8%/33.3% WR buckets | optional session filter; learner tracks per-session WR |
| Learner tuned the wrong knobs | pv%/bid_lo churned while the core edge was negative | learner now reweights SIGNALS, not just size |
| Two instances corrupted the ledger (07/02) | fable5 docstring + state file archaeology | keep single-instance lock, bankroll ledger, event-position adoption |

## 3. Research method (reproducible)

All scripts run standalone from this folder against the shared
`stock-trade/` engine (`combined_scalp` + `38trades_signals.py`):

| Phase | Script | Question | Output |
|---|---|---|---|
| 1 | `backtest_signals_btc60.py` | which of ~30 signals × filters × combos predict ±$100/30min? 3,586 combos, windows 24/48/72/100/150/250h | `btc60_signal_backtest_report.md`, `.csv` |
| 2 | `btc60_validate_ensemble.py` | do phase-1 winners survive 46 days + weekly folds + Wilson bounds? ADX fine-sweep 15→42.5, CUSUM k 1.0→2.5 | `btc60_ensemble_validation.md` |
| 3 | `btc60_regime_signal.py` | does a volatility-regime gate (ATR budget, realized-vol percentile) create the missing accuracy? | `btc60_regime_signal_report.md` |
| 4 | `btc60_payoff_map.py` | what payoff shape monetizes the surviving edge? (±100/100, +100/−50, +80/−40, +150/−75, forward-drift) | `btc60_payoff_map.md` |
| 5 | `btc60_timebox_study.py` | WHEN does the committee work? per-hour rhythm + 3h-box accuracy + good-box gate fold check | `btc60_timebox_report.md` |
| 6 | `btc60_coinbase_validation.py` | does everything replicate on COINBASE candles (the bot's runtime source, real volume)? | `btc60_coinbase_validation.md` |

Signal universe tested: engine signals (liquidity_sweep, vidya_dmi,
adx_di_cross, scalp_bias, mechanical_trigger, vp_premium,
confluence_star), filters (delta, cumdelta, near_level, momentum,
ADX 15-42.5, DI dominance, POC side, net-30), and new BTC-specific
signals built for this program: **AFML CUSUM (k=1.0/1.5/2.0/2.5),
Bollinger squeeze-break, 1h Donchian break, volume burst, range burst,
3-bar momentum ($40/60/90), 6-bar momentum ($120), VWAP cross, POC
cross**, regime gates (ATR-6 sum, realized-vol percentile p50/p65/p80).

### Headline numbers every future reader must know

* Unconditional baseline (any bar): first-touch ±$100/30min ≈ **50%**;
  reach ≈ **47-48%**.  Any signal must beat these, out of sample.
* Phase-1 "100% accuracy" combos (12 days) → 48-64% over 46 days.
  **Small-n accuracy is regime luck, not edge.**
* Volatility gate rv≥p80 lifts *reach* to 62-74% (contracts WILL
  reprice) but first-touch stays ~44-50% — vol makes moves bigger,
  not more predictable.
* Tight stops destroy the edge: +100/−50 first-touch ≈ 36-40% (below
  the 36% breakeven of a 35c contract).  Winners need symmetric room.

## 4. The validated committee (the signal)

Five members, each ≥54% first-touch ±$100/30min over 46 days with
positive worst-week behavior, plus one high-conviction overlay:

| # | Member | Dir | 46-day ft-acc | n | /day | Notes (tuned values) |
|---|---|---|---|---|---|---|
| S1 | `squeeze_break + di_dom` | SHORT | **64.1%** | 78 | 2.0 | BB(20,2) width < 20th pctile of 24h AND close < lower band AND −DI > +DI |
| S2 | `poc_cross + adx>30` | LONG | **62.9%** | 35 | 0.8 | close crosses volume-profile POC upward, ADX(14) > 30 — mean fwd-30min **+$117** |
| S3 | `adx_di_cross + momentum (+adx>20)` | LONG | 58.7% | 46 | 1.2 | +DI crosses 20 w/ DI dominance, EMA6>EMA17 & close>EMA6; ADX>20 |
| S4 | `mom3_60 + poc_cross (+near_lvl)` | SHORT | 58.0% | 69 | 1.7 | 3-bar net ≤ −$60 AND POC cross down; near-resistance strengthens it |
| S5 | `poc_cross + adx>27.5` | SHORT | 55-64% (window-dep.) | 47 | 1.0 | mirror of S2; ADX threshold tuned 27.5 |
| O1 | S2 with ADX>32.5 | LONG | 64% @ n=25 | — | 0.6 | size-up overlay: highest conviction LONG |

ADX tuning result: LONG poc_cross peaks at ADX>30-32.5; SHORT at
27.5-30; adx_di_cross prefers threshold 20 with DI dominance ON.
CUSUM k=1.5 helps vidya_dmi in trending weeks but failed w4-w5 chop —
vidya_dmi+cusum is **excluded** from v1 (23.7% on asymmetric barriers,
worst fold 0/8).

**Regime gate (tradability, not direction): rv_1h ≥ p50** rolling
3-day percentile — filters the dead chop where even correct calls
can't reach ±$100 (reach jumps from 48% → 55-62%).  At p80 gating
becomes too tight for frequency; p50 is the balance.

**Committee behavior**: members are OR-ed per direction; opposite-
direction simultaneous fires cancel; one position at a time.  Expected
de-duplicated tradeable fires: **4-6/day**.

### 4b. Timebox gate (phase-5, `btc60_timebox_study.py`)

Committee accuracy is strongly time-of-day dependent (46-day study,
3h UTC boxes, pooled across members):

| UTC box | n | acc | verdict |
|---|---|---|---|
| 00-03 | 39 | 46.2% | **BAD** — Asia open whipsaw |
| 03-06 | 43 | 58.1% | good |
| 06-09 | 54 | 63.0% | good |
| 09-12 | 51 | 54.9% | good (borderline) — lowest 30-min ranges of the day (~$195) |
| 12-15 | 62 | 59.7% | good — biggest ranges (US morning, $263-413) |
| 15-18 | 29 | 44.8% | **BAD** — US midday chop/reversal zone |
| 18-21 | 35 | 65.7% | good |
| 21-24 | 30 | 60.0% | good |

Trading **good boxes only** (UTC 03-15, 18-24): accuracy 57.1% → **61.2%**
(Wilson LB 54.6%), still 5.6 fires/day, EV/50c contract +4.4c → **+5.8c**
(+32%/trade).  The bad boxes pooled at 49.6% (coin flip, EV ≈ fees) and
produced the catastrophic weeks (w3: 1/10).  Fold check: the good-box gate
is positive in **all 7 weeks** (worst 54%).

**Rule: the bot only enters during UTC 03:00-15:00 and 18:00-24:00.**
(00-03 and 15-18 UTC are no-trade windows; positions opened before a
boundary still run their normal 30-min clock.)  The weekly learner
re-scores boxes and may flip a borderline box (09-12) off if its
trailing accuracy drops under 52%.

### 4c. Coinbase-candle validation (phase-6) — FINAL committee

Phases 1-5 ran on yfinance BTC-USD.  The bot's runtime source is
Coinbase, whose tape differs (and yfinance carries NO volume, so its
"POC" was effectively a time-profile).  Rerunning everything on 46 days
of paged Coinbase 5m candles:

| Member | yfinance | Coinbase | verdict |
|---|---|---|---|
| S1 `sqz_break+di_dom` SHORT | 64.1% | **62.4%** (n=85) | ROBUST — keep |
| S2 `poc_cross+adx30` LONG | 62.9% | 56.5% (n=46) | keep (weaker but +EV) |
| S3 `adx_di_cross+mom+adx20` LONG | 58.7% | 55.0% (n=80) | keep |
| S4 `mom3_60+poc_cross` SHORT | 58.0% | **49.3%** (n=152) | **CUT** — volume-POC sensitive |
| S5 `poc_cross+adx27.5` SHORT | 55-64% | **48.2%** (n=56) | **CUT** — same reason |

**Final committee = S1+S2+S3.**  On Coinbase, all-hours: 58.3%
(LB 51.6%), 5.1 fires/day, EV +4.8c/50c.  Inside Coinbase-native good
boxes (UTC 00-09, 12-15, 18-21): **63.7% (Wilson LB 55.6%), EV +6.8c
per 50c contract**, n=146.

Timebox agreement across both tapes: **15-18 UTC is toxic on both**
(44.8% / 35.0%) — permanent exclusion.  06-09 and 12-15 are the two
best boxes on both tapes (63-71%).  00-03 and 21-24 flip between
tapes — start them ENABLED (Coinbase is the tape that matters) but
under weekly learner review; 09-12 (50.0% on Coinbase, the day's
lowest-volume hours) starts DISABLED.

SHORT-side note: with S4/S5 cut, S1 is the only SHORT member — the
committee leans LONG 2:1.  The monthly re-research must hunt for a
second robust SHORT (order-book imbalance is the prime candidate).

## 5. Kalshi execution mapping (the money printer)

The signal predicts ±$100 in 30 min.  On KXBTCD hourly markets a $100
spot move near the strike reprices a near-the-money contract by roughly
20-35c.  Execution rules:

1. **When** a committee member fires (and regime gate passes, and
   minute-of-hour ≤ 25 so the time-stop fits inside the hour):
2. **Instrument**: the strike **nearest to spot** (ATM).  Buy YES if
   LONG, NO if SHORT — but ONLY at **40-60c** (near-money).  Never pay
   >60c (that's the old favorite-overpay failure), never buy <40c
   lottery tickets.
3. **Entry**: maker limit at the bid; cancel if unfilled in 3 minutes
   (the burst is perishable — a late fill is a different trade).
4. **Exit — take profit**: resting maker sell at entry + 20c
   (≈ the $100-move repricing).
5. **Exit — stop**: taker sell if bid ≤ entry − 15c.
6. **Exit — time-stop**: 30 min after entry, flatten at bid whatever
   the P&L (the signal's horizon has expired; holding = gambling).
7. **Hard flatten** ≥ 5 min before market close (unchanged from fable5;
   settlement killed the live account).
8. One position at a time; adopt any orphan position on the event
   (keep fable5's adoption guard, cancel-all V2 path, single-instance
   lock, PID watchdog).

### EV arithmetic (per 50c contract, committee at 61% inside good boxes)

```
win  : +20c (maker exit, no taker fee)
loss : −15c − ~1.5c taker fee ≈ −16.5c
time : ≈ −2c average (small negative drift when stopped flat)
EV/trade ≈ 0.61(+20) − 0.29(−16.5) − 0.10(−2)  ≈ +7.2c  ≈ +14% of a 50c stake
```
Breakeven WR at this shape ≈ **45%** — a 16-point cushion under the
good-box committee's 61.2% (measured, Wilson LB 54.6%), vs the old
bot's NEGATIVE 12-point deficit.  At ~5.6 fires/day (≈4 tradeable after
one-position-at-a-time) × 6% bankroll × +14% ≈ **+3.4%/day expectancy**,
with materially lower variance than all-hours trading (the excluded
boxes were a 49.6% coin flip whose worst week ran 1/10).

## 6. Adaptive accuracy maximization (the honest 99% answer)

A static 99%-accuracy signal at useful frequency **does not exist** on
this tape — 3,586 combos, 6 windows, 46 days, weekly folds, Wilson
bounds all say so.  What the bot does instead:

* **Weekly re-fit** (`learner v2`): every Sunday (or every 40 trades)
  recompute each member's trailing-21-day first-touch accuracy from the
  bot's own trade log + a fresh 5m backtest (phase-2 script is imported,
  not duplicated).  Weight = max(0, acc − 50%)²; member disabled below
  52%, re-enabled at 55%.  Size multiplier ∝ committee weight of the
  firing member (S2/O1 highest).
* **Fast brake** (kept from fable5): 3 losses in last 5 trades →
  halve size until the next 3-win run.
* **Regime monitor**: if rv_1h < p50 for 6+ hours, the bot idles (logs
  `REGIME-IDLE`) — no trades in dead tape, the old bot's silent bleed.
* **Monthly re-research**: rerun phase 1-4 scripts; if a new combo
  beats an incumbent's Wilson lower bound by ≥5 points over 46 days,
  promote it to the committee.  The committee is a living object.

## 7. Risk framework

| Control | Value | Source |
|---|---|---|
| Bankroll ledger | separate from account; seeded $100 | fable5 (kept) |
| Size/trade | 6% of ledger × member weight (cap 10%) | Kelly/4 at measured edge |
| Max trades/hour | 3 | churn breaker |
| Max daily loss | −10% of ledger → halt to next UTC day | new |
| Min ledger | $25 halt | fable5 (kept) |
| Single instance | PID lock file | fable5 (kept, it caught a real incident) |
| Crash recovery | watchdog ps1 relaunch | fable5 (kept) |
| Paper/live split | separate state+CSV suffixes | fable5 (kept) |

## 8. Bot architecture (new file: `bot_kalshi_btc60_burst.py`)

```
kalshi/btc/                       (self-contained, per 2026-07-08 refactor)
├── btc/                          local signal package (monitor, liquidity_sr, cb_btc_signal)
├── btc.env                       customer_folder / default_customer (secrets pointer)
└── btc60/
    ├── bot_kalshi_btc60_burst.py   ← the new bot (to build)
    │     SignalEngine   : 5m candle poll (Coinbase, closed bars) → committee members
    │     RegimeGate     : rv_1h percentile from rolling 3-day window
    │     TimeboxGate    : no entries UTC 00-03 / 15-18 (learner can re-score)
    │     Trader         : strike selection, maker entry, TP/SL/time-stop
    │     LearnerV2      : member weights, fast brake, ledger
    │     (KalshiClient, locks, watchdog, flatten logic lifted from fable5)
    ├── backtest_signals_btc60.py     phase-1 harness (rerunnable)
    ├── btc60_validate_ensemble.py    phase-2 folds + sweeps
    ├── btc60_regime_signal.py        phase-3 regime study
    ├── btc60_payoff_map.py           phase-4 payoff mapping
    ├── btc60_signal_backtest_report.md / .csv
    ├── btc60_ensemble_validation.md
    ├── btc60_regime_signal_report.md
    ├── btc60_payoff_map.md
    └── btc60_bot_trsategy.md         ← this document
```

Committee evaluation runs on **closed 5-minute Coinbase candles** —
validated end-to-end on this exact source in phase 6 (paged public
candles endpoint, 350 bars/request; the fetcher in
`btc60_coinbase_validation.py::fetch_all` is the reference
implementation to lift into the bot).  Engine indicators (ADX/DMI,
EMA, BB, volume-profile POC) are computed locally from the candle
buffer; no yfinance dependency at runtime.

## 8b. As-built notes (2026-07-10, owner's live-money spec)

`bot_kalshi_btc60_burst.py` is IMPLEMENTED with these owner-requested
deltas from the research defaults above:

* **1-hour timeboxes** (not 3h): entries allowed only in UTC hours whose
  pooled committee accuracy ≥ **54%** over the trailing 46 days; hours
  with n < 8 inherit their 3-hour parent's verdict.  Current table:
  `btc60_burst_revalidation.md`; machine copy `btc60_burst_config.json`.
* **48-hour auto-revalidation**: the bot refetches 46d of Coinbase 5m
  candles every 48h in-process, re-scores every member and every 1h box
  with the same ≥54% rule, and hot-reloads the config.  Also runnable
  standalone: `python bot_kalshi_btc60_burst.py revalidate` (or
  `btc60_burst_launch.bat revalidate`).  First run (2026-07-11) DISABLED
  member S3 at 48.1% — the gate works.
* **Bankroll (real money)**: seeded **$100** on first launch; max **25%
  of current bankroll per trade** (owner's spec; research suggested 6% —
  aggressive sizing accepted by owner).  Daily reset at **08:00
  America/Chicago**: profit day → bankroll = day_start + 50% of profit,
  other 50% "banked" (never risked again); loss day → carries unchanged.
  State: `btc60_burst_state.json` (`_paper` suffix in DRY_RUN).
* **Launcher**: `btc60_burst_launch.bat` — console (live) logs + mirror
  to `btc60_burst_YYYYMMDD.log`; `paper` arg for simulation,
  `revalidate` arg for a config refresh; default is **LIVE**.

## 9. Deployment plan

1. **Build** `bot_kalshi_btc60_burst.py` (reuse fable5 plumbing: client,
   locks, paper book, flatten, CSV/state).
2. **Paper** ≥ 100 trades (~3 weeks).  Promotion gates:
   WR ≥ 52% at the +20/−15/time payoff, expectancy ≥ +3c/contract,
   no control failures (locks, flatten, adoption).
3. **Live** at $100 ledger, 6% sizing.  Scale ledger only after a
   full profitable month.
4. Keep fable5 paper instance running in parallel for A/B comparison
   until burst has 200 trades.

## 10. Known limitations & future research

* 46 days is one macro regime (BTC $60-65k, mid-2026 vol).  The monthly
  re-research loop is not optional.
* Kalshi order-book depth at ATM strikes limits size; above ~$500/trade
  the maker-entry assumption degrades — revisit before scaling.
* Candidate upgrades: order-book imbalance from Kalshi's own book
  (bid/ask depth ratio predicted repricing in the perp bot's data),
  funding-rate skew, and a cross-exchange lead-lag (Binance leads
  Coinbase by seconds in bursts — worth a dedicated study).
* The ±$100/30min target is a proxy.  The real object is contract
  repricing; a future phase should backtest on recorded Kalshi bid
  ticks (the bot logs them — `kbtc-60.log` format) once ≥30 days of
  tick history accumulates again.
