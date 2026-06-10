"""TP-15 strategy: EMA trend + RSI pullback + breakout trigger. Pure functions, no I/O."""
from dataclasses import dataclass

import config as cfg


def ema(values, length):
    k = 2 / (length + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(closes, length=14):
    out = [50.0] * len(closes)
    gains = losses = 0.0
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        g, l = max(ch, 0), max(-ch, 0)
        if i <= length:
            gains += g
            losses += l
            if i == length:
                ag, al = gains / length, losses / length
                out[i] = 100 - 100 / (1 + (ag / al if al else 1e9))
        else:
            ag = (ag * (length - 1) + g) / length
            al = (al * (length - 1) + l) / length
            out[i] = 100 - 100 / (1 + (ag / al if al else 1e9))
    return out


def atr(highs, lows, closes, length=14):
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    out = [trs[0]]
    for i in range(1, len(trs)):
        out.append((out[-1] * (length - 1) + trs[i]) / length)
    return out


def resample(candles, minutes=60):
    """Group 15m candles into higher-timeframe candles (oldest first)."""
    buckets = {}
    for c in candles:
        key = c["time"] // (minutes * 60)
        b = buckets.get(key)
        if b is None:
            buckets[key] = dict(time=key * minutes * 60, open=c["open"],
                                high=c["high"], low=c["low"], close=c["close"])
        else:
            b["high"] = max(b["high"], c["high"])
            b["low"] = min(b["low"], c["low"])
            b["close"] = c["close"]
    return [buckets[k] for k in sorted(buckets)]


def htf_trend(candles):
    """Returns 'up', 'down' or None based on 1h EMA20/EMA50."""
    htf = resample(candles, cfg.HTF_MINUTES)
    if len(htf) < cfg.HTF_EMA_SLOW + 5:
        return None
    closes = [c["close"] for c in htf]
    f, s = ema(closes, cfg.HTF_EMA_FAST)[-1], ema(closes, cfg.HTF_EMA_SLOW)[-1]
    if f > s and closes[-1] > s:
        return "up"
    if f < s and closes[-1] < s:
        return "down"
    return None


@dataclass
class Signal:
    side: str          # "buy" or "sell"
    entry: float
    stop: float
    tp1: float
    tp2: float
    lots: int


def position_size(entry, stop):
    """Lots so that hitting the stop loses ~RISK_PCT of capital."""
    risk_inr = cfg.CAPITAL_INR * cfg.RISK_PCT
    loss_per_lot_inr = abs(entry - stop) * cfg.LOT_BTC * cfg.USDINR
    return max(int(risk_inr // loss_per_lot_inr), 0)


def check_signal(candles):
    """candles: list of dicts with open/high/low/close, oldest first. Evaluates the last CLOSED bar."""
    if len(candles) < cfg.EMA_SLOW + 10:
        return None
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]

    e_fast = ema(closes, cfg.EMA_FAST)
    e_slow = ema(closes, cfg.EMA_SLOW)
    r = rsi(closes, cfg.RSI_LEN)
    a = atr(highs, lows, closes, cfg.ATR_LEN)

    i = len(closes) - 1                      # last closed bar
    c, prev_h, prev_l = closes[i], highs[i - 1], lows[i - 1]
    recent_rsi = r[i - cfg.PULLBACK_LOOKBACK:i]

    htf = htf_trend(candles)                 # v2: 1h trend must agree
    up = e_fast[i] > e_slow[i] and c > e_slow[i] and htf == "up"
    down = e_fast[i] < e_slow[i] and c < e_slow[i] and htf == "down"
    sl_dist = max(cfg.SL_ATR_MULT * a[i], cfg.SL_MIN_PCT * c)

    if up and min(recent_rsi, default=100) < cfg.RSI_PULLBACK_LONG \
            and c > prev_h and c > e_fast[i]:
        stop = c - sl_dist
        sig = Signal("buy", c, stop, c + cfg.TP1_R * sl_dist, c + cfg.TP2_R * sl_dist, 0)
    elif down and max(recent_rsi, default=0) > cfg.RSI_PULLBACK_SHORT \
            and c < prev_l and c < e_fast[i]:
        stop = c + sl_dist
        sig = Signal("sell", c, stop, c - cfg.TP1_R * sl_dist, c - cfg.TP2_R * sl_dist, 0)
    else:
        return None

    sig.lots = position_size(sig.entry, sig.stop)
    return sig if sig.lots > 0 else None
