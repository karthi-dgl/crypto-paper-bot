"""
Executor: turns the AI's decision into REAL orders on Delta Exchange India.

SAFE BY DEFAULT: trades the TESTNET (demo money) unless BOT_MODE=live AND
I_UNDERSTAND_LIVE_RISK=yes are both set. Keys come from environment variables
(GitHub Secrets in the cloud) — never from files.

Each run (every 15 min via GitHub Actions):
  no position, no orders  -> ask AI -> place limit entry if edge >= margin
  entry filled            -> place SL + TP1 + TP2 brackets
  TP1 filled              -> move SL to breakeven
  position gone           -> clean up leftover orders
"""
import hashlib
import hmac
import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from features import SL_ATR
from signal_logger import LOT, RISK, USDINR, decide, fetch, in_session

MODE = os.getenv("BOT_MODE", "testnet")
if MODE == "live" and os.getenv("I_UNDERSTAND_LIVE_RISK") != "yes":
    raise SystemExit("Refusing live mode without I_UNDERSTAND_LIVE_RISK=yes")
BASE = {"testnet": "https://cdn-ind.testnet.deltaex.org",
        "live": "https://api.india.delta.exchange"}[MODE]
KEY, SECRET = os.getenv("DELTA_API_KEY", ""), os.getenv("DELTA_API_SECRET", "")
SYMBOL = "BTCUSD"
IST = ZoneInfo("Asia/Kolkata")
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "executor_state.json")
ENTRY_TTL = 1200          # cancel unfilled entry after 20 min


class Delta:
    def _headers(self, method, path, query="", body=""):
        ts = str(int(time.time()))
        msg = method + ts + path + query + body
        sig = hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
        return {"api-key": KEY, "timestamp": ts, "signature": sig,
                "Content-Type": "application/json", "User-Agent": "rest-client"}

    def get(self, path, params=None):
        query = "?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else ""
        r = requests.get(BASE + path + query,
                         headers=self._headers("GET", path, query), timeout=20)
        if r.status_code >= 400:
            print("  API error:", r.text[:300])
        r.raise_for_status()
        return r.json()["result"]

    def send(self, method, path, payload):
        body = json.dumps(payload, separators=(",", ":"))
        r = requests.request(method, BASE + path, data=body,
                             headers=self._headers(method, path, body=body), timeout=20)
        if r.status_code >= 400:
            print("  API error:", r.text[:300])
        r.raise_for_status()
        return r.json()["result"]

    def product_id(self):
        r = requests.get(BASE + f"/v2/tickers/{SYMBOL}", timeout=20)
        return r.json()["result"]["product_id"]

    def order(self, pid, side, size, order_type="limit_order", limit_price=None,
              stop_price=None, reduce_only=False):
        p = {"product_id": pid, "side": side, "size": int(size),
             "order_type": order_type, "reduce_only": reduce_only}
        if limit_price is not None:
            p["limit_price"] = str(limit_price)
        if stop_price is not None:
            p.update(order_type="market_order", stop_order_type="stop_loss_order",
                     stop_price=str(stop_price))
        return self.send("POST", "/v2/orders", p)

    def cancel_all(self, pid):
        return self.send("DELETE", "/v2/orders/all", {"product_id": pid})


def load_state():
    try:
        return json.load(open(STATE))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(s):
    json.dump(s, open(STATE, "w"), indent=1)


def run():
    api = Delta()
    pid = api.product_id()
    now = datetime.now(IST)
    print(f"[{now.strftime('%Y-%m-%d %H:%M')}] executor {MODE} product {pid}")

    pos = api.get("/v2/positions", {"product_id": pid}) or {}
    size = int(pos.get("size") or 0)
    orders = api.get("/v2/orders", {"product_ids": pid, "states": "open"}) or []
    st = load_state()

    if size == 0:
        if st.get("active") and not orders:
            print(f"  position closed -> trade over, clearing state")
            st = {}
        if orders:
            entry_orders = [o for o in orders if not o.get("reduce_only")]
            if entry_orders and time.time() - st.get("placed_at", 0) > ENTRY_TTL:
                print("  entry not filled in 20 min -> cancel all")
                api.cancel_all(pid)
                st = {}
            elif not entry_orders:
                print("  leftover bracket orders -> cancel all")
                api.cancel_all(pid)
                st = {}
        elif in_session(now):
            sig = decide(fetch(), *_load_model())
            if sig["decision"] == "FLAT":
                print(f"  AI: FLAT (edge {float(sig['edge']):+.1%})")
            else:
                a, price = float(sig["atr"]), float(sig["price"])
                lots = max(int(RISK // (SL_ATR * a * LOT * USDINR)), 2)
                api.order(pid, "buy" if sig["decision"] == "BUY" else "sell",
                          lots, limit_price=round(price, 0))
                st = {"active": True, "side": sig["decision"], "lots": lots,
                      "entry": price, "sl": float(sig["sl"]), "tp1": float(sig["tp1"]),
                      "tp2": float(sig["tp2"]), "placed_at": time.time(),
                      "bracketed": False, "be_done": False}
                print(f"  ENTRY {sig['decision']} {lots} lots @ {price:,.0f} "
                      f"(edge {float(sig['edge']):+.1%})")
    else:
        d = 1 if size > 0 else -1
        close_side = "sell" if d == 1 else "buy"
        if not st.get("active"):                       # crashed state; rebuild minimal
            st = {"active": True, "side": "BUY" if d == 1 else "SELL",
                  "lots": abs(size), "entry": float(pos.get("entry_price") or 0),
                  "bracketed": False, "be_done": False}
        if not st.get("bracketed"):
            half = st["lots"] // 2
            api.order(pid, close_side, abs(size), stop_price=round(st["sl"], 0),
                      reduce_only=True)
            api.order(pid, close_side, half, limit_price=round(st["tp1"], 0),
                      reduce_only=True)
            api.order(pid, close_side, abs(size) - half,
                      limit_price=round(st["tp2"], 0), reduce_only=True)
            st["bracketed"] = True
            print(f"  brackets placed: SL {st['sl']:,.0f} TP1 {st['tp1']:,.0f} "
                  f"TP2 {st['tp2']:,.0f}")
        elif abs(size) <= st["lots"] // 2 and not st.get("be_done"):
            print("  TP1 filled -> moving SL to breakeven")
            stops = [o for o in orders if o.get("stop_order_type")]
            for o in stops:
                api.send("DELETE", "/v2/orders", {"id": o["id"], "product_id": pid})
            api.order(pid, close_side, abs(size),
                      stop_price=round(st["entry"], 0), reduce_only=True)
            st["be_done"] = True
        else:
            print(f"  holding {st['side']} {abs(size)} lots (entry {st['entry']:,.0f})")

    save_state(st)


def _load_model():
    import pickle
    with open(os.path.join(HERE, "model.pkl"), "rb") as fh:
        b = pickle.load(fh)
    models = b["model"] if isinstance(b["model"], list) else [b["model"]]
    return models, b["features"]


if __name__ == "__main__":
    import sys
    if not KEY or not SECRET:
        raise SystemExit("Set DELTA_API_KEY and DELTA_API_SECRET environment variables "
                         "(GitHub: repo Settings -> Secrets -> Actions)")
    if "--loop" in sys.argv:                  # local mode: checks every 15 minutes
        print("Executor loop running. Ctrl+C to stop.")
        while True:
            try:
                run()
            except KeyboardInterrupt:
                break
            except Exception as e:
                print("error:", e)
            time.sleep(900 - int(time.time()) % 900 + 10)
    else:
        run()
