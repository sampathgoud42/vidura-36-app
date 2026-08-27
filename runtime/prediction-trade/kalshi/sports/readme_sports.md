# Kalshi Sports — `kalshi_sports_v1.py`

Async, strongly-typed helpers to discover and filter **Kalshi sports markets**
over the current **Trade API v2** (read-only `GET` endpoints), and to pull
per-match stats for buy decisions.

> Auth/HTTP reuse the v1 `KalshiClient` (RSA-PSS signed requests). Only reads
> are performed — this module never places or cancels orders.

```bash
cd kalshi/
python kalshi_sports.py        # runs the built-in demo
```

---

## Running the trading bot (`bot_kalshi_sports_v1.py`)

The bot itself lives entirely under this repo — it never imports code from
anywhere else. Only its **credentials, logs, and trade-history CSV** live
outside the repo, in a per-customer folder:

```
D:\_projects\tradier-bot\customers\<customer>\
├── .env                  # KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY, BASE_URI
├── <name>.pem            # private key (KALSHI_PRIVATE_KEY may be just the filename)
├── logs\                 # kalshi_sports_YYYYMMDD.log (+ archive\ for prior days)
└── trade_history\
    └── trade_history_sports.csv
```

The customer is selected by (first match wins): the 1st CLI arg, the
`SPORTS_CUSTOMER` env var, else `"suma"`. The customers root defaults to
`D:\_projects\tradier-bot\customers` (override with `SPORTS_CUSTOMERS_DIR`).

```bash
cd kalshi/sports/
python bot_kalshi_sports_v1.py            # customer "suma" (default)
python bot_kalshi_sports_v1.py acme       # customer "acme" (D:\_projects\tradier-bot\customers\acme\)
SPORTS_CUSTOMER=acme python bot_kalshi_sports_v1.py
```

Non-secret bot config (`SPORTS_LIST`, `MIN_VOLUME_USD`, `SPORT_*` knobs, …)
still comes from `kaslhi_sports.env` in this folder (tracked in git) —
that part is shared across all customers. `SPORT_LOG_DIR` and
`SPORT_TRADE_CSV` env vars override the customer-folder defaults above if
ever needed for a one-off run.

## How Kalshi models sports (verified live)

- **Series** carry the taxonomy: the **sport** is in `tags` (e.g. `["Soccer"]`)
  and the **league/tournament** is the series `title` (e.g. `"English Premier
  League"`). Sports series have `category == "Sports"`.
- **Markets**: tradeable state is `status == "active"`; prices are dollar strings
  (`yes_bid_dollars` …); volume is a fixed-point **contract** count (`volume_fp`).
- **USD volume is estimated** as `volume_fp × last_price_dollars` — Kalshi reports
  contract volume, not dollar volume.
- **live vs scheduled** is *derived* (Kalshi has no native flag) from
  `occurrence_datetime` / `expected_expiration_time`:
  - `scheduled` — unopened, or active and the event hasn't started (`now < occurrence`), or an outright (no occurrence time).
  - `live` — active and the event has started (`occurrence ≤ now < expiry`).
  - `settled` — closed/settled, or past expiration.
- **Live scoreboard** is available for *game* sports via the milestone/live-data
  route — `GET /milestones?related_event_ticker=…` → `GET
  /live_data/milestone/{id}/game_stats` returns play-by-play (`pbp`). Supported:
  Pro/College Football, Pro/College/WNBA Basketball, Soccer, Pro Hockey, Pro
  Baseball. Other sports (e.g. **Tennis**) have a milestone but no `pbp`. See
  `get_game_stats(ticker, sport)` in `bot_kalshi_sports_v1.py`. For sports
  without play-by-play, `get_the_market_scores_kalshi()` still gives the
  market's **implied probabilities** (+ an optional `_external_scores` feed).

---

## Available sports

Live tags under `category == "Sports"` (via `await list_sports()`):

`Aussie Rules`, `Baseball`, `Basketball`, `Boxing`, `Chess`, `Cricket`, `Darts`,
`Esports`, `Football`, `Golf`, `Hockey`, `Lacrosse`, `MMA`, `Motorsport`,
`Olympics`, `Rowing`, `Rugby`, `Soccer`, `Squash`, `Table Tennis`, `Tennis`,
`UFC`, `Video games`

