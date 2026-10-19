# PREDICT-15 — can the next Kalshi 15-minute BTC / ETH window be called?

Research behind `backend/app/domains/botstation/predict15.py` and the Bot Station
**PREDICT-15** panel. Data: 2026-09-28 → 2026-10-19. Scripts: `tools/research/predict15/`.

## The market

`KXBTC15M` / `KXETH15M`: YES if the CF Benchmarks BRTI average over the 60 seconds before
the close is **at least** the average over the 60 seconds before the open (`floor_strike`).
So it is a digital option on "price at the close ≥ this strike", not a call on direction
in general.

## Data

| Source | What | Size |
|---|---|---|
| Kalshi settled markets | strike, final value, result, per window | 1,992 BTC + 1,992 ETH (21 days) |
| Coinbase 1-minute candles | features, the price inside the window | 30,599 bars per coin |
| Kalshi 1-minute candlesticks | the real YES bid / ask at each minute | 665 windows per coin (last 7 days) |

Base rate: YES 49.6% (BTC), 50.4% (ETH).

## A. Before the window opens: a coin flip

Every number is out-of-sample or a fixed rule; ±0.022 is the 95% band on 1,990 calls.

| Signal | BTC | ETH |
|---|---|---|
| last 1-minute move continues | 53.7% | 54.4% |
| last 5 / 15 / 60-minute move continues | 51.3 / 50.4 / 50.8% | 52.4 / 50.6 / 50.1% |
| previous window's result repeats | 48.9% | 50.2% |
| mean reversion (60-minute z-score) | 50.3% | 49.9% |
| 12-feature logistic regression, trained on the first 60%, tested on the last 40% | 51.5% | 54.7% |

The one real effect, the last minute's move, is mechanical: the strike is a 60-second
*average*, so a price still rising starts above its own strike. The fair-value formula
below prices that through S/K. Nothing else is distinguishable from noise.

## B. Inside the window: price against the strike

`P(YES) = N( ln(S/K) / (σ·√τ) )`, with σ the standard deviation of one-minute log returns
over the previous hour and τ the minutes left.

| Decision time | BTC accuracy | ETH accuracy | when the model is ≥60% sure |
|---|---|---|---|
| T+1m | 60.8% | 61.3% | 68% / 67% |
| T+2m | 63.5% | 64.2% | 71% / 72% |
| T+3m | 67.1% | 69.3% | 74% / 76% |
| T+5m | 72.2% | 71.2% | 78% / 79% |
| T+10m | 81.0% | 84.8% | 86% / 89% |

It is calibrated (T+5m BTC: 62% predicted → 63% seen; 21% → 20%), with slightly
overconfident tails (96% → 90%), so probabilities are clipped to 2–98%.

## C. Against Kalshi's real prices

Buying the better side whenever the model beat the real quote at that minute by more than
a margin, with Kalshi's taker fee (7% of p(1−p), rounded up), settled on Kalshi's result:

| | margin > 0 | > 3c | > 5c | > 10c |
|---|---|---|---|---|
| BTC T+2m ROI | −6.3% (581 trades) | −4.2% | −4.2% | +25% (15) |
| ETH T+2m ROI | −0.7% (590) | +6.7% | +19% (123) | +52% (7) |
| BTC T+8m ROI | −3.5% | −6.7% | −0.9% | −41% (46) |
| ETH T+8m ROI | −12.5% | −7.6% | −20% | −21% (64) |

Trading every disagreement **loses** on both coins. Late in the window the model loses
badly: the market sees the BRTI and the closing average better than a Coinbase price does.
The positive cells are small, do not agree across coins, and are a handful out of 40 cells
tested. They are not a proven edge.

Who predicts better, the model or the market (log-loss, lower is better)?

| | model | Kalshi mid | 50/50 blend |
|---|---|---|---|
| BTC T+2m | 0.6138 | 0.6121 | 0.6120 |
| BTC T+5m | 0.5514 | 0.5390 | 0.5428 |
| ETH T+2m | 0.6053 | 0.6079 | 0.6055 |
| ETH T+5m | 0.5198 | 0.5138 | 0.5147 |

## What PREDICT-15 does with this

* **The call (YES/NO)** is a blend: half model, half Kalshi mid for the first 4 minutes,
  a quarter model after. That is at least as good as either alone.
* **Model** is the fair value by itself, shown next to the Kalshi quote.
* **TRADE / EDGE** only when the model beats the quote by **10c or more after the fee**,
  the only margin not negative on both coins. Unproven: paper first.
* **Simulate** replays the last 12h–3 days at a chosen minute against the real quotes,
  so any rule change can be checked on fresh data before it is trusted.

Nothing here places an order.
