"""
Download BTC 15m candles from Delta India public API and save to data/btc_15m.csv.

Usage:  python fetch_data.py [days]     (default 365; use 730 or 1095 for 2-3 years)
"""
import csv
import os
import sys
import time

import requests

API = "https://api.india.delta.exchange/v2/history/candles"
SYMBOL, RESOLUTION = "BTCUSD", "15m"


def fetch(days):
    out, end = [], int(time.time())
    start = end - days * 86400
    step = 7 * 86400
    s = start
    while s < end:
        e = min(s + step, end)
        for attempt in range(3):
            try:
                r = requests.get(API, params={"resolution": RESOLUTION, "symbol": SYMBOL,
                                              "start": s, "end": e}, timeout=20)
                r.raise_for_status()
                out += r.json()["result"]
                break
            except Exception as ex:
                print(f"  retry {attempt + 1}: {ex}")
                time.sleep(2)
        s = e
        done = (s - start) / (end - start) * 100
        print(f"\r  {done:.0f}%", end="")
        time.sleep(0.25)
    print()
    seen, rows = set(), []
    for c in sorted(out, key=lambda c: c["time"]):
        if c["time"] not in seen:
            seen.add(c["time"])
            rows.append([c["time"], c["open"], c["high"], c["low"], c["close"],
                         c.get("volume", 0)])
    return rows


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    print(f"Fetching {days} days of {RESOLUTION} {SYMBOL} candles from Delta India...")
    rows = fetch(days)
    os.makedirs("data", exist_ok=True)
    with open("data/btc_15m.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close", "volume"])
        w.writerows(rows)
    print(f"Saved {len(rows)} candles -> data/btc_15m.csv "
          f"({rows[0][0]} .. {rows[-1][0]})")
