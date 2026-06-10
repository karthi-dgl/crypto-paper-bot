"""Minimal Delta Exchange India REST client (public data + signed orders)."""
import hashlib
import hmac
import json
import time

import requests

import config as cfg


class DeltaClient:
    def __init__(self, base_url=cfg.BASE_URL, key=cfg.API_KEY, secret=cfg.API_SECRET):
        self.base = base_url.rstrip("/")
        self.key, self.secret = key, secret
        self.s = requests.Session()

    # ---------- public ----------
    def candles(self, symbol=cfg.SYMBOL, resolution=cfg.RESOLUTION, days=3):
        end = int(time.time())
        start = end - days * 86400
        r = self.s.get(f"{self.base}/v2/history/candles",
                       params={"resolution": resolution, "symbol": symbol,
                               "start": start, "end": end}, timeout=15)
        r.raise_for_status()
        out = r.json()["result"]
        out.sort(key=lambda c: c["time"])           # oldest first
        return out

    def ticker(self, symbol=cfg.SYMBOL):
        r = self.s.get(f"{self.base}/v2/tickers/{symbol}", timeout=15)
        r.raise_for_status()
        return r.json()["result"]

    # ---------- signed ----------
    def _sign(self, method, path, query="", body=""):
        ts = str(int(time.time()))
        msg = method + ts + path + query + body
        sig = hmac.new(self.secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
        return {"api-key": self.key, "timestamp": ts, "signature": sig,
                "Content-Type": "application/json"}

    def _request(self, method, path, payload=None):
        body = json.dumps(payload, separators=(",", ":")) if payload else ""
        headers = self._sign(method, path, body=body)
        r = self.s.request(method, self.base + path, headers=headers,
                           data=body or None, timeout=15)
        r.raise_for_status()
        return r.json()

    def place_order(self, side, size, order_type="market_order", limit_price=None,
                    stop_price=None, reduce_only=False):
        p = {"product_id": cfg.PRODUCT_ID, "side": side, "size": size,
             "order_type": order_type, "reduce_only": reduce_only}
        if limit_price is not None:
            p["limit_price"] = str(limit_price)
        if stop_price is not None:                   # stop-market order
            p["stop_order_type"] = "stop_loss_order"
            p["stop_price"] = str(stop_price)
            p["order_type"] = "market_order"
        return self._request("POST", "/v2/orders", p)

    def positions(self):
        return self._request("GET", f"/v2/positions/margined")

    def cancel_all(self):
        return self._request("DELETE", "/v2/orders/all",
                             {"product_id": cfg.PRODUCT_ID})
