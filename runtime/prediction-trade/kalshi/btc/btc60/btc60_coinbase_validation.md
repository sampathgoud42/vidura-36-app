# Coinbase-candle validation — committee + timeboxes, 46 days
- candles 13246, 2026-05-26 03:15:00+00:00 → 2026-07-11 03:05:00+00:00 (source: Coinbase public /market/products/BTC-USD/candles, paged 350/req)
- same engine, same committee definitions as phases 2-5 (yfinance)

## 1. Committee members on Coinbase data
member | dir | n | acc% | wilsonLB | /day
S1 sqz_break+di_dom          | SHORT |  85 |  62.4 |  51.7 | 2.11
S2 poc_cross+adx30           | LONG  |  46 |  56.5 |  42.2 | 1.04
S3 adx_di_cross+mom+adx20    | LONG  |  80 |  55.0 |  44.1 | 1.91
S4 mom3_60+poc_cross         | SHORT | 152 |  49.3 |  41.5 | 3.72
S5 poc_cross+adx27.5         | SHORT |  56 |  48.2 |  35.7 | 1.28

## 2. Pooled committee per 3h UTC timebox
box(UTC) | n | acc% | wilsonLB | yfinance verdict
00-03 |  49 |  57.1 |  43.3 | BAD
03-06 |  35 |  65.7 |  49.2 | good
06-09 |  69 |  55.1 |  43.4 | good
09-12 |  58 |  50.0 |  37.5 | good~
12-15 |  64 |  56.2 |  44.1 | good
15-18 |  38 |  42.1 |  27.9 | BAD
18-21 |  64 |  53.1 |  41.1 | good
21-24 |  42 |  50.0 |  35.5 | good
- **ALL hours**: n=419, acc 53.7% (LB 48.9%), EV/50c ≈ +3.1c
- **GOOD boxes (yfinance def)**: n=332, acc 54.5% (LB 49.1%), EV/50c ≈ +3.4c
- **BAD boxes**: n=87, acc 50.6% (LB 40.3%), EV/50c ≈ +2.0c

## 3. Weekly folds (pooled committee, all hours)
w0:23/46 w1:45/67 w2:44/72 w3:18/47 w4:34/80 w5:39/64 w6:22/43

## 3b. TRIMMED committee (S1+S2+S3 only) per timebox
box(UTC) | n | acc% | wilsonLB
00-03 |  22 |  59.1 |  38.7
03-06 |  20 |  70.0 |  48.1
06-09 |  38 |  71.1 |  55.2
09-12 |  30 |  50.0 |  33.2
12-15 |  30 |  63.3 |  45.5
15-18 |  20 |  35.0 |  18.1
18-21 |  36 |  55.6 |  39.6
21-24 |  15 |  53.3 |  30.1
- **TRIMMED all hours**: n=211, acc 58.3% (LB 51.6%), EV/50c ≈ +4.8c, 5.1 fires/day (all-hours)
- **TRIMMED good boxes [0, 1, 2, 4, 6]**: n=146, acc 63.7% (LB 55.6%), EV/50c ≈ +6.8c, 5.1 fires/day (all-hours)
- TRIMMED weekly folds: w0:11/23 w1:33/40 w2:23/36 w3:10/21 w4:21/44 w5:16/28 w6:9/19

## 4. REAL volume rhythm (Coinbase, median per UTC hour)
hour | med volume (BTC) | med 30-min range $
00   |    16.78 |    227
01   |    16.73 |    276
02   |    15.33 |    270
03   |    13.67 |    239
04   |    12.48 |    216
05   |    11.94 |    231
06   |    10.94 |    218
07   |    12.38 |    207
08   |    12.39 |    219
09   |    11.74 |    205
10   |    11.74 |    204
11   |    14.72 |    206
12   |    23.10 |    284
13   |    39.68 |    354
14   |    47.65 |    433
15   |    43.70 |    404
16   |    36.37 |    318
17   |    31.05 |    300
18   |    25.22 |    254
19   |    30.77 |    234
20   |    20.72 |    216
21   |    19.70 |    237
22   |    17.90 |    251
23   |    15.02 |    209