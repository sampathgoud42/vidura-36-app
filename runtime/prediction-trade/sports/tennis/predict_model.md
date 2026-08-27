# Tennis Match Prediction Model — v2.0

> Spec for [`predict.py`](./predict.py). Goal: given a **live** tennis match, pick the
> player to **back to win the match** (the only tradeable Kalshi market) with a
> **confidence**, and — when that player's live bid sits in the value band — emit a
> **BUY** tip. Edit this doc to propose changes; each section maps to a function in
> `predict.py`.

---

## 1. Output

`predict_buy(...)` returns a dict:

| field        | meaning |
|--------------|---------|
| `action`     | `BUY` \| `SKIP` \| `WAIT` |
| `player`     | resolved player name to back |
| `side`       | `A` (home) \| `B` (away) |
| `bid`        | that player's live YES bid (cents) |
| `confidence` | `ultra high` \| `high` \| `medium` \| `low` |
| `situation`  | `A`–`F` or `fallback` |
| `reason`     | human explanation |
| `score`      | one-liner score string |
| `tip`        | only on BUY: `"<Lastname> >> buy at <bid>c (<conf>)"` |

**Action gate** (`predict_buy`):
- `WAIT` — too early / no data / engine deferred with a "wait" reason.
- `SKIP` — a side was chosen but there's **no live bid**, or the bid is **outside the band**.
- `BUY`  — a side was chosen **and** `BID_LO ≤ bid ≤ BID_HI`.

---

## 2. Confidence levels → buy gate

Confidence drives the buy decision in `predict_buy`:

| confidence  | rule |
|-------------|------|
| `ultra high`| **ignore the bid band**; BUY if `bid < ULTRA_BUY_MAX` (85¢), else SKIP |
| `high`      | standard flow — BUY if `BID_LO ≤ bid ≤ BID_HI` |
| `medium`    | **set 1** (`completed_sets == 0`): **WAIT** for set 2, then re-predict · **set 2/3**: standard band flow |
| `low`       | **WAIT** — never buy; wait for a medium+ prediction |

**Set-1 cap:** while the match is still in set 1 (`completed_sets == 0`), any non-ultra
buy additionally requires **`bid < SET1_MAX_BID` (50¢)** — i.e. the effective band is
`BID_LO … min(BID_HI, 49)`. Ultra-high is exempt (its own `< ULTRA_BUY_MAX` rule).

---

## 3. Config (env vars)

| env | default | use |
|-----|---------|-----|
| `PREDICT_BID_LO`   | `26` | buy band low (cents) |
| `PREDICT_BID_HI`   | `72` | buy band high (cents) |
| `PREDICT_HEAVY_FAV`| `70` | "heavy favorite" threshold (pre-match implied %) |
| `PREDICT_ULTRA_MAX`| `85` | ultra-high: buy if `bid <` this (band ignored) |
| `PREDICT_SET1_MAX` | `50` | set 1 (non-ultra): buy only if `bid <` this |
| `PREDICT_POLL_S`   | `5`  | demo poll interval |

> NOTE: the **bot** also has its own discovery band (`SPORT_BID_LO/HI`) and applies a
> separate `+5¢` bump at order time — those live in `bot_kalshi_sports_v1.py`, not here.

---

## 4. Inputs — `match_data` ("md") shape

Built by `_md_from_kalshi(match)` (live path) or `_md_from_scraper(d)` (on-demand). Side **A = home, B = away**.

| field            | type | derivation |
|------------------|------|------------|
| `scenario`       | `elite` \| `parity` | **elite** if either player's rank ≤ 10, else parity |
| `favorite`       | `A` \| `B` \| `None` | better (lower) rank; `None` if ranks equal/missing |
| `fav_prob`       | cents \| `None` | favorite's **pre-match** implied % (from original odds) |
| `completed_sets` | int  | `a_sets + b_sets` |
| `sets`           | (a,b) | sets won each |
| `set1_winner/margin`, `set2_winner/margin` | | from games of completed sets |
| `games`          | (ga,gb) | current-set games |
| `serving`        | `A` \| `B` \| `None` | |
| `points`         | (pa,pb) | each `0/15/30/40/A` (normalized by `_norm_pt`) |
| `break_point`    | bool | receiver at `A`, or at `40` with server not at `40/A` |
| `double_break`   | `A` \| `B` \| `None` | set leader when game margin **≥ 3** |
| `stay_in_set`    | `A` \| `B` \| `None` | server at games **(4,5)** or **(5,6)** (serving to stay in set) |

