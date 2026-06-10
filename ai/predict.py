"""
Ask the AI: what trade should I take RIGHT NOW?

Usage:  python predict.py          (fetches live candles, prints the decision)
"""
import pickle
import time

import pandas as pd
import requests

from features import build_features, SL_ATR

try:                  # edge margin chosen by backtest_ai.py (threshold.txt)
    MARGIN = float(open("threshold.txt").read().strip())
except FileNotFoundError:
    MARGIN = 0.10
CAPITAL = 50_000
RISK = 500
USDINR = 87.0
LOT = 0.001
PHASES = {0: "chop / no-man's-land", 1: "TREND UP (markup)", 2: "TREND DOWN (markdown)",
          3: "ACCUMULATION (range after decline)", 4: "DISTRIBUTION (range after rally)"}


def fetch_recent(days=30):
    end = int(time.time())
    out, s = [], end - days * 86400
    while s < end:
        e = min(s + 7 * 86400, end)
        r = requests.get("https://api.india.delta.exchange/v2/history/candles",
                         params={"resolution": "15m", "symbol": "BTCUSD",
                                 "start": s, "end": e}, timeout=20)
        out += r.json()["result"]
        s = e
    seen, rows = set(), []
    for c in sorted(out, key=lambda x: x["time"]):
        if c["time"] not in seen:
            seen.add(c["time"])
            rows.append(c)
    return pd.DataFrame(rows)[["time", "open", "high", "low", "close", "volume"]]


if __name__ == "__main__":
    import numpy as np
    with open("model.pkl", "rb") as fh:
        bundle = pickle.load(fh)
    models, cols = bundle["model"], bundle["features"]
    if not isinstance(models, list):
        models = [models]

    df = fetch_recent()
    X, meta = build_features(df)
    i = len(X) - 2                              # last CLOSED bar
    x = X.iloc[[i]][cols].fillna(0)
    proba = np.mean([m.predict_proba(x)[0] for m in models], axis=0)
    p = {int(c): proba[k] for k, c in enumerate(models[0].classes_)}
    p_none, p_long, p_short = p.get(0, 0), p.get(1, 0), p.get(2, 0)

    price, atr0 = meta.close.iloc[i], meta.atr.iloc[i]
    phase = PHASES[int(meta.phase.iloc[i])]
    side = "BUY" if p_long >= p_short else "SELL"
    conf = max(p_long, p_short)
    edge = conf - p_none                 # v2: must beat the no-edge probability

    print("=" * 58)
    print(f" BTC @ ${price:,.0f}   |   market phase: {phase}")
    print(f" AI confidence:  LONG {p_long:.1%}   SHORT {p_short:.1%}   NO-EDGE {p_none:.1%}")
    print("=" * 58)
    if edge < MARGIN:
        print(f" DECISION: STAY FLAT (edge {edge:+.1%} < {MARGIN:.1%} required margin)")
        print(" Not trading is a position. Wait for a better setup.")
    else:
        d = 1 if side == "BUY" else -1
        sl_d = SL_ATR * atr0
        lots = int(RISK // (sl_d * LOT * USDINR))
        print(f" DECISION: {side}  (confidence {conf:.1%})")
        print(f"   Size:   {lots} lots ({lots * LOT:.3f} BTC) — risks Rs{lots * sl_d * LOT * USDINR:,.0f} of Rs{CAPITAL:,}")
        print(f"   Entry:  ${price:,.1f}  (limit order)")
        print(f"   SL:     ${price - d * sl_d:,.1f}  (1.2 x ATR)")
        print(f"   TP1:    ${price + d * 1.5 * sl_d:,.1f}  -> close half, SL to breakeven")
        print(f"   TP2:    ${price + d * 3.0 * sl_d:,.1f}  -> close rest")
        print(f"   Trail:  after TP1, chandelier 2.2 x ATR = ${2.2 * atr0:,.0f} behind best price")
    print("=" * 58)
