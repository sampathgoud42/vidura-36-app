# btc-15 — quarter-hour breakout signal → dashboard → Kalshi bot

End-to-end flow built 07/24/2026. One pipeline, three consumers: a CSV signal
feed, an interactive dashboard, and a live Kalshi order bot.

```
Coinbase 1m candles (public API, paginated 300/req, 429-retry)
        │
        ▼
btc15_signal.py  ──►  btc15_signal_report_w2.csv  (+ hourly aggregate)
   ±2m engine          btc15_signal_report.csv    (legacy name = same data)
        │                        │
        │ every :02/:17/:32/:47  │
        │ (btc15_quarter.bat     ├──► bake_btc15_dashboard.py ──► btc15_dashboard.html
        │  via schtask + bot)    │         (also published as a claude.ai artifact)
        │                        │
        ▼                        └──► bot_btc_15_2.py  (Kalshi KXBTC15M orders)
```

---

## 1. The signal

For every quarter-hour mark **T** (`:00 :15 :30 :45`, all times **America/Chicago**):

| Field | Meaning |
|---|---|
| `created_on` | timestamp (CT, with seconds) when the row was FIRST inserted — preserved across upserts, so pending→resolved keeps its birth time; pre-migration rows are backfilled with their mark time |
| `minus_min / minus_max` | low/high of the **2 minutes before** T (`[T-2m, T)`) |
| `plus_min / plus_max`   | low/high of the **2 minutes after** T (`[T, T+2m)`) |
| `best_move` | larger-magnitude of `plus_max − minus_min` (LONG, +) vs `plus_min − minus_max` (SHORT, −) |
| `direction` | `LONG` / `SHORT` from the winning side above |
| `btc_current15` | close of the 1m candle **ending at** T (price at HH:MM:00) |
| `btc_next15` | same read at T+15m (empty while pending) |
| `is_matched` | `TRUE` when `btc_next15` moved in `direction` vs `btc_current15`; `FALSE` otherwise; `NA` while pending |
| `momentum` | did THIS window's drift confirm the **previous** record's direction? `NA` when no adjacent prev record or pending |

**Pending rows:** the row for mark T is inserted as soon as its ±2m windows
complete (~T+2m50s) with `is_matched=NA` / empty `btc_next15`; it resolves
automatically on the first refresh after T+15. This is what lets the bot act
on `direction` minutes before the outcome exists.

**Pre-mark momentum report (`btc15_pre3_report.csv`):** a second CSV built on
the same refresh cycle from the LAST 3 one-minute candles before each mark —
columns `minus3_min/max`, `minus2_min/max`, `minus1_min/max` (candles T−3,
T−2, T−1), `best_move` = the largest chronological two-candle move (up =
`later_max − earlier_min`, down = `later_min − earlier_max`, over pairs
m3→m2, m3→m1, m2→m1; larger magnitude wins), `direction`, `btc_current15`.
All three candles close AT T, so this signal is fully decision-time at the
mark itself — usable the moment a market opens, unlike the main ±2m signal
(ready ~T+3). Same upsert/retention behavior; 30d backfilled 07/24.

**Engines:** the window width is parameterized. Current default is one engine,
`--engines "2"` (±2m). Syntax: `"2,3,5"` (symmetric ±W) or `"5:1"`
(asymmetric minus-5/plus-1, key `custom51`). With multiple engines, each gets
`btc15_signal_report_{key}.csv`, and the **best by overall is_matched %**
also lands in the legacy filenames. (Earlier sweeps: ±1..±5 + custom51/52 were
built and compared, then trimmed to ±2m on request.)

## 2. Refresh cadence

- **Scheduled task `btc15_signal_q15`** → runs `btc15_quarter.bat` at
  **:02 / :17 / :32 / :47** — now a fast **past-1-hour** fetch (1 API request;
  the signal script adds a 20-minute context pad).
- **`btc15_quarter.bat [HOURS]`** — optional lookback arg in hours (default 1).
  Sleeps 30s first so the just-closed candle is queryable, then runs the signal
  script and the dashboard bake. Appends to `btc15_quarter.log`.
  Full backfill when needed: `python btc15_signal.py --days 30`.
- **The bot** calls `btc15_quarter.bat 1` (same past-hour refresh) on the same
  minute grid, so its signal row is ready fast.
