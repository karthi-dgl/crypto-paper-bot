"""
Paper-trading engine. The AI decides, this records — no real money, no API keys.

Designed to run unattended (GitHub Actions, every 15 min in session hours):
each run it (1) updates open paper trades against fresh candles, (2) asks the
AI for a new trade if flat, (3) stores everything in paper_trades.db, and
(4) regenerates the dashboard at ../docs/index.html.

Run manually:  python engine.py
"""
import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

import make_dashboard
from signal_logger import (FEE_MAKER, FEE_TAKER, HORIZON, LOT, RISK,
                           TRAIL_ATR, USDINR, decide, fetch, in_session)
from features import SL_ATR

IST = ZoneInfo("Asia/Kolkata")
HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "paper_trades.db")
CAPITAL = 50_000
MAX_TRADES_DAY = 3
DAY_STOP = -0.02 * CAPITAL
SLIP = 0.5

SCHEMA = """CREATE TABLE IF NOT EXISTS trades(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  open_epoch INTEGER, open_time TEXT, side TEXT, lots INTEGER,
  entry REAL, sl REAL, tp1 REAL, tp2 REAL, atr REAL,
  edge REAL, phase TEXT, notional_inr REAL,
  status TEXT DEFAULT 'OPEN',
  close_epoch INTEGER, close_time TEXT, exit_price REAL, outcome TEXT,
  gross_pnl REAL, fees REAL, net_pnl REAL)"""


def ist(epoch):
    return datetime.fromtimestamp(epoch, IST).strftime("%Y-%m-%d %H:%M")


def manage_open(con, df):
    """Replay candles since entry for every OPEN trade; close if bracket resolved."""
    h, l, c, t = df.high.values, df.low.values, df.close.values, df.time.values
    for tr in con.execute("SELECT * FROM trades WHERE status='OPEN'").fetchall():
        tr = dict(tr)
        d = 1 if tr["side"] == "BUY" else -1
        idx = np.searchsorted(t, tr["open_epoch"], side="right")
        entry, sl, tp1, tp2, a = (tr["entry"], tr["sl"], tr["tp1"], tr["tp2"], tr["atr"])
        lots, half = tr["lots"], tr["lots"] // 2
        gross, fees = 0.0, entry * lots * LOT * USDINR * FEE_MAKER
        half_done, extreme = False, entry
        exit_px = outcome = close_ep = None
        for j in range(idx, min(idx + HORIZON, len(t))):
            extreme = max(extreme, h[j]) if d == 1 else min(extreme, l[j])
            if (l[j] <= sl if d == 1 else h[j] >= sl):
                lots_left = lots - half if half_done else lots
                px = sl - d * SLIP
                gross += d * (px - entry) * lots_left * LOT * USDINR
                fees += px * lots_left * LOT * USDINR * FEE_TAKER
                exit_px, outcome, close_ep = px, ("BE/TRAIL" if half_done else "SL"), t[j]
                break
            if not half_done and (h[j] >= tp1 if d == 1 else l[j] <= tp1):
                gross += d * (tp1 - entry) * half * LOT * USDINR
                fees += tp1 * half * LOT * USDINR * FEE_MAKER
                half_done, sl = True, entry
            if half_done:
                trail = extreme - d * TRAIL_ATR * a
                sl = max(sl, trail) if d == 1 else min(sl, trail)
            if half_done and (h[j] >= tp2 if d == 1 else l[j] <= tp2):
                gross += d * (tp2 - entry) * (lots - half) * LOT * USDINR
                fees += tp2 * (lots - half) * LOT * USDINR * FEE_MAKER
                exit_px, outcome, close_ep = tp2, "TP2", t[j]
                break
        else:
            j = idx + HORIZON - 1
            if j < len(t):                                   # 8h timeout exit
                lots_left = lots - half if half_done else lots
                px = c[j]
                gross += d * (px - entry) * lots_left * LOT * USDINR
                fees += px * lots_left * LOT * USDINR * FEE_TAKER
                exit_px, outcome, close_ep = px, "TIMEOUT", t[j]
        if outcome:
            con.execute(
                "UPDATE trades SET status='CLOSED', close_epoch=?, close_time=?, "
                "exit_price=?, outcome=?, gross_pnl=?, fees=?, net_pnl=? WHERE id=?",
                (int(close_ep), ist(close_ep), round(exit_px, 1), outcome,
                 round(gross), round(fees), round(gross - fees), tr["id"]))
            print(f"  closed #{tr['id']} {tr['side']} {outcome} net Rs{gross - fees:+,.0f}")
    con.commit()


def maybe_open(con, df, models, cols):
    now = datetime.now(IST)
    if not in_session(now):
        return
    if con.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'").fetchone()[0]:
        return
    today = now.strftime("%Y-%m-%d")
    n_today = con.execute("SELECT COUNT(*) FROM trades WHERE open_time LIKE ?",
                          (today + "%",)).fetchone()[0]
    pnl_today = con.execute(
        "SELECT COALESCE(SUM(net_pnl),0) FROM trades WHERE status='CLOSED' "
        "AND open_time LIKE ?", (today + "%",)).fetchone()[0]
    if n_today >= MAX_TRADES_DAY or pnl_today <= DAY_STOP:
        return
    sig = decide(df, models, cols)
    if sig["decision"] == "FLAT":
        print(f"  AI: FLAT (edge {sig['edge']:+.1%})")
        return
    if con.execute("SELECT COUNT(*) FROM trades WHERE open_epoch=?",
                   (sig["epoch"],)).fetchone()[0]:
        return                                              # this bar already traded
    a, price = float(sig["atr"]), float(sig["price"])
    lots = max(int(RISK // (SL_ATR * a * LOT * USDINR)), 2)
    notional = price * lots * LOT * USDINR
    con.execute(
        "INSERT INTO trades(open_epoch, open_time, side, lots, entry, sl, tp1, tp2,"
        " atr, edge, phase, notional_inr) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (sig["epoch"], ist(sig["epoch"]), sig["decision"], lots, price,
         float(sig["sl"]), float(sig["tp1"]), float(sig["tp2"]), a,
         float(sig["edge"]), sig["phase"], round(notional)))
    con.commit()
    print(f"  OPENED {sig['decision']} {lots} lots @ ${price:,.0f} "
          f"(edge {float(sig['edge']):+.1%}, {sig['phase']})")


def run():
    import pickle
    with open(os.path.join(HERE, "model.pkl"), "rb") as fh:
        b = pickle.load(fh)
    models = b["model"] if isinstance(b["model"], list) else [b["model"]]
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute(SCHEMA)
    print(f"[{datetime.now(IST).strftime('%Y-%m-%d %H:%M')}] engine run")
    df = fetch()
    manage_open(con, df)
    maybe_open(con, df, models, b["features"])
    make_dashboard.build(con, float(df.close.iloc[-1]))
    con.close()


if __name__ == "__main__":
    run()
