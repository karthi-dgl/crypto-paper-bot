"""
Forward-test logger: records every AI signal, then scores it against what BTC
actually did. NO real orders - this is the honest 3-4 week validation.

  python signal_logger.py           # leave running: auto-checks every 15 min in session
  python signal_logger.py --once    # single check, then exit (for Task Scheduler)
  python signal_logger.py --report  # scorecard: how is the AI doing forward?
"""
import csv
import os
import pickle
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from features import build_features, SL_ATR

IST = ZoneInfo("Asia/Kolkata")
LOG = "signals.csv"
SESSION_START, SESSION_END = "17:30", "23:30"
TP1_R, TP2_R, TRAIL_ATR = 1.5, 3.0, 2.2
HORIZON = 32                      # score after 8h
RISK, USDINR, LOT = 500, 87.0, 0.001
FEE_MAKER, FEE_TAKER = 0.0002 * 1.18, 0.0005 * 1.18
PHASES = {0: "chop", 1: "trend-up", 2: "trend-down", 3: "accumulation", 4: "distribution"}
COLS = ["time", "epoch", "price", "atr", "phase", "p_long", "p_short", "p_none",
        "edge", "decision", "sl", "tp1", "tp2", "outcome", "pnl"]


def margin():
    try:
        return float(open("threshold.txt").read().strip())
    except FileNotFoundError:
        return 0.10


def fetch(days=30):
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
    return pd.DataFrame(rows)[["time", "open", "high", "low", "close", "volume"]].astype(float)


def load_log():
    if not os.path.exists(LOG):
        return []
    with open(LOG) as f:
        return list(csv.DictReader(f))


def save_log(rows):
    with open(LOG, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)


def decide(df, models, cols):
    X, meta = build_features(df)
    i = len(X) - 2                                # last closed bar
    x = X.iloc[[i]][cols].fillna(0)
    proba = np.mean([m.predict_proba(x)[0] for m in models], axis=0)
    p = {int(c): proba[k] for k, c in enumerate(models[0].classes_)}
    pn, pl, ps = p.get(0, 0), p.get(1, 0), p.get(2, 0)
    conf, edge = max(pl, ps), max(pl, ps) - pn
    price, a = meta.close.iloc[i], meta.atr.iloc[i]
    side = "BUY" if pl >= ps else "SELL"
    d = 1 if side == "BUY" else -1
    take = edge >= margin()
    sl_d = SL_ATR * a
    return {"time": str(datetime.now(IST))[:16], "epoch": int(meta.time.iloc[i]),
            "price": round(price, 1), "atr": round(a, 1),
            "phase": PHASES[int(meta.phase.iloc[i])],
            "p_long": round(pl, 3), "p_short": round(ps, 3), "p_none": round(pn, 3),
            "edge": round(edge, 3), "decision": side if take else "FLAT",
            "sl": round(price - d * sl_d, 1) if take else "",
            "tp1": round(price + d * TP1_R * sl_d, 1) if take else "",
            "tp2": round(price + d * TP2_R * sl_d, 1) if take else "",
            "outcome": "" if take else "-", "pnl": "" if take else "0"}