Point rank used for comparisons: `0<15<30<40<A` (`_PT_RANK`).

---

## 5. Situation engine — `predict_v2(md)`

Evaluated **top to bottom**; first match wins. Returns `(side, confidence, situation, reason)`;
`side = None` means *wait* or *defer to fallback*.

### Pre-empt rules (checked before set structure)

| # | Situation | Trigger | Action | Conf |
|---|-----------|---------|--------|------|
| E | double-break dead zone | `double_break` set (game margin ≥ 3) | back **set leader** | high |
| D | serving to stay        | `stay_in_set` set **and** server dropped **≥ 3 straight points** (server pts `0`, receiver pts `40` — triple break point) | back **receiver** | high |

### Set-structure situations

**Situation A — set 1 in progress (`completed_sets == 0`)**

| condition | action | conf |
|-----------|--------|------|
| `ga+gb < 4` and not break_point | **WAIT** (too early) | — |
| no favorite | *defer to fallback* | — |
| favorite holding/leading (`fav_games ≥ opp_games`) | back **favorite** | high if elite else **medium** |
| elite & favorite broken | back **favorite** (recovery) | medium |
| parity & favorite broken | back **underdog** | medium |

**Situation B2 — set-2 management of a STRONG original favorite (priority over B)**

Applies in set 2 when one player is a **strong original favorite** — BOTH a rank
edge ≥ `FAV_RANK_DIFF` (50) **and** an original-odds edge ≥ `FAV_ODDS_DIFF` (25) —
**and that favorite won set 1**. Then:
1. **Wait** until set 2 reaches the **5th game** (`games played ≥ SET2_MIN_GAMES`, 4).
2. If the favorite's **live price dropped sharply** (`orig − live ≥ FAV_DROP_C`, 25¢)
   **and the favorite is serving** → **BUY the favorite (value)**, regardless of how
   the low-ranked player is doing in set 2.
3. Else if set 2 still **favours the favorite** (≥ on games) → BUY (normal band/confidence).
   Otherwise (favorite faltering, no price drop) → **WAIT**.
Example: `Gill(220) vs Choinski(106)* 0-1: 4-6, 2-2 (15:0) orig{36;82}` — wait until 5th
game; buy Choinski if his price drops & he serves, else buy while he holds set 2.

**Situation B — set 1 completed (`completed_sets == 1`)** (when no strong-favorite case)

| condition | action | conf |
|-----------|--------|------|
| set1 winner unknown | **WAIT** | — |
| no favorite | back **set1 winner** | low |
| favorite won set 1 | back **favorite** (→ straight sets) | high |
| favorite lost, margin ≥ 4 (dominant), **elite** | back **favorite** (bounce-back) | medium |
| favorite lost, margin ≥ 4 (dominant), **parity** | back **set1 winner** (→ 2-0) | high |
| **heavy fav** (`fav_prob ≥ HEAVY_FAV`) lost a **tight** set1 (margin ≤ 2) | back **underdog** | medium |
| else | back **set1 winner** | low |

**Situation F3 — set-3 close decider (odds + return pressure, priority over F)**

Runs first in the decider (in `predict_buy`, needs live + original odds): if the
**original odds were close** (`|origA−origB| ≤ SET3_CLOSE_C`, 10¢) and the **slight
original favorite** is **≥ even on live odds** AND is **returning** with **≥ 1 point
on the opponent's serve**, back that player **high**.
Example: `Kunitsyn* vs Chen 1-1: 5-7,6-4,0-0 (15:15) live{49;50} orig{50;53}` → BUY Chen.

