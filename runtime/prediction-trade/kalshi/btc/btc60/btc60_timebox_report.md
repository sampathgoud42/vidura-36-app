# BTC-60 timebox study — 46 days 5m, boxes of 3h (UTC)
- bars 13267, 2026-05-26 00:00:00+00:00 → 2026-07-11 03:00:00+00:00
- CST = UTC−5 (CDT).  Box b covers UTC [3b, 3b+3).

## 1. Market rhythm by UTC hour
hour | med volume | med 30-min range $ | uncond ft-LONG % | reach-any %
00   |  1378304.0 |      221 |  45.4 |  88.3
01   |        0.0 |      265 |  46.3 |  86.5
02   |        0.0 |      258 |  43.3 |  84.8
03   |        0.0 |      228 |  43.9 |  77.9
04   |        0.0 |      208 |  46.7 |  87.3
05   |  5539840.0 |      224 |  47.6 |  79.2
06   |        0.0 |      208 |  48.0 |  81.5
07   |  7304192.0 |      200 |  53.5 |  77.5
08   |        0.0 |      211 |  40.8 |  78.1
09   |   569344.0 |      198 |  45.8 |  79.9
10   |        0.0 |      194 |  49.8 |  75.7
11   |        0.0 |      200 |  45.9 |  78.6
12   |        0.0 |      263 |  44.0 |  88.0
13   |        0.0 |      345 |  43.1 |  93.8
14   |        0.0 |      413 |  48.7 |  94.2
15   |        0.0 |      377 |  45.0 |  92.6
16   |        0.0 |      305 |  47.0 |  92.2
17   |        0.0 |      284 |  47.1 |  88.8
18   |        0.0 |      243 |  39.6 |  80.1
19   |        0.0 |      223 |  52.1 |  82.8
20   |  4589056.0 |      208 |  54.6 |  76.6
21   |        0.0 |      228 |  50.0 |  85.9
22   |   567296.0 |      243 |  47.7 |  79.1
23   |        0.0 |      204 |  55.4 |  80.2

## 2. Committee accuracy per 3h timebox (ft ±$100/30min)

member | box(UTC) | n | acc% | wilsonLB
S1 sqz_break+di_dom          | 00-03 |   7 |  42.9 |  15.8
S1 sqz_break+di_dom          | 03-06 |   8 |  87.5 |  52.9
S1 sqz_break+di_dom          | 06-09 |  11 |  63.6 |  35.4
S1 sqz_break+di_dom          | 09-12 |  17 |  64.7 |  41.3
S1 sqz_break+di_dom          | 12-15 |  11 |  63.6 |  35.4
S1 sqz_break+di_dom          | 15-18 |   5 | 100.0 |  56.6
S1 sqz_break+di_dom          | 18-21 |  13 |  53.8 |  29.1
S1 sqz_break+di_dom          | 21-24 |   6 |  50.0 |  18.8
S2 poc_cross+adx30           | 00-03 |   5 |  20.0 |   3.6
S2 poc_cross+adx30           | 03-06 |   7 |  71.4 |  35.9
S2 poc_cross+adx30           | 06-09 |  10 |  70.0 |  39.7
S2 poc_cross+adx30           | 09-12 |   4 |  75.0 |  30.1
S2 poc_cross+adx30           | 12-15 |   5 |  80.0 |  37.6
S2 poc_cross+adx30           | 15-18 |   2 | 100.0 |  34.2
S2 poc_cross+adx30           | 21-24 |   2 |   0.0 |   0.0
S3 adx_di_cross+mom+adx20    | 00-03 |   5 |  60.0 |  23.1
S3 adx_di_cross+mom+adx20    | 03-06 |   5 |  60.0 |  23.1
S3 adx_di_cross+mom+adx20    | 06-09 |   7 |  71.4 |  35.9
S3 adx_di_cross+mom+adx20    | 09-12 |   4 |  25.0 |   4.6
S3 adx_di_cross+mom+adx20    | 12-15 |  10 |  80.0 |  49.0
S3 adx_di_cross+mom+adx20    | 15-18 |   9 |  22.2 |   6.3
S3 adx_di_cross+mom+adx20    | 18-21 |   4 | 100.0 |  51.0
S3 adx_di_cross+mom+adx20    | 21-24 |   2 |  50.0 |   9.5
S4 mom3_60+poc_cross         | 00-03 |  17 |  47.1 |  26.2
S4 mom3_60+poc_cross         | 03-06 |  15 |  46.7 |  24.8
S4 mom3_60+poc_cross         | 06-09 |  16 |  68.8 |  44.4
S4 mom3_60+poc_cross         | 09-12 |  21 |  52.4 |  32.4
S4 mom3_60+poc_cross         | 12-15 |  30 |  50.0 |  33.2
S4 mom3_60+poc_cross         | 15-18 |  12 |  33.3 |  13.8
S4 mom3_60+poc_cross         | 18-21 |  15 |  66.7 |  41.7
S4 mom3_60+poc_cross         | 21-24 |  15 |  66.7 |  41.7
S5 poc_cross+adx27.5         | 00-03 |   5 |  60.0 |  23.1
S5 poc_cross+adx27.5         | 03-06 |   8 |  37.5 |  13.7
S5 poc_cross+adx27.5         | 06-09 |  10 |  40.0 |  16.8
S5 poc_cross+adx27.5         | 09-12 |   5 |  40.0 |  11.8
S5 poc_cross+adx27.5         | 12-15 |   6 |  50.0 |  18.8
S5 poc_cross+adx27.5         | 15-18 |   1 |   0.0 |   0.0
S5 poc_cross+adx27.5         | 18-21 |   3 |  66.7 |  20.8
S5 poc_cross+adx27.5         | 21-24 |   5 |  80.0 |  37.6

### Pooled committee per timebox
box(UTC) | n | acc% | wilsonLB
00-03 |  39 |  46.2 |  31.6
03-06 |  43 |  58.1 |  43.3
06-09 |  54 |  63.0 |  49.6
09-12 |  51 |  54.9 |  41.4
12-15 |  62 |  59.7 |  47.3
15-18 |  29 |  44.8 |  28.4
18-21 |  35 |  65.7 |  49.2
21-24 |  30 |  60.0 |  42.3

## 3. Good-box gate: boxes [1, 2, 4, 6, 7] (UTC ['03-06', '06-09', '12-15', '18-21', '21-24'])
- **ALL hours**: n=343, acc 57.1% (LB 51.9%), 8.6 fires/day, EV/50c-contract ≈ +4.4c — folds w0:22/37 w1:39/58 w2:24/43 w3:15/36 w4:32/70 w5:34/49 w6:30/50
- **GOOD boxes only**: n=224, acc 61.2% (LB 54.6%), 5.6 fires/day, EV/50c-contract ≈ +5.8c — folds w0:13/22 w1:28/41 w2:15/23 w3:14/26 w4:25/53 w5:22/30 w6:20/29
- **BAD boxes only**: n=119, acc 49.6% (LB 40.8%), 3.0 fires/day, EV/50c-contract ≈ +1.6c — folds w0:9/15 w1:11/17 w2:9/20 w3:1/10 w4:7/17 w5:12/19 w6:10/21