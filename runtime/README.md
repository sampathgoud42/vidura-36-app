# runtime/ — the vendored trading runtime

Everything this project **executes** lives here: the signal engines the
Tradier desk reads, the level watcher its auto-trader follows, and every
Kalshi bot script the Bot Station launches. `settings.source_repo` defaults
to this folder (`backend/app/core/config.py`), and nothing is read from the
checkouts this project was extracted from.

```
runtime/
├── prediction-trade/           the Bot Station's bots
│   ├── kalshi/
│   │   ├── btc/                btc.env · btc/ (monitor, liquidity_sr,
│   │   │   │                   cb_btc_signal) · monitor_bot.py
│   │   │   ├── btc15/          v2 v3 v4 v5 engines
│   │   │   └── btc60/          fable5 · burst
│   │   ├── sports/             bot_kalshi_main · v1 · v2 · bot_kalshi_parley
│   │   │                       kalshi_sports · sport_adapters/
│   │   │                       kaslhi_sports.env  (the misspelling is
│   │   │                       load-bearing — the bots look for that name)
│   │   └── commodities/        gold15/ · silver15/ · oil15/  (v1 + v2)
│   └── sports/                 the models the sports bots import
│       ├── tennis/             predict_v1..v6 · live score · rankings
│       └── baseball/           sabermetric model + scraper
├── indicators/                 imported as `btc` by the sports bots (NOT the
│                               same package as kalshi/btc/btc — both are
│                               required). Also holds commodity_dmi.py, which
│                               the station's live gold/silver/oil readout
│                               imports directly.
├── stock-trade/                levels_watcher.py + its state and crossings
│                               CSV — the opening-range auto-trader's input
├── super_research/             super_signal_bot · engine_common ·
│                               <ticker>_research/ · super_research.config ·
│                               a/b_signals.csv · archive/ · gex/ ·
│                               gex_daily.json · econ_today.json
├── NIFTY_research/             India workers — MUST stay siblings of
└── BANKNIFTY_research/         super_research (their sys.path hack is
                                HERE.parent/"super_research")
```

## Layout rules — these are not cosmetic

The scripts resolve everything from `__file__`, so the directory depths
above are part of the contract:

- `sport_adapters/generic.py` walks `parents[3]/"sports"`;
- the sports bots walk `parents[2]` for the project root and alias
  `sys.modules["btc"] = indicators`;
- the btc15 bots insert `.../kalshi/btc` on `sys.path` to import `btc`;
- `bot_launcher.py` scans ancestors for `btc/btc15` to alias the renamed
  module `bot_kalshi_btc15` → `v4_bot_kalshi_btc15.py`;
- `commodity_signals.py` inserts `indicators/` on `sys.path` to import
  `commodity_dmi`;
- the India workers insert `HERE.parent/"super_research"`.

Flattening or re-nesting any of it breaks imports at bot start.
`tools/paper_smoke_bots.py --all-versions` is what catches that: it starts
every registered engine for real, in paper, and an import error shows up as
"exited early" with the traceback in the tail.

## Local edits made during vendoring

- `v5_bot_btc_15_2.py` — the two absolute defaults pointing at the old
  checkout's `indicators/` now resolve from `__file__`.
- `indicators/btc15_quarter.bat` — `cd /d <old repo>` → `cd /d "%~dp0"`, and
  the hardcoded interpreter path → `python`.
- The sports family's order cancels moved from the deprecated V1 path
  `DELETE /portfolio/orders/{id}` (Kalshi answers HTTP 410) to the V2
  `DELETE /portfolio/events/orders/{id}` the BTC bots already used. The bots
  swallow cancel failures, so this was silent: an unfilled order rested
  forever, holding capital and skewing position checks. Guarded by
  `tests/test_kalshi_v2_endpoints.py`.
- `kaslhi_sports.env` — `TARGET_PORTFOLIO_PCT` 50 → 0. The Kalshi account is
  shared by every bot, so a target on its JOINT value let one bot's run stop
  the others (user rule 07/30). Risk is per bot, on its own bankroll. The
  API already forced this at launch; the file now agrees with it, so a
  hand-launched bot behaves the same way. Guarded by
  `tests/test_no_portfolio_halt.py`.
- Every doc path naming another checkout was repointed at this project.
  `tools/check_self_contained.py` fails if one comes back.

## Not copied (and why)

`__pycache__/` (a stale `.pyc` for the renamed module would shadow the
launcher's alias), per-ticker `cache/` (bar caches, regenerate on demand),
`results/all_configs.csv` (~80 MB of backtest sweeps; only
`engine_scores.json` is read at runtime), and `top100_research/` (retired).

`*.lock` files, bot session state, ledger CSVs and the scraped tennis
rankings are gitignored: a copied PID lock makes a bot refuse to start, and
the rest is one machine's history. Every one of them is recreated on the
next run.

## Secrets

`super_research/flashalpha.env` holds a live API key and
`kalshi/sports/kaslhi_sports_secrets.env` holds Kalshi credentials — both
are **gitignored**. On a fresh clone, recreate them (or set
`TBOT_FLASHALPHA_API_KEY`). Per-operator Kalshi and Tradier credentials are
*not* here at all: they stay in `customers/<username>/` under
`TBOT_CUSTOMERS_ROOT`.

The two non-secret bot configs — `kalshi/sports/kaslhi_sports.env` and
`kalshi/btc/btc.env` — are deliberately un-ignored and DO ship, because a
fresh clone has no sport list, no entry band and no series without them.
Never put a key in either one.