**Situation F — set 3 decider, 1-1 (`completed_sets == 2`)** (fallback when F3 doesn't fire)

| condition | action | conf |
|-----------|--------|------|
| elite & favorite exists | back **favorite** | high |
| parity & set 2 dominant (margin ≥ 4) | back **set2 winner** | medium |
| someone serving | back **set-3 opening server** | low |
| (none) | *defer to fallback* | — |

> Situation **C** (post-break consolidation) is named in the header but not yet a
> distinct branch — currently absorbed by A/E. Candidate for review.

---

## 6. Fallback micro-state engine — `_combo_fallback(md, combos)`

Used when `predict_v2` returns no side **and** the reason is not a "wait".

| condition | action | conf | reason |
|-----------|--------|------|--------|
| `max(ga,gb) == 5` and `ga≠gb`, **server is the 5-game leader** (serving for set) | back leader | **high** | serving for set (was ultra; log showed ~57% collapse at 85¢) |
| `max(ga,gb) == 5` and `ga≠gb`, leader is **receiving** | back leader | **low → WAIT** | premature — server usually holds to 5-5 (log: ~70% collapse) |
| `ga == gb`, A ahead on points | back A | low | symmetric, A up on points |
| `ga == gb`, B ahead on points | back B | low | symmetric, B up on points |
| `ga == gb`, points tied, someone serving | back server | low | symmetric tie, edge to server |
| lookup hit in `tennis_all_combinations.csv` | back table leader | low | combinations.csv |
| else | — | — | undetermined → **WAIT** |

**Combinations table** (`load_combinations`, `tennis_all_combinations.csv`):
key = `(serving, "min(ga,5):min(gb,5)", "pa:pb")` → leader `A`/`B`.
CSV columns used: `Serving`, `Current Score (A:B)` (parsed as `ga:gb(pa:pb)`), `Leading`.

---

## 7. Buy gate — `predict_buy(match, live_bids, original_bids, ...)`

1. Build `md` from the Kalshi match; set `fav_prob` = favorite's **original** (pre-match) bid.
2. Run `predict_v2`. If `side is None`:
   - reason contains "wait" → return **WAIT**.
   - else → run `_combo_fallback`.
3. If still no side → **WAIT**.
4. Resolve `name` from `side`; `bid = live_bids[name]`. No bid → **SKIP**.
5. Apply the **confidence gate** (§2): `low` → WAIT; `medium` in set 1 → WAIT;
   `ultra high` → BUY if `bid < ULTRA_BUY_MAX` else SKIP; `high` / `medium` (set 2/3)
   → BUY if `bid` in band, else SKIP.

---

## 8. Data sources

- **Live (in-bot):** `_md_from_kalshi` from the Kalshi milestone data the bot already
  fetches — fast, scales to many matches, used in the per-poll loop.
- **On-demand:** `_md_from_scraper` via the SofaScore Playwright scraper
  (`tennis/web/tennis_live_match_scraper.py`), searched by **first name**
  (lowercased/stripped). Launches a browser per call → **not** used in the poll loop.
  Exposed by `scrape_match_data`, `predict_for_player`, and `live_statuses`.

---

## 9. Review checklist / open questions

- [x] Confidence drives the buy gate (ultra-high ignores band <85¢; medium waits out set 1; low waits). See §2.
- [x] Log-drift analysis (06/22-23): downgraded the fallback 5-game rules — receiver→LOW (~70% collapse), server ultra→high (~57% collapse). E/high (double-break) is the best high-volume signal (~9% collapse), kept.
- [x] Real-trade backtest (trade_history_sports.csv, 23 closes): **high-price backs (77-87c) became total losses** (favorites that lost the match); only low-priced entries (32-41c) won; overall win rate low (~12%). Action: lowered `BID_HI` 81→**68** and `ULTRA_BUY_MAX` 85→**72** to cut the -EV high-price favorite backs. (Per-trade `realized_pnl` from fills was overcounting all-time fills — fixed with a since-open filter.)
- [ ] Should confidence also drive **sizing** (contracts)?
- [ ] Re-check **B/high** (fav won set 1) — avg entry ~69¢, ~22% collapse, little price edge (small sample).
- [ ] **F/medium** (set-3 decider) looked poor (n=2, 100% collapse) — revisit once more data.
- [ ] Add an explicit **Situation C** (post-break consolidation)?
- [ ] Tune `double_break` threshold (currently game margin ≥ 3) and `stay_in_set` games.
- [ ] Revisit `HEAVY_FAV` trap (B) and the elite "bounce-back" rules.
- [ ] Confirm band defaults (`26–72`) vs the bot's discovery band and the `+5¢` order bump.
