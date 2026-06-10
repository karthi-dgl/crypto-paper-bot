# BTC Intraday Strategy — Delta Exchange India (BTCUSD Perpetual)

## Market facts (verified June 2026)

| Item | Value |
|---|---|
| Contract | BTCUSD Perpetual (product_id 27) |
| Lot size | 0.001 BTC (~$62 / ~₹5,400 at BTC $62,000) |
| Tick size | $0.5 |
| Max leverage | up to 200x (we use ~2–3x effective) |
| Fees | Taker 0.05%, Maker 0.02% (+18% GST on fee) |
| Funding | every 8 hours (avoid holding through if flat edge) |
| Settlement | INR-settled. Profits taxed as business/speculative income at your slab — NOT 30% VDA tax, NO 1% TDS (per Delta Exchange support docs; confirm with your CA) |

## Strategy: 15-minute EMA Trend Pullback ("TP-15")

Trade in the direction of the trend, enter after a pullback resumes, fixed-risk bracket exit.

### Rules

| Component | Rule |
|---|---|
| Timeframe | 15-minute candles |
| Trend filter (long) | EMA20 > EMA50 AND close > EMA50 |
| Trend filter (short) | EMA20 < EMA50 AND close < EMA50 |
| Pullback (long) | RSI(14) dipped below 45 within the last 6 bars |
| Pullback (short) | RSI(14) rose above 55 within the last 6 bars |
| Entry trigger (long) | Candle closes above previous candle's high AND above EMA20 |
| Entry trigger (short) | Candle closes below previous candle's low AND below EMA20 |
| Stop loss | 1.2 × ATR(14) from entry (minimum 0.45% of price) |
| TP1 | entry + 1.5R → close 50% of position, move SL to breakeven |
| TP2 | entry + 3.0R → close remaining 50% |
| Session filter | 17:30–23:30 IST only (US session = best BTC liquidity/moves) |
| Daily limits | Max 3 trades/day; stop trading the day at −2% equity |
| Risk per trade | 1% of capital (₹500 on ₹50,000) |

R = distance from entry to stop loss.

### Position sizing (₹50,000 capital, BTC @ $62,000, ₹87/USD)

| Item | Value |
|---|---|
| Risk per trade | ₹500 (1%) |
| Typical SL distance | ~0.5% = ~$310 |
| Loss per lot if SL hit | $310 × 0.001 × 87 ≈ ₹27 |
| Position size | ₹500 ÷ ₹27 ≈ **18 lots (0.018 BTC)** |
| Notional | ~$1,116 ≈ ₹97,000 → **~2x effective leverage** |
| Margin used | ~₹5,000–10,000 of ₹50,000 (rest is drawdown buffer) |

Never size by leverage. Size by stop distance. High leverage (50–100x) on ₹50k means liquidation, not returns.

### Expected returns on ₹50,000 (honest numbers, fees included)

Round-trip fees+GST ≈ ₹80–115/trade ≈ 0.16–0.23R. ~30–40 trades/month.

| Scenario | Win rate | Net expectancy/trade | Monthly P&L | Monthly % |
|---|---|---|---|---|
| Bad month | 40% | −0.13R | **−₹2,000 to −₹2,600** | −4% to −5% |
| Break-even month | 45% | ~0R | **~₹0** | ~0% |
| Good month | 50% | +0.13R | **+₹1,900 to +₹2,600** | +4% to +5% |
| Great month | 55% | +0.26R | **+₹3,800 to +₹5,100** | +8% to +10% |

Realistic annual expectation if the edge holds: **20–50%/year with −10 to −15% drawdowns along the way.** Anyone promising 10%+ per month consistently is lying. Fees are the #1 killer — use limit orders (maker) for entries wherever possible.

### Capital allocation recommendation

| Item | Recommendation |
|---|---|
| Total capital | ₹50,000 |
| Deployed margin per trade | ~₹5,000–10,000 |
| Risk per trade | ₹500 (1%) |
| Max daily loss | ₹1,000 (2%) |
| Max open positions | 1 |
| Kill switch | Pause bot after 6% total drawdown; review |

## Sources
- [Delta Exchange contract specs](https://www.delta.exchange/contracts) · [Fees](https://www.delta.exchange/fees) · [VDA tax FAQ](https://www.delta.exchange/support/solutions/articles/80001132761-is-there-30-vda-tax-applicable-on-trading-profits-) · [API docs](https://docs.delta.exchange/) · [Crypto futures tax India (KoinX)](https://www.koinx.com/tax-guides/tax-on-crypto-futures-trading-india)

*Not financial advice. Futures trading can lose your entire capital. Validate on testnet/backtest before risking real money.*
