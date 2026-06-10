"""
Backtest TP-15 on real Delta India candles.

Usage:  python backtest.py [days]   (default 60)
Fetches 15m BTCUSD candles from the public API in 7-day chunks, simulates the
strategy with fees, prints stats and writes backtest_trades.csv.
"""
import csv
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

import config as cfg
from strategy import check_signal

IST = ZoneInfo(cfg.TIMEZONE)


def fetch_candles(days):
    out, end = [], int(time.time())
    start = end - days * 86400
    step = 7 * 86400
    s = start
    while s < end:
        e = min(s + step, end)
        r = requests.get("https://api.india.delta.exchange/v2/history/candles",
                         params={"resolution": cfg.RESOLUTION, "symbol": cfg.SYMBOL,
                                 "start": s, "end": e}, timeout=20)
        r.raise_for_status()
        out += r.json()["result"]
        s = e
        time.sleep(0.3)
    seen, dedup = set(), []
    for c in sorted(out, key=lambda c: c["time"]):
        if c["time"] not in seen:
            seen.add(c["time"])
            dedup.append({k: float(c[k]) if k != "time" else c[k]
                          for k in ("time", "open", "high", "low", "close")})
    return dedup


def in_session(ts):
    hm = datetime.fromtimestamp(ts, IST).strftime("%H:%M")
    if not (cfg.SESSION_START <= hm <= cfg.SESSION_END):
        return False
    return not (cfg.BLACKOUT_START <= hm <= cfg.BLACKOUT_END)   # v2: NY-open blackout


def fee_inr(price, lots, rate):
    return price * lots * cfg.LOT_BTC * cfg.USDINR * rate


def run(candles):
    trades, pos = [], None
    equity = cfg.CAPITAL_INR
    day, trades_today, day_pnl = None, 0, 0.0

    for i in range(cfg.EMA_SLOW + 10, len(candles)):
        c = candles[i]
        d = datetime.fromtimestamp(c["time"], IST).date()
        if d != day:
            day, trades_today, day_pnl = d, 0, 0.0

        if pos:
            long = pos["side"] == "buy"
            sl = c["low"] <= pos["stop"] if long else c["high"] >= pos["stop"]
            tp1 = c["high"] >= pos["tp1"] if long else c["low"] <= pos["tp1"]
            tp2 = c["high"] >= pos["tp2"] if long else c["low"] <= pos["tp2"]

            def book(price, lots, tag):
                nonlocal equity, day_pnl
                diff = (price - pos["entry"]) * (1 if long else -1)
                pnl = diff * lots * cfg.LOT_BTC * cfg.USDINR \
                    - fee_inr(pos["entry"], lots) - fee_inr(price, lots)
                equity += pnl
                day_pnl += pnl
                trades.append({"time": datetime.fromtimestamp(c["time"], IST).isoformat(),
                               "side": pos["side"], "lots": lots, "entry": pos["entry"],
                               "exit": price, "pnl": round(pnl), "tag": tag,
                               "equity": round(equity)})

            if sl:                                    # conservative: stop checked first
                lots = pos["lots"] if not pos["half"] else pos["lots"] - pos["lots"] // 2
                book(pos["stop"], lots, "SL" if not pos["half"] else "BE")
                pos = None
            else:
                if tp1 and not pos["half"]:
                    book(pos["tp1"], pos["lots"] // 2, "TP1")
                    pos["half"], pos["stop"] = True, pos["entry"]
                if pos and tp2 and pos["half"]:
                    book(pos["tp2"], pos["lots"] - pos["lots"] // 2, "TP2")
                    pos = None
            continue

        if (in_session(c["time"]) and trades_today < cfg.MAX_TRADES_PER_DAY
                and day_pnl > -cfg.MAX_DAILY_LOSS_PCT * cfg.CAPITAL_INR):
            sig = check_signal(candles[max(0, i - 200):i + 1])
            if sig:
                pos = {"side": sig.side, "lots": sig.lots, "entry": sig.entry,
                       "stop": sig.stop, "tp1": sig.tp1, "tp2": sig.tp2, "half": False}
                trades_today += 1

    return trades, equity


def report(trades, equity, days):
    if not trades:
        print("No trades generated.")
        return
    closes = [t for t in trades if t["tag"] in ("SL", "BE", "TP2")]
    pnl = equity - cfg.CAPITAL_INR
    by_trade = {}
    for t in trades:
        by_trade.setdefault(t["time"][:16] + t["side"], 0)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    peak, dd = cfg.CAPITAL_INR, 0
    for t in trades:
        peak = max(peak, t["equity"])
        dd = max(dd, (peak - t["equity"]) / peak)
    print(f"\n===== BACKTEST {days} days | {cfg.SYMBOL} {cfg.RESOLUTION} =====")
    print(f"Round trips:      {len(closes)}")
    print(f"Fills (w/ partials): {len(trades)}  | winning fills: {wins}")
    print(f"Net P&L:          Rs{pnl:,.0f}  ({pnl / cfg.CAPITAL_INR * 100:.1f}%)")
    print(f"Final equity:     Rs{equity:,.0f}")
    print(f"Max drawdown:     {dd * 100:.1f}%")
    print(f"Avg P&L / round trip: Rs{pnl / max(len(closes), 1):,.0f}")
    with open("backtest_trades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=trades[0].keys())
        w.writeheader()
        w.writerows(trades)
    print("Trade log -> backtest_trades.csv")


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    print(f"Fetching {days} days of {cfg.RESOLUTION} candles...")
    candles = fetch_candles(days)
    print(f"{len(candles)} candles fetched.")
    trades, equity = run(candles)
    report(trades, equity, days)