- ⚠️ With hourly-lookback refreshes, an outage longer than ~1h leaves a
  permanent gap in the CSV until a manual `--days N` backfill is run.
- **Writes are UPSERTS, never overwrites** — each run replaces/inserts only the
  `(date, 15minute)` keys inside its fetched window; all other history is
  preserved, sorted, and trimmed to `--keep-days` (default **90**). Pending
  rows resolve in place; short-window refreshes cannot wipe the file, and
  history accumulates toward 90 days over time.

## 3. Dashboard (`btc15_dashboard.html`)

Rebaked every refresh from the engine CSVs by `bake_btc15_dashboard.py`
(template: `btc15_dashboard_template.html` — data is baked in, fully offline).
Published snapshot: https://claude.ai/code/artifact/315aa523-cbc6-49d3-b900-fd4944d4437e
(the artifact does NOT auto-update — ask Claude to republish).

- Filters: engine · **expansion ratio** (`|best_move| ÷ pre-range width`; chips show each threshold's overall match %, ★ = smallest threshold reaching **≥70%**, selected by default — currently ≥2.5 at 70.6% on ±2m) · **min |move|** (points-magnitude filter; sub-25pt signals win only ~54% — chop; chips show standalone win %, ★ = best with n≥300, default All; **stacks with ratio**: |move|≥75 & ratio≥2.0 → 73.4% @ ~16/day) · quarter mark (default **:15**) · weekday/weekend · 7/14/30d — everything recomputes
- KPI row: samples, avg/median/p90 |move|, LONG share, **next-15 match**, **match ex-FF**, **match ex-FF2**, momentum, best hour
- "Average move by hour": LONG-day vs SHORT-day arms + direction-share strip
- "Match ex-FF2 by hour": one bar per hour with its % labeled, growing from the 50% line
- Heatmap (every day × hour, signed move) and per-day spread plot
- Hour card: full stats for the selected hour; the **current CT hour is pre-selected on launch**
- Pending rows show as PENDING/`…`/`NA`; all match denominators use resolved rows only

**ex-FF / ex-FF2 are decision-time filters** (redefined 07/24, second pass):
the current row's outcome is treated as unknown at the mark, and the filter
skips the whole row — win or loss — based only on the previous record:
`ex-FF` skips rows whose prev `is_matched` = FALSE; `ex-FF2` skips rows whose
prev `momentum` = FALSE (`NA` never blocks). These are executable rules; on
30d of ±2m data they keep ~58/day at 61.0% and ~48/day at 60.8% respectively,
vs 60.2% baseline — honest, and honestly small.

## 4. The bot (`prediction-trade/kalshi/btc/btc15/bot_btc_15_2.py`)

Kalshi client + V2 order mapping reused from `v4_bot_kalshi_btc15.py`.

Flow per market: new open `KXBTC15M` market → mark **T = close_time − 15min**
→ **pre-signal price feed from market open**: a parallel task prints the ask
for the PREVIOUS record's side (`(prev-side, pre-signal)` tag, print-only —
no orders) until the real signal lands → at T+2:00 kick the past-hour refresh
(its 30s candle-grace lands the fetch at ~T+2:30) → **first CSV check at T+2:30** (`BOT152_SIGNAL_CHECK_SEC`): print
the signal if available, else poll every 2s (`BOT152_SIGNAL_POLL_SEC`) until
the CSV updates, bounded only by the entry deadline → **no signal filter
beyond direction** (prev-record flags are still logged per trade) →
**freshness gate**: the
row's `created_on` must fall inside this market's 15-min window (stale signals
skipped) → **dynamic band**: if the side's initial ask is already **>60¢**
(`BOT152_WIDE_TRIGGER_CENTS`) the band widens to **35–55¢**
(`BOT152_WIDE_MAX_CENTS`) to catch a pullback; otherwise standard **35–45¢**
(`BOT152_MIN_CENTS`/`BOT152_MAX_CENTS`) → **async band watcher**: poll the
side's live ask every ~1s (`BOT152_BAND_POLL_SEC`) and buy the INSTANT it is
inside the band (limit at band max), any time up to **market minute 12** —
no orders in the last 3 minutes even if in range (`BOT152_CLOSE_BUFFER_SEC`
= 180); never in band → skip →
`LONG` → buy YES, `SHORT` → buy NO (×`BOT152_CONTRACTS`, GTC, taker-at-cross)
→ **take-profit leg**: at market minute 10 (mark+10m) the bot **double-confirms
the open position via the positions API** (two reads ~2s apart — the sell
quantity is always the latest API value, covering partial fills; side change or
vanished position aborts the sell) and, if held, rests a **sell at 90¢** for
the exact held side/quantity (`BOT152_TP_CENTS`/`BOT152_TP_AT_MIN`).
**No stop-loss** — anything unsold rides to settlement.

