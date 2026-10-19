"""predict-15 research: what, if anything, calls a Kalshi 15-minute up/down market."""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(sys.argv[1])
SQ2 = math.sqrt(2)


def ncdf(x):
    return 0.5 * (1 + np.vectorize(math.erf)(np.asarray(x) / SQ2))


def load(coin):
    m = pd.read_csv(D / f"{coin}_markets.csv", parse_dates=["open_time", "close_time"])
    m = m[m["result"].isin(["yes", "no"])].sort_values("open_time").reset_index(drop=True)
    b = pd.read_csv(D / f"{coin}_1m.csv", parse_dates=["t"]).set_index("t").sort_index()
    b = b[~b.index.duplicated()]
    b = b.reindex(pd.date_range(b.index.min(), b.index.max(), freq="1min")).ffill()
    return m, b


def features(m, b, other_b):
    lc = np.log(b["close"])
    olc = np.log(other_b["close"])
    r1 = lc.diff()
    vol60 = r1.rolling(60).std()
    rsi_up = r1.clip(lower=0).rolling(14).mean(); rsi_dn = (-r1.clip(upper=0)).rolling(14).mean()
    rsi = 100 - 100 / (1 + rsi_up / rsi_dn.replace(0, np.nan))
    z60 = (b["close"] - b["close"].rolling(60).mean()) / b["close"].rolling(60).std()
    vr = b["volume"].rolling(15).mean() / b["volume"].rolling(60).mean()
    rows = []
    prev = None
    for i, row in m.iterrows():
        t0 = row["open_time"] - pd.Timedelta(minutes=1)   # the last full bar BEFORE the open
        if t0 not in lc.index or t0 - pd.Timedelta(minutes=61) not in lc.index:
            prev = row["result"]; continue
        f = {"y": int(row["result"] == "yes"), "open_time": row["open_time"],
             "strike": row["strike"], "final": row["final"]}
        for k in (1, 5, 15, 30, 60):
            f[f"r{k}"] = lc[t0] - lc[t0 - pd.Timedelta(minutes=k)]
        f["o15"] = olc[t0] - olc[t0 - pd.Timedelta(minutes=15)]
        f["vol60"] = vol60[t0]; f["rsi"] = rsi[t0]; f["z60"] = z60[t0]; f["vr"] = vr[t0]
        f["prev_yes"] = 1 if prev == "yes" else 0 if prev == "no" else np.nan
        h = row["open_time"].hour + row["open_time"].minute / 60
        f["hs"], f["hc"] = math.sin(2 * math.pi * h / 24), math.cos(2 * math.pi * h / 24)
        # in-window: Coinbase close k minutes after the open, against the strike
        for k in (1, 2, 3, 5, 8, 10):
            tk = row["open_time"] + pd.Timedelta(minutes=k - 1)  # bar ending at open+k
            f[f"in{k}"] = b["close"].get(tk, np.nan)
        rows.append(f)
        prev = row["result"]
    return pd.DataFrame(rows).dropna(subset=["r60", "vol60", "rsi", "z60", "prev_yes"])


def logit_fit(X, y, l2=1.0, iters=300):
    X = np.c_[np.ones(len(X)), X]; w = np.zeros(X.shape[1])
    for _ in range(iters):                     # Newton / IRLS with a ridge
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (p - y) + l2 * np.r_[0, w[1:]]
        H = (X * (p * (1 - p))[:, None]).T @ X + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        w -= np.linalg.solve(H, g)
    return w


def logit_pred(w, X):
    return 1 / (1 + np.exp(-(np.c_[np.ones(len(X)), X] @ w)))


def auc(y, p):
    order = np.argsort(p); y = np.asarray(y)[order]
    n1 = y.sum(); n0 = len(y) - n1
    return (np.arange(1, len(y) + 1)[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def report(name, y, p):
    y = np.asarray(y); p = np.clip(np.asarray(p), 1e-4, 1 - 1e-4)
    acc = ((p >= 0.5) == y).mean()
    ll = -(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()
    brier = ((p - y) ** 2).mean()
    conf = np.abs(p - 0.5) >= 0.1
    cacc = ((p[conf] >= 0.5) == y[conf]).mean() if conf.any() else float("nan")
    se = math.sqrt(0.25 / len(y))
    print(f"  {name:34s} n={len(y):4d} acc={acc:.3f} (±{1.96*se:.3f}) AUC={auc(y, p):.3f} "
          f"logloss={ll:.4f} (coin 0.6931) brier={brier:.4f} | p≥.6/≤.4: n={conf.sum()} acc={cacc:.3f}")


FEATS = ["r1", "r5", "r15", "r30", "r60", "o15", "vol60", "rsi", "z60", "vr", "prev_yes", "hs", "hc"]
data = {c: load(c) for c in ("BTC", "ETH")}
for coin, other in (("BTC", "ETH"), ("ETH", "BTC")):
    m, b = data[coin]
    f = features(m, b, data[other][1])
    print(f"\n=== {coin}: {len(f)} markets, base YES {f['y'].mean():.3f} ===")
    # --- A. simple rules at the open
    print(" A. at the open (no peeking):")
    for k in ("r1", "r5", "r15", "r60"):
        report(f"momentum sign {k}", f["y"], np.where(f[k] > 0, 0.55, 0.45))
    report("prev result repeats", f["y"], np.where(f["prev_yes"] == 1, 0.55, 0.45))
    report("mean reversion z60", f["y"], np.where(f["z60"] > 0, 0.45, 0.55))
    # walk-forward logistic: train first 60%, test the rest
    cut = int(len(f) * 0.6)
    X = f[FEATS].to_numpy(float); mu, sd = X[:cut].mean(0), X[:cut].std(0) + 1e-12
    Xs = (X - mu) / sd
    w = logit_fit(Xs[:cut], f["y"].to_numpy()[:cut], l2=5.0)
    report("logistic, all features (test 40%)", f["y"].to_numpy()[cut:], logit_pred(w, Xs[cut:]))
    print("    weights:", {n: round(v, 3) for n, v in zip(["b"] + FEATS, w)})
    # --- B. in the window: P(final >= strike) from where price is now
    print(" B. inside the window (price vs strike, sigma from the last hour):")
    for k in (1, 2, 3, 5, 8, 10):
        s = f[f"in{k}"].to_numpy(float); K = f["strike"].to_numpy(float)
        sig = f["vol60"].to_numpy(float) * math.sqrt(15 - k)
        p = ncdf(np.log(s / K) / sig)
        ok = ~np.isnan(p)
        report(f"at T+{k}m  N(ln(S/K)/σ√τ)", f["y"].to_numpy()[ok], p[ok])
    # calibration at T+5
    s = f["in5"].to_numpy(float); K = f["strike"].to_numpy(float)
    p = ncdf(np.log(s / K) / (f["vol60"].to_numpy(float) * math.sqrt(10)))
    bins = pd.cut(p, [0, .1, .3, .45, .55, .7, .9, 1.0])
    cal = pd.DataFrame({"p": p, "y": f["y"]}).groupby(bins, observed=True).agg(n=("y", "size"), predicted=("p", "mean"), actual=("y", "mean"))
    print("  calibration at T+5m:\n" + cal.round(3).to_string())
