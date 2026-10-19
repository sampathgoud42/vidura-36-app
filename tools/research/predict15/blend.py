import json, math, sys
from pathlib import Path
import numpy as np, pandas as pd
D = Path(sys.argv[1])
def ncdf(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
for coin in ("BTC","ETH"):
    m = pd.read_csv(D/f"{coin}_markets.csv", parse_dates=["open_time","close_time"])
    m = m[m["result"].isin(["yes","no"])].sort_values("open_time")
    m = m[m["open_time"] >= m["open_time"].max()-pd.Timedelta(days=7)]
    b = pd.read_csv(D/f"{coin}_1m.csv", parse_dates=["t"]).set_index("t").sort_index(); b=b[~b.index.duplicated()]
    b = b.reindex(pd.date_range(b.index.min(), b.index.max(), freq="1min")).ffill()
    vol = np.log(b["close"]).diff().rolling(60).std()
    q = json.loads((D/f"{coin}_quotes.json").read_text())
    print(f"\n=== {coin} ===")
    for k in (1,2,3,5,8):
        Y=[];PM=[];PK=[]
        for r in m.itertuples():
            qq=q.get(r.ticker,{}).get(str(k)); tk=r.open_time+pd.Timedelta(minutes=k-1)
            if not qq or None in qq or tk not in b.index: continue
            a,bd=qq
            if not (0<bd<=a<1): continue
            s=vol[r.open_time-pd.Timedelta(minutes=1)]*math.sqrt(15-k)
            if not s or math.isnan(s): continue
            PM.append(ncdf(math.log(b["close"][tk]/r.strike)/s)); PK.append((a+bd)/2); Y.append(r.result=="yes")
        Y=np.array(Y); PM=np.clip(PM,.02,.98); PK=np.clip(PK,.02,.98)
        def st(p): 
            acc=((p>=.5)==Y).mean(); ll=-(Y*np.log(p)+(1-Y)*np.log(1-p)).mean(); return f"acc={acc:.3f} logloss={ll:.4f}"
        print(f" T+{k}m n={len(Y)}  model {st(PM)} | kalshi mid {st(PK)} | 50/50 blend {st((PM+PK)/2)} | 25/75 {st(.25*PM+.75*PK)}")