30-day backtest of that exact entry rule on the ±2m engine: 854 of 2,878 marks
traded (~28/day), win 61.8% vs 60.1% baseline — the tradable filter is a small
edge, far below the retrospective ex-FF2 metric (~84%), which by construction
only removes losers it already knows about.

Run it **from your customer folder** (that's where `.env` + `kalshi_private.pem`
resolve, and where the trade log/state land):

```cmd
cd D:\_projects\vidura-36-app\customers\suma
python D:\_projects\vidura-36-app\runtime\prediction-trade\kalshi\btc\btc15\bot_btc_15_2.py >> bot_btc_15_2.out 2>&1
```

The bot loads `.env` from the **current directory first** (then falls back to
the repo walk-up .env for anything missing) — so the launch folder decides the
account. The startup banner prints the key-id tail + resolved pem path;
verify it before leaving it running. Currently configured account: **suma**
(`customers/suma/.env`: `BOT152_DRY_RUN=FALSE`, `BOT152_CONTRACTS=10`).

| Env var | Default | Meaning |
|---|---|---|
| `BOT152_DRY_RUN` | `TRUE` | paper mode — logs orders without sending (independent of v4's `DRY_RUN_MODE`) |
| `BOT152_CONTRACTS` | `1` | contracts per trade |
| `BOT152_MIN_CENTS` / `BOT152_MAX_CENTS` | `35` / `45` | strict entry band — buy only while the side's ask is inside it |
| `BOT152_TP_CENTS` / `BOT152_TP_AT_MIN` | `90` / `10` | take-profit sell price and the market minute it is placed |
| `BTC15_SIGNAL_CSV` / `BTC15_QUARTER_BAT` | indicators paths | override signal feed / refresh script |
| `KALSHI_API_KEY_ID` / `KALSHI_PRIVATE_KEY` / `BASE_URI` | — | same auth as v4 |

Files written (per customer): `bot_btc_15_2_trades.csv` (every order:
mark, direction, best_move, order id), `bot_btc_15_2_state.json` (traded
markets — restart-safe dedupe), `bot_btc_15_2.out` (log, if redirected).

## 5. What the 30-day research says

- ±2m engine baseline: **~60% is_matched**; wider windows score higher but
  partly by construction (their plus window overlaps the grading path)
- **Momentum ≈ 48.5%** — the previous mark's direction does NOT carry; the
  market slightly mean-reverts at this scale. Skip rules built on previous-row
  flags add nothing (verified: ~coin-flip conditionals)
- The one **tradable** filter that moves the needle: **expansion ratio
  `|best_move| ÷ (minus_max − minus_min)`** — ≥2 → ~74-79% match, ≥2.5 → ~84%
  (holdout-validated); stacks with against-drift and one-sided-break
- Buying at a 99¢ limit fills at the ask — compare `bot_btc_15_2_trades.csv`
  entry prices against settlements before scaling size

## 6. Ops quick reference

```cmd
:: manual full refresh + rebake (30d)
D:\_projects\vidura-36-app\runtime\indicators\btc15_quarter.bat

:: manual fast refresh (past 24h only)
D:\_projects\vidura-36-app\runtime\indicators\btc15_quarter.bat 1

:: rebake dashboard only (no fetch)
python D:\_projects\vidura-36-app\runtime\indicators\bake_btc15_dashboard.py

:: scheduled task status / run now / delete
schtasks /Query /TN btc15_signal_q15 /FO LIST
schtasks /Run   /TN btc15_signal_q15
schtasks /Delete /TN btc15_signal_q15 /F

:: is the bot running?
powershell "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | ? { $_.CommandLine -like '*bot_btc_15_2*' } | select ProcessId,CreationDate"

:: logs
type D:\_projects\vidura-36-app\runtime\indicators\btc15_quarter.log
type D:\_projects\vidura-36-app\customers\sampath\bot_btc_15_2.out
```
