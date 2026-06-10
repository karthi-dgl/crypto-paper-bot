"""
BTC intraday bot — Delta Exchange India, TP-15 strategy.

MODE=paper   -> simulates fills locally using live prices (default, zero risk)
MODE=testnet -> sends real orders to Delta demo account (fake money)
MODE=live    -> real money. Do NOT enable until tested for weeks.

Run:  python bot.py
"""
import csv
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import config as cfg
from delta_client import DeltaClient
from strategy import check_signal

IST = ZoneInfo(cfg.TIMEZONE)
LOG = "trades.csv"


def in_session(now):
    hm = now.strftime("%H:%M")
    return cfg.SESSION_START <= hm <= cfg.SESSION_END


def log_trade(row):
    new = False
    try:
        open(LOG).close()
    except FileNotFoundError:
        new = True
    with open(LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "side", "lots", "entry", "stop", "tp1", "tp2",
                        "exit", "pnl_inr", "note"])
        w.writerow(row)


class Bot:
    def __init__(self):
        self.client = DeltaClient()
        self.pos = None          # dict: side, lots, entry, stop, tp1, tp2, half_closed
        self.day = None
        self.trades_today = 0
        self.day_pnl = 0.0
        self.total_pnl = 0.0

    # ---------- order placement (testnet/live) ----------
    def open_position(self, sig):
        if cfg.MODE != "paper":
            close_side = "sell" if sig.side == "buy" else "buy"
            self.client.place_order(sig.side, sig.lots)                       # entry (market)
            self.client.place_order(close_side, sig.lots, stop_price=sig.stop,
                                    reduce_only=True)                          # SL (full)
            half = sig.lots // 2
            self.client.place_order(close_side, half, "limit_order",
                                    limit_price=sig.tp1, reduce_only=True)     # TP1 (half)
            self.client.place_order(close_side, sig.lots - half, "limit_order",
                                    limit_price=sig.tp2, reduce_only=True)     # TP2 (rest)
        self.pos = {"side": sig.side, "lots": sig.lots, "entry": sig.entry,
                    "stop": sig.stop, "tp1": sig.tp1, "tp2": sig.tp2,
                    "half_closed": False}
        self.trades_today += 1
        print(f"[{now_str()}] OPEN {sig.side} {sig.lots} lots @ {sig.entry:.1f} "
              f"SL {sig.stop:.1f} TP1 {sig.tp1:.1f} TP2 {sig.tp2:.1f}")

    def pnl_inr(self, exit_price, lots):
        d = exit_price - self.pos["entry"]
        if self.pos["side"] == "sell":
            d = -d
        gross = d * lots * cfg.LOT_BTC * cfg.USDINR
        fees = (self.pos["entry"] + exit_price) * lots * cfg.LOT_BTC \
            * cfg.USDINR * 0.0005 * 1.18
        return gross - fees

    def close_chunk(self, exit_price, lots, note):
        pnl = self.pnl_inr(exit_price, lots)
        self.day_pnl += pnl
        self.total_pnl += pnl
        p = self.pos
        log_trade([now_str(), p["side"], lots, f'{p["entry"]:.1f}', f'{p["stop"]:.1f}',
                   f'{p["tp1"]:.1f}', f'{p["tp2"]:.1f}', f"{exit_price:.1f}",
                   f"{pnl:.0f}", note])
        print(f"[{now_str()}] {note} {lots} lots @ {exit_price:.1f} -> Rs{pnl:.0f} "
              f"(day Rs{self.day_pnl:.0f}, total Rs{self.total_pnl:.0f})")

    # ---------- paper-mode position management ----------
    def manage_paper(self, candle):
        p = self.pos
        hi, lo = candle["high"], candle["low"]
        long = p["side"] == "buy"
        sl_hit = lo <= p["stop"] if long else hi >= p["stop"]
        tp1_hit = hi >= p["tp1"] if long else lo <= p["tp1"]
        tp2_hit = hi >= p["tp2"] if long else lo <= p["tp2"]

        if sl_hit:                                   # worst case first (conservative)
            lots = p["lots"] if not p["half_closed"] else p["lots"] - p["lots"] // 2
            self.close_chunk(p["stop"], lots, "STOP" if not p["half_closed"] else "BE-STOP")
            self.pos = None
            return
        if tp1_hit and not p["half_closed"]:
            self.close_chunk(p["tp1"], p["lots"] // 2, "TP1")
            p["half_closed"] = True
            p["stop"] = p["entry"]                   # breakeven
        if tp2_hit and p["half_closed"]:
            self.close_chunk(p["tp2"], p["lots"] - p["lots"] // 2, "TP2")
            self.pos = None

    # ---------- main loop ----------
    def run(self):
        print(f"Bot started | mode={cfg.MODE} | capital Rs{cfg.CAPITAL_INR:,} "
              f"| risk/trade Rs{cfg.CAPITAL_INR * cfg.RISK_PCT:.0f}")
        while True:
            try:
                now = datetime.now(IST)
                if now.date() != self.day:
                    self.day, self.trades_today, self.day_pnl = now.date(), 0, 0.0

                candles = self.client.candles(days=3)
                closed = candles[:-1]                # drop the still-forming bar

                if self.pos:
                    self.manage_paper(closed[-1])
                elif (in_session(now)
                      and self.trades_today < cfg.MAX_TRADES_PER_DAY
                      and self.day_pnl > -cfg.MAX_DAILY_LOSS_PCT * cfg.CAPITAL_INR
                      and self.total_pnl > -cfg.MAX_DRAWDOWN_KILL * cfg.CAPITAL_INR):
                    sig = check_signal(closed)
                    if sig:
                        self.open_position(sig)

                time.sleep(seconds_to_next_bar())
            except KeyboardInterrupt:
                print("Stopped by user.")
                break
            except Exception as e:
                print(f"[{now_str()}] error: {e} — retrying in 60s")
                time.sleep(60)


def now_str():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def seconds_to_next_bar(minutes=15):
    t = int(time.time())
    return minutes * 60 - t % (minutes * 60) + 5     # +5s buffer after bar close


if __name__ == "__main__":
    Bot().run()