Catch-all buckets also appear: `Other`, `Cities`. The taxonomy is fetched live,
so this list updates automatically — call `list_sports()` for the current set.

Leagues are the series `title` (e.g. `"English Premier League"`, `"ATP Grand
Slam"`, `"NBA Game Winner"`, `"WTA Miami"`). Pass any substring to
`filter_by_league`.

---

## Functions

All filters are **async** and **chainable**: pass `markets=<prev result>` to
filter an in-memory list (no I/O), or omit it to fetch live data first.

### 1. `live_or_scheduled(status, markets=None)`
Filter to markets whose derived state is `"live"` or `"scheduled"`.
```python
live = await live_or_scheduled("live", markets=await fetch_sports_markets(sport="Soccer"))
```

### 2. `filter_by_sport(sport_name, markets=None)`
Filter by sport category (series tag).
```python
tennis = await filter_by_sport("Tennis")
```

### 3. `filter_by_league(league_name, markets=None)`
Filter by league/tournament (series-title substring, case-insensitive).
```python
epl = await filter_by_league("English Premier League")
```

### 4. `filter_by_min_volume(min_usd, markets=None)`
Keep markets with estimated USD volume ≥ `min_usd`.
```python
liquid = await filter_by_min_volume(5000, markets=await filter_by_sport("Soccer"))
```

### 5. `filter_by_sport_league_min_volume(sport_name, league_name, min_usd)`
One-shot fetch + combined filter → `list[SportsMarket]`.
```python
picks = await filter_by_sport_league_min_volume("Soccer", "English Premier League", 1000)
```

### 6. `filter_live_matches(list_of_markets)`
From #5's output, return the **live, headline match-winner** markets with their
bid/ask prices (ready to order). Drops derivative sub-markets (spreads, totals,
"win by 1.5+", BTTS, halves, …) when `main_only=True`; re-fetches fresh bids when
`refresh_bids=True`.
```python
ready = await filter_live_matches(picks)        # [{ticker, yes_bid, no_bid, ...}, ...]
```

### 7. `get_the_market_scores_kalshi(market_ticker)`
Full match stats for a buy decision. Returns a dict:
```python
{
  "sport": "Tennis", "league": "...", "match_status": "live",
  "participants": [{"name","ticker","yes_bid","yes_ask","last_price","implied_prob"}, ...],
  "implied": {"Jannik Sinner": 0.70, ...},      # market's live probabilities
  "score": {"unit": "set", "sets": [], ...},    # per-sport skeleton
  "scores_source": "none",                       # "external" once a feed is wired in
  "note": "...",
}
```
Per-sport `score` shapes: tennis→sets, cricket→innings/runs/wickets,
baseball→inning/runs, basketball/football→quarter/points, soccer→goals,
hockey→period/goals, MMA/boxing→round, golf→holes, motorsport→laps, chess→game.
The skeleton is populated only if you implement `_external_scores()` against a
real provider (ESPN, api-sports.io, …).
```python
stats = await get_the_market_scores_kalshi(ready[0]["ticker"])
```

### Helpers
- `list_sports()` → every distinct sport tag, sorted.
- `fetch_sports_markets(sport=None, league=None, status="open", max_series=150, concurrency=10)`
  → the underlying enriched-market fetcher (concurrent, capped).

---

## End-to-end example

```python
import asyncio, kalshi_sports as ks

async def main():
    picks = await ks.filter_by_sport_league_min_volume("Soccer", "English Premier League", 1000)
    ready = await ks.filter_live_matches(picks)          # live match-winners + bids
    for r in ready:
        stats = await ks.get_the_market_scores_kalshi(r["ticker"])
        print(r["title"], r["yes_bid"], stats["implied"])

asyncio.run(main())
```

---

## Notes & caveats
- **USD volume** is an estimate (`contracts × last_price`); use it for relative
  liquidity ranking, not exact dollar turnover.
- **Reuse a client** for chains/perf: pass `client=KalshiClient()` to each call
  (and `await client.close()` once) to avoid per-call connections.
- **`fetch_sports_markets` caps** at `max_series` (default 150) when no
  `sport`/`league` narrowing is given, to avoid hammering the API (some sports
  have hundreds of series). Always narrow by sport+league for live game scans.
- The series taxonomy is cached for 10 min (`_sports_series` TTL).
