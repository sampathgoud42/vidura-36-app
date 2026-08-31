# BTC-60 ensemble validation — ±$100 / 30min first-touch, 46 days of 5m
- bars 13264, 2026-05-26 00:00:00+00:00 → 2026-07-11 02:45:00+00:00
- folds = calendar weeks (w0 = most recent); wilson_lb = 95% lower bound on accuracy; worst_fold = min weekly accuracy (folds with ≥3 resolved)

## Shortlist + fine sweeps, ranked by Wilson lower bound

direction                                combo   n  acc  wilson_lb  worst_fold  per_day                                                        folds
    SHORT                   poc_cross + adx>20 127 55.9       47.2        40.0     3.14   w0:9/14 w1:14/22 w2:6/12 w3:6/15 w4:14/27 w5:9/17 w6:13/20
     LONG                   poc_cross + adx>30  35 62.9       46.3        33.3     0.82             w0:5/5 w1:5/7 w2:3/6 w3:1/3 w4:2/5 w5:2/2 w6:4/7
     LONG                   poc_cross + adx>30  35 62.9       46.3        33.3     0.82             w0:5/5 w1:5/7 w2:3/6 w3:1/3 w4:2/5 w5:2/2 w6:4/7
    SHORT       mom3_60 + poc_cross + near_lvl  69 58.0       46.2        30.8     1.71           w0:7/8 w1:5/8 w2:6/9 w3:4/13 w4:7/15 w5:7/8 w6:4/8
     LONG     adx_di_cross + momentum + adx>15  83 56.6       45.9        42.9     2.21        w0:5/9 w1:6/8 w2:5/7 w3:10/13 w4:12/26 w5:6/14 w6:3/6
    SHORT                  mom3_60 + poc_cross 141 53.9       45.7        35.0     3.49 w0:11/18 w1:10/18 w2:8/14 w3:7/20 w4:14/34 w5:16/21 w6:10/16
     LONG              adx_di_cross + momentum 122 54.1       45.3        41.0     3.14     w0:7/11 w1:8/12 w2:7/13 w3:17/23 w4:16/39 w5:7/16 w6:4/8
     LONG                 poc_cross + adx>32.5  25 64.0       44.5        40.0     0.56             w0:5/5 w1:2/2 w2:2/4 w3:0/1 w4:2/5 w5:2/2 w6:3/6
     LONG scalp_bias + adx_di_cross + near_lvl  16 68.8       44.4        66.7     0.56             w0:4/5 w1:2/2 w2:2/3 w3:2/2 w4:1/2 w5:0/1 w6:0/1
     LONG     adx_di_cross + momentum + adx>20  46 58.7       44.3        40.0     1.21            w0:3/3 w1:6/6 w2:2/3 w3:4/7 w4:6/13 w5:4/9 w6:2/5
     LONG     adx_di_cross + momentum + adx>20  46 58.7       44.3        40.0     1.21            w0:3/3 w1:6/6 w2:2/3 w3:4/7 w4:6/13 w5:4/9 w6:2/5
     LONG   adx_di_cross + momentum + adx>17.5  64 56.2       44.1        38.5     1.63          w0:3/5 w1:6/7 w2:4/6 w3:8/11 w4:8/17 w5:5/13 w6:2/5
    SHORT                   poc_cross + adx>25  67 55.2       43.4        25.0     1.60        w0:2/4 w1:10/14 w2:5/10 w3:3/9 w4:6/10 w5:2/8 w6:9/12
    SHORT                 poc_cross + adx>22.5  92 53.3       43.1        33.3     2.21     w0:6/8 w1:11/17 w2:5/11 w3:4/11 w4:9/17 w5:4/12 w6:10/16
    SHORT     cusum_1.5 + poc_cross + near_lvl  63 54.0       41.8        30.0     1.56         w0:2/2 w1:7/11 w2:7/10 w3:3/10 w4:5/13 w5:5/9 w6:5/8
    SHORT              adx_di_cross + momentum 147 49.0       41.0        33.3     3.88    w0:5/13 w1:10/20 w2:8/24 w3:8/19 w4:21/43 w5:13/19 w6:7/9
     LONG                 poc_cross + adx>27.5  52 53.8       40.5        25.0     1.24           w0:5/5 w1:6/10 w2:6/10 w3:2/6 w4:2/8 w5:3/4 w6:4/9
     LONG    mech_trigger + cusum_2.0 + adx>20  50 54.0       40.4        14.3     1.34           w0:6/6 w1:5/7 w2:7/11 w3:2/5 w4:1/7 w5:3/10 w6:3/4
     LONG                   poc_cross + adx>20 125 48.0       39.4        29.6     3.08    w0:9/14 w1:12/20 w2:8/14 w3:7/15 w4:8/27 w5:10/17 w6:6/18
     LONG     adx_di_cross + momentum + adx>25  24 58.3       38.8        33.3     0.61             w0:1/1 w1:2/2 w2:2/3 w3:1/3 w4:5/9 w5:2/4 w6:1/2
     LONG      scalp_bias + vol_burst + adx>20  29 55.2       37.5        42.9     0.72             w0:4/6 w1:5/5 w2:0/2 w3:1/2 w4:0/1 w5:3/6 w6:3/7
     LONG                 poc_cross + adx>22.5  89 46.1       36.1        35.7     2.15       w0:5/7 w1:7/14 w2:7/12 w3:4/11 w4:8/21 w5:5/10 w6:5/14
     LONG        poc_cross + cumdelta + adx>20  72 47.2       36.1        25.0     1.80         w0:5/6 w1:2/3 w2:1/4 w3:6/12 w4:5/16 w5:9/16 w6:6/15
     LONG   adx_di_cross + momentum + adx>22.5  30 53.3       36.1        25.0     0.76            w0:1/1 w1:3/3 w2:2/3 w3:1/4 w4:6/11 w5:2/6 w6:1/2
     LONG                   poc_cross + adx>25  69 46.4       35.1        21.4     1.65         w0:5/5 w1:7/13 w2:6/10 w3:2/7 w4:3/14 w5:4/8 w6:5/12
     LONG     vidya_dmi + cusum_1.5 + momentum  38 50.0       34.8         0.0     0.95             w0:3/4 w1:6/6 w2:4/8 w3:3/4 w4:0/6 w5:1/6 w6:2/4
     LONG        poc_cross + momentum + adx>20  65 46.2       34.6        25.0     1.52          w0:5/5 w1:7/13 w2:2/3 w3:3/8 w4:4/16 w5:6/13 w6:3/7
    SHORT                 poc_cross + adx>27.5  43 48.8       34.6        25.0     1.02            w0:0/2 w1:4/8 w2:2/7 w3:1/4 w4:4/6 w5:2/5 w6:8/11
     LONG               vidya_dmi + cusum_2.25  27 51.9       34.0        20.0     0.76             w0:2/3 w1:4/6 w2:1/3 w3:3/3 w4:1/5 w5:2/5 w6:1/2
     LONG                vidya_dmi + cusum_1.5  39 48.7       33.9         0.0     0.98             w0:3/4 w1:6/7 w2:4/8 w3:3/4 w4:0/6 w5:1/6 w6:2/4
     LONG                vidya_dmi + cusum_1.5  39 48.7       33.9         0.0     0.98             w0:3/4 w1:6/7 w2:4/8 w3:3/4 w4:0/6 w5:1/6 w6:2/4
    SHORT     adx_di_cross + momentum + adx>15  95 43.2       33.7        27.3     2.56        w0:3/11 w1:6/15 w2:6/18 w3:4/8 w4:9/23 w5:7/12 w6:6/8
    SHORT   adx_di_cross + momentum + adx>17.5  73 43.8       33.0        33.3     2.02         w0:3/9 w1:4/12 w2:6/15 w3:3/7 w4:6/15 w5:6/10 w6:4/5
    SHORT     adx_di_cross + momentum + adx>20  56 44.6       32.4        27.3     1.56           w0:3/7 w1:3/11 w2:2/7 w3:2/6 w4:6/13 w5:5/7 w6:4/5
    SHORT     adx_di_cross + momentum + adx>20  56 44.6       32.4        27.3     1.56           w0:3/7 w1:3/11 w2:2/7 w3:2/6 w4:6/13 w5:5/7 w6:4/5
    SHORT    mech_trigger + cusum_2.0 + adx>20  65 43.1       31.8        15.4     1.60          w0:2/8 w1:5/8 w2:9/12 w3:4/13 w4:2/13 w5:1/3 w6:5/8
     LONG     vidya_dmi + cusum_1.5 + poc_side  34 47.1       31.5         0.0     0.82             w0:3/3 w1:6/7 w2:3/6 w3:2/4 w4:0/5 w5:0/5 w6:2/4
    SHORT                vidya_dmi + cusum_1.5  34 47.1       31.5        16.7     0.85             w0:1/2 w1:2/3 w2:2/3 w3:1/6 w4:3/8 w5:3/6 w6:4/6
     LONG               vidya_dmi + cusum_1.75  34 47.1       31.5         0.0     0.87             w0:3/4 w1:4/6 w2:2/6 w3:4/4 w4:0/4 w5:1/6 w6:2/4
    SHORT                vidya_dmi + cusum_1.5  34 47.1       31.5        16.7     0.85             w0:1/2 w1:2/3 w2:2/3 w3:1/6 w4:3/8 w5:3/6 w6:4/6
     LONG               vidya_dmi + cusum_1.25  40 45.0       30.7         0.0     1.02            w0:2/4 w1:7/10 w2:3/7 w3:3/3 w4:0/7 w5:1/6 w6:2/3
    SHORT               vidya_dmi + cusum_1.25  40 45.0       30.7        16.7     0.95             w0:1/2 w1:2/3 w2:3/6 w3:1/6 w4:4/9 w5:4/7 w6:3/7
    SHORT               vidya_dmi + cusum_1.75  35 45.7       30.5        16.7     0.85             w0:1/3 w1:3/4 w2:2/4 w3:1/6 w4:3/8 w5:2/5 w6:4/5
     LONG                vidya_dmi + cusum_2.0  31 45.2       29.2         0.0     0.85             w0:3/5 w1:4/6 w2:1/4 w3:3/3 w4:0/4 w5:1/5 w6:2/4
    SHORT                vidya_dmi + cusum_2.0  34 44.1       28.9        20.0     0.87             w0:1/1 w1:3/4 w2:1/3 w3:1/5 w4:3/9 w5:2/5 w6:4/7
    SHORT                   poc_cross + adx>35  11 54.5       28.0        33.3     0.24                                         w2:2/4 w4:1/3 w6:3/4
    SHORT   adx_di_cross + momentum + adx>22.5  42 40.5       27.0        16.7     1.11             w0:3/5 w1:3/9 w2:1/6 w3:2/6 w4:2/7 w5:3/5 w6:3/4
    SHORT      scalp_bias + vol_burst + adx>20  44 38.6       25.7        20.0     1.21            w0:1/4 w1:1/3 w2:4/8 w3:3/12 w4:1/5 w5:4/8 w6:3/4
    SHORT                   poc_cross + adx>30  27 40.7       24.5        33.3     0.61             w0:0/2 w1:3/5 w2:2/6 w3:0/2 w4:1/3 w5:0/2 w6:5/7
    SHORT                   poc_cross + adx>30  27 40.7       24.5        33.3     0.61             w0:0/2 w1:3/5 w2:2/6 w3:0/2 w4:1/3 w5:0/2 w6:5/7
     LONG liquidity_sweep + cusum_1.0 + adx>15  50 36.0       24.1        14.3     1.30           w0:5/6 w1:1/5 w2:2/7 w3:3/7 w4:0/1 w5:2/14 w6:5/10
     LONG                   poc_cross + adx>35  13 46.2       23.2        25.0     0.30                    w1:1/1 w2:1/2 w3:0/1 w4:1/3 w5:2/2 w6:1/4
    SHORT                 poc_cross + adx>32.5  19 42.1       23.1        33.3     0.43             w0:0/2 w1:1/2 w2:2/5 w3:0/1 w4:1/3 w5:0/1 w6:4/5
    SHORT     adx_di_cross + momentum + adx>25  31 35.5       21.1        20.0     0.80             w0:3/4 w1:2/6 w2:1/5 w3:1/5 w4:1/5 w5:1/3 w6:2/3
     LONG                vidya_dmi + cusum_2.5  26 34.6       19.4         0.0     0.69             w0:1/3 w1:3/5 w2:0/2 w3:2/3 w4:0/7 w5:2/5 w6:1/1
    SHORT               vidya_dmi + cusum_2.25  38 31.6       19.1        20.0     0.93             w0:1/2 w1:2/4 w2:1/4 w3:1/5 w4:2/9 w5:3/7 w6:2/7
    SHORT                vidya_dmi + cusum_2.5  31 32.3       18.6        25.0     0.78             w0:1/4 w1:1/3 w2:1/3 w3:1/4 w4:2/7 w5:2/5 w6:2/5

## Survivors (acc≥74, wilsonLB≥55, worst fold≥50, n≥12)

_(none)_

## OR-ensembles of survivors (fire when ANY member fires)

- LONG: no survivors to ensemble
- SHORT: no survivors to ensemble