def score_pending(rows, df):
    """Simulate bracket outcome for unscored signals whose 8h window has passed."""
    h, l, t = df.high.values, df.low.values, df.time.values
    for r in rows:
        if r["decision"] == "FLAT" or r["outcome"]:
            continue
        idx = np.searchsorted(t, float(r["epoch"]), side="right")
        if len(t) - idx < HORIZON + 1:
            continue                                       # window not finished yet
        d = 1 if r["decision"] == "BUY" else -1
        entry, a = float(r["price"]), float(r["atr"])
        sl, tp1, tp2 = float(r["sl"]), float(r["tp1"]), float(r["tp2"])
        lots = max(int(RISK // (SL_ATR * a * LOT * USDINR)), 2)
        half = lots // 2
        pnl = -entry * lots * LOT * USDINR * FEE_MAKER
        half_done, extreme, out = False, entry, "TIMEOUT"
        for j in range(idx, idx + HORIZON):
            extreme = max(extreme, h[j]) if d == 1 else min(extreme, l[j])
            if (l[j] <= sl if d == 1 else h[j] >= sl):
                lots_left = lots - half if half_done else lots
                px = sl - d * 0.5
                pnl += d * (px - entry) * lots_left * LOT * USDINR - px * lots_left * LOT * USDINR * FEE_TAKER
                out = "BE/TRAIL" if half_done else "SL"
                break
            if not half_done and (h[j] >= tp1 if d == 1 else l[j] <= tp1):
                pnl += d * (tp1 - entry) * half * LOT * USDINR - tp1 * half * LOT * USDINR * FEE_MAKER
                half_done, sl = True, entry
            if half_done:
                trail = extreme - d * TRAIL_ATR * a
                sl = max(sl, trail) if d == 1 else min(sl, trail)
            if half_done and (h[j] >= tp2 if d == 1 else l[j] <= tp2):
                pnl += d * (tp2 - entry) * (lots - half) * LOT * USDINR - tp2 * (lots - half) * LOT * USDINR * FEE_MAKER
                out = "TP2"
                break
        else:
            j = idx + HORIZON - 1
            lots_left = lots - half if half_done else lots
            px = df.close.values[j]
            pnl += d * (px - entry) * lots_left * LOT * USDINR - px * lots_left * LOT * USDINR * FEE_TAKER
        r["outcome"], r["pnl"] = out, str(round(pnl))
    return rows


def report():
    rows = load_log()
    taken = [r for r in rows if r["decision"] != "FLAT"]
    scored = [r for r in taken if r["outcome"] and r["outcome"] != "-"]
    print(f"Signals logged: {len(rows)} | trades signalled: {len(taken)} | scored: {len(scored)}")
    if not scored:
        print("Nothing scored yet - signals need 8h to mature.")
        return
    pnl = np.array([float(r["pnl"]) for r in scored])
    wins = pnl[pnl > 0]
    pf = wins.sum() / abs(pnl[pnl <= 0].sum()) if (pnl <= 0).any() and pnl[pnl <= 0].sum() else float("inf")
    print(f"\n=== FORWARD SCORECARD (paper, Rs500 risk/trade) ===")
    print(f"Win rate:      {len(wins) / len(pnl):.0%}")
    print(f"Net P&L:       Rs{pnl.sum():+,.0f}")
    print(f"Profit factor: {pf:.2f}   (backtest tune-half expectation: ~1.4-1.6)")
    print(f"Avg/trade:     Rs{pnl.mean():+,.0f}")
    by_out = {}
    for r in scored:
        by_out.setdefault(r["outcome"], []).append(float(r["pnl"]))
    print("\nBy outcome: " + "  ".join(f"{k}: {len(v)} (Rs{sum(v):+,.0f})" for k, v in by_out.items()))
    print("\nVerdict: PF > 1.3 after 3-4 weeks -> wire to testnet executor. PF < 1.1 -> back to research.")


def check_once(models, cols):
    df = fetch()
    rows = load_log()
    rows = score_pending(rows, df)
    sig = decide(df, models, cols)
    if rows and rows[-1]["epoch"] == str(sig["epoch"]):
        save_log(rows)                                   # bar already logged, just rescore
        return rows[-1]
    rows.append({k: str(v) for k, v in sig.items()})
    save_log(rows)
    print(f"[{sig['time']}] {sig['decision']:5s} @ ${sig['price']:,} "
          f"edge {float(sig['edge']):+.1%} phase {sig['phase']}")
    return sig


def in_session(now):
    return SESSION_START <= now.strftime("%H:%M") <= SESSION_END


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
        sys.exit()
    with open("model.pkl", "rb") as fh:
        b = pickle.load(fh)
    models = b["model"] if isinstance(b["model"], list) else [b["model"]]
    cols = b["features"]
    if "--once" in sys.argv:
        check_once(models, cols)
        sys.exit()
    print(f"Signal logger running (margin {margin():.3f}). Session {SESSION_START}-{SESSION_END} IST. Ctrl+C to stop.")
    while True:
        try:
            if in_session(datetime.now(IST)):
                check_once(models, cols)
            time.sleep(900 - int(time.time()) % 900 + 10)
        except KeyboardInterrupt:
            print("Stopped.")
            break
        except Exception as e:
            print(f"error: {e} - retry in 60s")
            time.sleep(60)
