"""
Simulate Rs 50,000 trading the AI's out-of-sample predictions (honest months only).

The confidence threshold is tuned on the FIRST half of the unseen data and the
final verdict is given on the SECOND half (data neither the model nor the
threshold has ever seen). Usage:  python backtest_ai.py
"""
import numpy as np
import pandas as pd

CAPITAL = 50_000
RISK = 500                  # 1%
USDINR = 87.0
LOT = 0.001
FEE_MAKER = 0.0002 * 1.18
FEE_TAKER = 0.0005 * 1.18
SLIP = 0.5                  # 1 tick slippage on stop exits
SL_ATR = 1.2
TP1_R, TP2_R = 1.5, 3.0
TRAIL_ATR = 2.2
MAX_TRADES_DAY = 3
DAY_STOP = -0.02 * CAPITAL
PHASES = {0: "chop", 1: "trend-up", 2: "trend-down", 3: "accumulation", 4: "distribution"}


def simulate(df, thresh):
    trades = []
    i, n = 0, len(df)
    t = pd.to_datetime(df.time, unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
    day = t.dt.date.values
    h, l, c, a = df.high.values, df.low.values, df.close.values, df.atr.values
    pl, ps, pn = df.p_long.values, df.p_short.values, df.p_none.values
    cur_day, n_day, pnl_day = None, 0, 0.0

    while i < n - 2:
        if day[i] != cur_day:
            cur_day, n_day, pnl_day = day[i], 0, 0.0
        side = 1 if pl[i] >= ps[i] else -1
        conf = max(pl[i], ps[i])
        edge = conf - pn[i]                 # v2: confidence must BEAT "no-edge" prob
        if edge < thresh or n_day >= MAX_TRADES_DAY or pnl_day <= DAY_STOP or not a[i] > 0:
            i += 1
            continue

        entry, atr0 = c[i], a[i]
        sl_d = SL_ATR * atr0
        sl = entry - side * sl_d
        tp1 = entry + side * TP1_R * sl_d
        tp2 = entry + side * TP2_R * sl_d
        lots = int(RISK // (sl_d * LOT * USDINR))
        if lots < 2:
            i += 1
            continue
        half = lots // 2
        pnl = -entry * lots * LOT * USDINR * FEE_MAKER          # entry fee (maker)
        half_done, extreme = False, entry
        j = i + 1
        while j < n and day[j] == day[i + 1]:                    # manage same/next day only
            extreme = max(extreme, h[j]) if side == 1 else min(extreme, l[j])
            hit_sl = l[j] <= sl if side == 1 else h[j] >= sl
            hit_tp1 = (h[j] >= tp1 if side == 1 else l[j] <= tp1) and not half_done
            hit_tp2 = (h[j] >= tp2 if side == 1 else l[j] <= tp2) and half_done
            if hit_sl:
                lots_left = lots - half if half_done else lots
                px = sl - side * SLIP
                pnl += side * (px - entry) * lots_left * LOT * USDINR
                pnl -= px * lots_left * LOT * USDINR * FEE_TAKER
                break
            if hit_tp1:
                pnl += side * (tp1 - entry) * half * LOT * USDINR
                pnl -= tp1 * half * LOT * USDINR * FEE_MAKER
                half_done, sl = True, entry                       # breakeven
            if half_done:                                         # chandelier trail
                trail = extreme - side * TRAIL_ATR * atr0
                sl = max(sl, trail) if side == 1 else min(sl, trail)
            if hit_tp2:
                pnl += side * (tp2 - entry) * (lots - half) * LOT * USDINR
                pnl -= tp2 * (lots - half) * LOT * USDINR * FEE_MAKER
                break
            j += 1
        else:                                                     # time exit end of day
            j = min(j, n - 1)
            lots_left = lots - half if half_done else lots
            pnl += side * (c[j] - entry) * lots_left * LOT * USDINR
            pnl -= c[j] * lots_left * LOT * USDINR * FEE_TAKER

        pnl_day += pnl
        n_day += 1
        trades.append({"time": str(t.iloc[i]), "month": str(t.iloc[i])[:7],
                       "side": "BUY" if side == 1 else "SELL", "conf": round(conf, 3),
                       "entry": entry, "pnl": pnl, "phase": PHASES[int(df.phase.values[i])],
                       "hour": int(str(t.iloc[i])[11:13])})
        i = j + 1
    return pd.DataFrame(trades)


def stats(tr):
    if tr.empty:
        return dict(trades=0, pnl=0, wr=0, pf=0, dd=0)
    eq = CAPITAL + tr.pnl.cumsum()
    peak = eq.cummax()
    dd = ((peak - eq) / peak).max()
    wins, losses = tr.pnl[tr.pnl > 0], tr.pnl[tr.pnl <= 0]
    pf = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() else float("inf")
    return dict(trades=len(tr), pnl=tr.pnl.sum(), wr=len(wins) / len(tr),
                pf=pf, dd=dd, final=eq.iloc[-1])


if __name__ == "__main__":
    df = pd.read_csv("oos_predictions.csv")
    mid = len(df) // 2
    tune, test = df.iloc[:mid], df.iloc[mid:]

    print("Tuning edge margin (confidence minus no-edge prob) on first half of unseen data:")
    best, best_pnl = None, -1e18
    for th in np.arange(0.00, 0.40, 0.025):
        s = stats(simulate(tune, th))
        flag = ""
        if s["trades"] >= 30 and s["pnl"] > best_pnl:
            best, best_pnl, flag = th, s["pnl"], "  <-- best"
        print(f"  margin {th:.3f}: {s['trades']:4d} trades  Rs{s['pnl']:+10,.0f}  "
              f"wr {s['wr']:.0%}  pf {s['pf']:.2f}  dd {s['dd']:.0%}{flag}")
    if best is None:
        raise SystemExit("No margin produced >=30 trades. Fetch more data.")

    with open("threshold.txt", "w") as fh:
        fh.write(f"{best:.2f}")
    print(f"\n===== FINAL VERDICT (second half, margin {best:.3f}, fully unseen) =====")
    tr = simulate(test, best)
    s = stats(tr)
    months = max(tr.month.nunique(), 1) if not tr.empty else 1
    print(f"Trades:        {s['trades']}  (~{s['trades'] / months:.0f}/month)")
    print(f"Win rate:      {s['wr']:.1%}   Profit factor: {s['pf']:.2f}")
    print(f"Net P&L:       Rs{s['pnl']:+,.0f}  ({s['pnl'] / CAPITAL * 100:+.1f}%)")
    print(f"Final equity:  Rs{s.get('final', CAPITAL):,.0f}  (from Rs{CAPITAL:,})")
    print(f"Max drawdown:  {s['dd']:.1%}")
    if not tr.empty:
        print("\nBy month:")
        print(tr.groupby("month").pnl.agg(["count", "sum"]).rename(
            columns={"count": "trades", "sum": "P&L Rs"}).round(0).to_string())
        print("\nBy market phase (where does the AI make money?):")
        print(tr.groupby("phase").pnl.agg(["count", "sum"]).rename(
            columns={"count": "trades", "sum": "P&L Rs"}).round(0).to_string())
        print("\nBy side:")
        print(tr.groupby("side").pnl.agg(["count", "sum"]).round(0).to_string())
        tr.to_csv("ai_trades.csv", index=False)
        print("\nTrade log -> ai_trades.csv")
