"""
Feature engineering: turns raw 15m candles into 30+ strategy signals per bar.
Concepts: trend, momentum, volatility, price action, SMC/ICT, order-flow proxies, Wyckoff phases.
All features use ONLY past data (no look-ahead).
"""
import numpy as np
import pandas as pd

HORIZON = 32          # label horizon: 32 x 15m = 8 hours
SL_ATR = 1.2          # stop = 1.2 x ATR
TP_R = 2.0            # label target = 2R


# ---------- basic indicators ----------
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def atr(df, n=14):
    tr = pd.concat([df.high - df.low,
                    (df.high - df.close.shift()).abs(),
                    (df.low - df.close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(df, n=14):
    up, dn = df.high.diff(), -df.low.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    trn = atr(df, n)
    pdi = 100 * pd.Series(plus, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / trn
    mdi = 100 * pd.Series(minus, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / trn
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


# ---------- SMC / ICT structural features (single pass loop) ----------
def structure_features(df, atr_s):
    n = len(df)
    h, l, c, o = df.high.values, df.low.values, df.close.values, df.open.values
    a = atr_s.values
    bos_dir = np.zeros(n)          # +1 last break of structure was up, -1 down
    bos_age = np.full(n, 200.0)    # bars since last BOS (capped)
    sweep = np.zeros(n)            # +1 swept lows & closed back (bullish), -1 swept highs
    fvg_dist = np.zeros(n)         # signed distance to nearest unfilled FVG mid, in ATR
    ob_dist = np.zeros(n)          # signed distance to last order block mid, in ATR

    swing_hi, swing_lo = [], []    # confirmed swing points (5-bar fractal)
    fvgs = []                      # (lo, hi, dir)
    last_ob = None                 # (mid, dir)
    cur_dir, cur_age = 0, 200.0

    for i in range(n):
        # confirmed fractal at i-2
        j = i - 2
        if j >= 2 and j + 2 <= i:
            if h[j] == max(h[j - 2:j + 3]):
                swing_hi.append(h[j])
            if l[j] == min(l[j - 2:j + 3]):
                swing_lo.append(l[j])
            swing_hi, swing_lo = swing_hi[-10:], swing_lo[-10:]

        # break of structure
        if swing_hi and c[i] > swing_hi[-1] and cur_dir <= 0:
            cur_dir, cur_age = 1, 0
            last_ob = (min(o[i - 1], c[i - 1]) / 2 + max(o[i - 1], c[i - 1]) / 2, 1) \
                if i >= 1 and c[i - 1] < o[i - 1] else last_ob
        elif swing_lo and c[i] < swing_lo[-1] and cur_dir >= 0:
            cur_dir, cur_age = -1, 0
            last_ob = ((o[i - 1] + c[i - 1]) / 2, -1) \
                if i >= 1 and c[i - 1] > o[i - 1] else last_ob
        else:
            cur_age = min(cur_age + 1, 200)
        bos_dir[i], bos_age[i] = cur_dir, cur_age

        # liquidity sweep: wick beyond last swing, close back inside
        if swing_lo and l[i] < swing_lo[-1] and c[i] > swing_lo[-1]:
            sweep[i] = 1
        elif swing_hi and h[i] > swing_hi[-1] and c[i] < swing_hi[-1]:
            sweep[i] = -1

        # fair value gaps (3-candle imbalance), keep unfilled, max 30
        if i >= 2:
            if l[i] > h[i - 2]:
                fvgs.append([h[i - 2], l[i], 1])
            elif h[i] < l[i - 2]:
                fvgs.append([h[i], l[i - 2], -1])
        fvgs = [g for g in fvgs if not (l[i] <= (g[0] + g[1]) / 2 <= h[i])][-30:]
        if fvgs and a[i] > 0:
            mids = [(g[0] + g[1]) / 2 for g in fvgs]
            nearest = min(mids, key=lambda m: abs(c[i] - m))
            fvg_dist[i] = np.clip((c[i] - nearest) / a[i], -10, 10)

        if last_ob and a[i] > 0:
            ob_dist[i] = np.clip((c[i] - last_ob[0]) / a[i], -20, 20) * last_ob[1]

    return bos_dir, bos_age, sweep, fvg_dist, ob_dist


# ---------- main ----------
def build_features(df):
    """df: columns time(open epoch s), open, high, low, close, volume. Returns (X df, meta df)."""
    df = df.reset_index(drop=True).astype(float)
    ts = pd.to_datetime(df.time, unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
    c, h, l, v = df.close, df.high, df.low, df.volume
    a = atr(df)
    f = pd.DataFrame(index=df.index)

    # A. trend & momentum
    e20, e50 = ema(c, 20), ema(c, 50)
    f["ema_dist"] = (e20 - e50) / a
    f["ema50_slope"] = e50.diff(8) / a
    f["rsi"] = rsi(c)
    f["macd_hist"] = (ema(c, 12) - ema(c, 26) - ema(ema(c, 12) - ema(c, 26), 9)) / a
    f["adx"] = adx(df)
    f["roc_6h"] = c.pct_change(24) * 100
    # 1h timeframe (resample on 4-bar groups)
    c1h = c.groupby(df.index // 4).transform("last")
    e20h = ema(c.iloc[3::4], 20).reindex(df.index).ffill()
    e50h = ema(c.iloc[3::4], 50).reindex(df.index).ffill()
    f["ema_dist_1h"] = (e20h - e50h) / a
    f["rsi_1h"] = rsi(c.iloc[3::4]).reindex(df.index).ffill()

    # B. volatility & location
    f["atr_pct"] = a / c * 100
    f["atr_ratio"] = a / a.rolling(480).mean()
    ma20, sd20 = c.rolling(20).mean(), c.rolling(20).std()
    f["boll_b"] = (c - (ma20 - 2 * sd20)) / (4 * sd20)
    day = ts.dt.date
    cumv = v.groupby(day).cumsum()
    cumpv = (c * v).groupby(day).cumsum()
    f["vwap_dist"] = (c - cumpv / cumv.replace(0, np.nan)) / a
    rng_hi, rng_lo = h.rolling(1920).max(), l.rolling(1920).min()   # 20 days
    f["range_pos"] = (c - rng_lo) / (rng_hi - rng_lo)               # premium/discount

    # C. price action
    rng = (h - l).replace(0, np.nan)
    f["body_ratio"] = (c - df.open) / rng
    f["wick_up"] = (h - np.maximum(c, df.open)) / rng
    f["wick_dn"] = (np.minimum(c, df.open) - l) / rng
    bull_eng = (c > df.open) & (c.shift() < df.open.shift()) & (c > df.open.shift()) & (df.open < c.shift())
    bear_eng = (c < df.open) & (c.shift() > df.open.shift()) & (c < df.open.shift()) & (df.open > c.shift())
    f["engulf"] = bull_eng.astype(int) - bear_eng.astype(int)
    don_hi, don_lo = h.rolling(20).max().shift(), l.rolling(20).min().shift()
    f["donchian"] = (c > don_hi).astype(int) - (c < don_lo).astype(int)
    f["compression"] = ((h - l) == (h - l).rolling(7).min()).astype(int)

    # D. SMC / ICT
    bos_dir, bos_age, sweep, fvg_dist, ob_dist = structure_features(df, a)
    f["bos_dir"], f["bos_age"] = bos_dir, bos_age
    f["sweep"], f["fvg_dist"], f["ob_dist"] = sweep, fvg_dist, ob_dist
    utc_h = ts.dt.tz_convert("UTC").dt.hour
    asia = (utc_h < 8)
    asia_hi = h.where(asia).groupby(day).transform("max")
    asia_lo = l.where(asia).groupby(day).transform("min")
    f["asia_break"] = np.where(c > asia_hi, 1, np.where(c < asia_lo, -1, 0))
    f["round_dist"] = (c % 1000) / 1000

    # E. order-flow proxies & phase
    f["vol_z"] = (v - v.rolling(96).mean()) / v.rolling(96).std()
    pos_in_bar = ((c - l) - (h - c)) / rng
    f["cvd_20"] = (pos_in_bar * v).rolling(20).sum() / v.rolling(20).sum()
    # F. v2 extra inputs
    e20_4h = ema(c.iloc[15::16], 20).reindex(df.index).ffill()
    e50_4h = ema(c.iloc[15::16], 50).reindex(df.index).ffill()
    f["ema_dist_4h"] = (e20_4h - e50_4h) / a          # third timeframe
    f["rsi_chg"] = f["rsi"].diff(4)                   # momentum of momentum
    f["atr_rank"] = a.rolling(480).rank(pct=True)     # volatility percentile
    f["dist_swing_hi"] = (h.rolling(96).max() - c) / a   # liquidity above
    f["dist_swing_lo"] = (c - l.rolling(96).min()) / a   # liquidity below
    up_bar = (c > df.open).astype(int) * 2 - 1
    f["streak"] = (up_bar.groupby((up_bar != up_bar.shift()).cumsum()).cumcount() + 1) * up_bar
    f["range_pos_5d"] = (c - l.rolling(480).min()) / (h.rolling(480).max() - l.rolling(480).min())
    f["weekend"] = (ts.dt.dayofweek >= 5).astype(int)

    # Wyckoff phase: 0 chop, 1 trend-up, 2 trend-down, 3 accumulation, 4 distribution
    trending = f["adx"] > 20
    slope_5d = e50.diff(480)
    phase = np.zeros(len(df))
    phase[trending & (e20 > e50)] = 1
    phase[trending & (e20 < e50)] = 2
    ranging = ~trending
    phase[ranging & (slope_5d < 0)] = 3      # range after markdown = accumulation
    phase[ranging & (slope_5d > 0)] = 4      # range after markup = distribution
    f["phase"] = phase

    # time
    f["hour"] = ts.dt.hour
    f["dow"] = ts.dt.dayofweek

    meta = pd.DataFrame({"time": df.time, "open": df.open, "high": h, "low": l,
                         "close": c, "atr": a, "phase": phase})
    return f, meta


def triple_barrier_labels(meta):
    """For each bar: 1 = long wins (TP 2R before SL), 2 = short wins, 0 = neither/timeout."""
    h, l, c, a = meta.high.values, meta.low.values, meta.close.values, meta.atr.values
    n = len(c)
    y = np.zeros(n, dtype=int)
    for i in range(n - HORIZON - 1):
        if not a[i] > 0:
            continue
        sl = SL_ATR * a[i]
        tp = TP_R * sl
        L_sl, L_tp = c[i] - sl, c[i] + tp
        S_sl, S_tp = c[i] + sl, c[i] - tp
        long_res = short_res = 0
        for j in range(i + 1, i + 1 + HORIZON):
            if long_res == 0:
                if l[j] <= L_sl:
                    long_res = -1
                elif h[j] >= L_tp:
                    long_res = 1
            if short_res == 0:
                if h[j] >= S_sl:
                    short_res = -1
                elif l[j] <= S_tp:
                    short_res = 1
            if long_res and short_res:
                break
        if long_res == 1 and short_res != 1:
            y[i] = 1
        elif short_res == 1 and long_res != 1:
            y[i] = 2
    return y


def load_dataset(csv_path="data/btc_15m.csv"):
    df = pd.read_csv(csv_path)
    X, meta = build_features(df)
    y = triple_barrier_labels(meta)
    warm = 2000                      # drop indicator warm-up
    valid = slice(warm, len(df) - HORIZON - 1)
    return X.iloc[valid].fillna(0), y[valid], meta.iloc[valid].reset_index(drop=True)
