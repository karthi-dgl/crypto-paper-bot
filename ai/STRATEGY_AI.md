# AI Trading Model — Design & Analysis (the "heart" of the bot)

## What this is

Instead of one fixed strategy (v1/v2 lost money — fees + sub-45% win rate), we feed the model
**27 strategy signals** computed on every 15-minute candle of 1–3 years of BTC history, plus the
**market phase** (accumulation / distribution / consolidation / trend). The model learns *which
combinations of signals, in which phase, at which hour* preceded profitable moves — and only
trades when its confidence is high. It stays flat the rest of the time. Not trading IS a decision.

```
1-3 yrs BTC 15m candles ──> 27 features per candle ──> Gradient-Boosted Trees ──> P(long wins) P(short wins) P(no edge)
                                   │                                                      │
                            Triple-barrier labels                          confidence > threshold?
                            (did 2R TP hit before 1R SL                   ──> BUY/SELL + entry, SL,
                             within next 8 hours?)                              TP1, TP2, trail | else FLAT
```

## The 27 features (the "multiple strategies")

### A. Trend & momentum (classic TA) — 8 features
| # | Feature | Strategy concept |
|---|---|---|
| 1 | EMA20 vs EMA50 distance (15m) | trend following |
| 2 | EMA20 vs EMA50 distance (1h) | higher-timeframe alignment |
| 3 | EMA50 slope (normalized) | trend strength/direction |
| 4 | RSI(14) | momentum / mean reversion |
| 5 | RSI(14) on 1h | HTF momentum |
| 6 | MACD histogram (normalized) | momentum shift |
| 7 | ADX(14) | trending vs ranging market |
| 8 | Rate of change 24 bars (6h) | medium-term momentum |

### B. Volatility & location — 5 features
| # | Feature | Concept |
|---|---|---|
| 9 | ATR(14)/price | volatility regime |
| 10 | ATR now vs ATR 5-day average | volatility expansion/contraction |
| 11 | Bollinger %B (20,2) | overextension |
| 12 | Distance from session VWAP | institutional mean |
| 13 | Position in last 20-day range (0–1) | premium/discount (ICT: above 0.5 = premium → favors shorts) |

### C. Price action — 5 features
| # | Feature | Concept |
|---|---|---|
| 14 | Candle body/range ratio | conviction candles |
| 15 | Upper & lower wick ratios | rejection / pin bars |
| 16 | Bullish/bearish engulfing flag | reversal pattern |
| 17 | Donchian(20) breakout flag (+1/0/−1) | breakout trading |
| 18 | Inside-bar / NR7 compression flag | volatility coil before expansion |

### D. SMC / ICT concepts — 6 features
| # | Feature | Concept |
|---|---|---|
| 19 | Market structure: bars since last BOS, direction | Break of Structure / CHoCH (swing logic, 5-bar fractals) |
| 20 | Liquidity sweep flag | wick takes out prior swing high/low then closes back inside (stop hunt) |
| 21 | Fair value gap: distance to nearest unfilled FVG | 3-candle imbalance, price magnets |
| 22 | Order-block proximity | last opposite candle before an impulsive move |
| 23 | Asia-range breakout state | ICT session concept: London/NY take Asia's liquidity |
| 24 | Round-number distance ($1000 levels) | psychological liquidity pools |

### E. Order-flow proxies & market phase — 4 features
True order flow needs tick data; from candles we use proven proxies:
| # | Feature | Concept |
|---|---|---|
| 25 | Volume z-score + volume×direction | effort vs result (Wyckoff) |
| 26 | Cumulative volume delta proxy (close-position-in-range × volume, summed 20 bars) | buying/selling pressure |
| 27 | **Market phase**: trend-up / trend-down / accumulation / distribution / neutral-chop | Wyckoff phases — encoded from ADX + 20-day range + preceding trend direction: range after markdown = **accumulation**, range after markup = **distribution** |

Plus hour-of-day and day-of-week (the v1 backtest proved 20:00–22:00 IST behaves differently).

## How it learns: triple-barrier labels (industry standard, López de Prado)

For every historical candle we simulate BOTH a long and a short with SL = 1.2×ATR and TP = 2×risk,
8-hour time limit. Label = which side won (or neither). The model is trained to predict this.
So a prediction directly answers: *"from here, would a 2R long/short have worked?"*

## How we avoid fooling ourselves (this is what makes it trustworthy)

- **Walk-forward validation**: train on months 1–6, test on month 7; retrain on 1–7, test 8; etc.
  The model is ALWAYS tested on data it has never seen. No look-ahead.
- **Purged labels**: 32-bar gap between train and test sets so overlapping labels can't leak.
- **Fees + slippage in every simulated trade** (maker entry, taker stop, 18% GST, 1-tick slippage).
- **Confidence threshold tuned on validation only** — we trade ~the top 15–25% most confident setups.

## Money management (trained for ₹50,000)

Risk 1% (₹500) per trade, sized by stop distance. TP1 = 1.5R closes half + SL→breakeven.
TP2 = 3R, with ATR chandelier trail after TP1. Max 3 trades/day, −2% daily stop, −6% kill switch.

## Honest expectations (read this twice)

₹50,000 → ₹3,00,000 (6x) in a year means 500% — no honestly validated system does this repeatably.
What a *good* result looks like in walk-forward: 50–55% win rate at 2R targets, profit factor 1.3–1.6,
**30–80%/year** with max drawdown under 15%. And taxes: you pay slab rate **on profit only** — any
profit is real profit. If walk-forward shows no edge, the honest answer is "don't trade this" and
we iterate on features — that result still saves your ₹50,000.
