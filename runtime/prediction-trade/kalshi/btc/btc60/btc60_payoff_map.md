# Kalshi payoff map — surviving signals, 46 days BTC-USD 5m
- bars 13265, 2026-05-26 00:00:00+00:00 → 2026-07-11 02:50:00+00:00
- fwd30 = signed forward 30-min move in signal direction (info content)
- ftX_Y = first-touch +X before −Y within 30 min (%)  — ft100_50 is the
  2:1 asymmetric barrier that maps to 'buy ~35c near-money, sell ~70c'
- timeout% = neither barrier (time-stop, ≈ scratch)

direction                      signal   n  per_day  fwd30_mean  fwd30_med  ft100_100  ft100_50  timeout%  lb_100_50                                             folds_100_50  ft80_40  ft150_75
    SHORT  mom3_60+poc_cross+near_lvl  79     1.71        23.8       10.4       58.0      39.7       1.3       29.6      w0:6/9 w1:4/8 w2:3/9 w3:4/17 w4:4/16 w5:6/10 w6:4/9     39.7      40.8
    SHORT            sqz_break+di_dom  93     2.02        -4.0      -13.5       64.1      38.9       3.2       29.5   w0:3/12 w1:9/21 w2:6/16 w3:2/5 w4:3/14 w5:7/11 w6:5/11     35.9      37.5
    SHORT                   sqz_break  97     2.10        -5.0      -13.5       63.0      38.7       4.1       29.4   w0:4/13 w1:9/22 w2:6/17 w3:2/5 w4:3/14 w5:7/11 w6:5/11     35.8      36.5
     LONG adx_di_cross+momentum+adx20  56     1.21        64.5       56.4       58.7      37.3       8.9       25.3        w0:1/5 w1:5/7 w2:1/3 w3:3/9 w4:4/13 w5:3/9 w6:2/5     43.4      46.3
     LONG       adx_di_cross+momentum 145     3.14        32.6       18.6       54.1      36.8       6.2       29.1 w0:4/15 w1:7/14 w2:5/15 w3:14/24 w4:11/41 w5:5/18 w6:4/9     37.1      36.6
    SHORT           mom3_60+poc_cross 161     3.49        -1.2        3.9       53.9      36.1       1.9       29.0 w0:9/19 w1:8/18 w2:5/17 w3:5/25 w4:8/37 w5:14/24 w6:8/18     36.1      37.3
     LONG             poc_cross+adx30  38     0.82       117.2       98.2       62.9      36.1       5.3       22.5         w0:4/5 w1:3/7 w2:2/7 w3:1/3 w4:1/5 w5:1/2 w6:1/7     35.1      41.9
    SHORT           poc_cross+adx27.5  47     1.02       -40.5      -30.1       48.8      35.6       4.3       23.2        w0:0/2 w1:3/8 w2:2/8 w3:0/4 w4:3/7 w5:2/5 w6:6/11     32.6      35.9
     LONG                   sqz_break  89     1.93        20.0       28.9       58.5      32.4      16.9       22.9    w0:1/11 w1:4/12 w2:4/15 w3:5/10 w4:8/13 w5:1/4 w6:1/9     31.7      37.9
     LONG          vidya_dmi+cusum1.5  65     1.41        15.6      -22.6       39.3      23.7       9.2       14.7      w0:3/6 w1:4/11 w2:2/10 w3:3/8 w4:0/8 w5:0/10 w6:2/6     21.0      31.5

## EV illustration (per contract, ft100_50 barrier)
buy at 35c: EV = p*0.65 − (1−p)*0.35 − fees  → breakeven p ≈ 36%
buy at 45c: EV = p*0.55 − (1−p)*0.45 − fees  → breakeven p ≈ 46%