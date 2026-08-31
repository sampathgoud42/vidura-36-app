# btc60_burst revalidation — 2026-07-11T03:24:08.217193+00:00
- data: 13247 bars, 2026-05-26 03:25:00+00:00 → 2026-07-11 03:15:00+00:00
- rule: drop members/boxes < 54.0% (±$100/30min first-touch)

## Members
name | dir | n | acc% | enabled
S1 | SHORT | 85 | 62.4 | True
S2 | LONG | 47 | 57.4 | True
S3 | LONG | 79 | 48.1 | False

## 1h UTC timeboxes
hour | n | acc% | enabled | basis
00 |   6 | 45.5 | False | 3h[00-03]
01 |   4 | 45.5 | False | 3h[00-03]
02 |   1 | 45.5 | False | 3h[00-03]
03 |   4 | 68.8 | True | 3h[03-06]
04 |   6 | 68.8 | True | 3h[03-06]
05 |   6 | 68.8 | True | 3h[03-06]
06 |   4 | 66.7 | True | 3h[06-09]
07 |   7 | 66.7 | True | 3h[06-09]
08 |  13 | 76.9 | True | 1h
09 |   5 | 60.0 | True | 3h[09-12]
10 |   7 | 60.0 | True | 3h[09-12]
11 |  13 | 61.5 | True | 1h
12 |   8 | 62.5 | True | 1h
13 |   2 | 66.7 | True | 3h[12-15]
14 |   5 | 66.7 | True | 3h[12-15]
15 |   5 | 66.7 | True | 3h[15-18]
16 |   1 | 66.7 | True | 3h[15-18]
17 |   3 | 66.7 | True | 3h[15-18]
18 |  11 | 45.5 | False | 1h
19 |   3 | 56.5 | True | 3h[18-21]
20 |   9 | 55.6 | True | 1h
21 |   6 | 44.4 | False | 3h[21-24]
22 |   1 | 44.4 | False | 3h[21-24]
23 |   2 | 44.4 | False | 3h[21-24]