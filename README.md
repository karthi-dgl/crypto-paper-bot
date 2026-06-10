# CRYPTO_BOT — BTC Intraday Bot for Delta Exchange India

Automated BTC futures bot: detects a trend-pullback setup on 15-minute candles, enters with a fixed ₹500 (1%) risk, exits via stop loss / TP1 / TP2 automatically. Strategy details and return projections: see **STRATEGY.md**.

## How it works (simple version)

1. Every 15 minutes the bot downloads fresh BTCUSD candles from Delta India.
2. It checks: is BTC trending? Did price pull back and resume? (EMA 20/50 + RSI rules)
3. If yes → it calculates how many lots to buy/sell so a stop-loss hit loses only ₹500.
4. It places 4 orders at once: entry, stop loss, TP1 (half position), TP2 (rest).
5. After TP1 fills, the stop moves to breakeven — the trade can no longer lose.
6. Built-in safety: max 3 trades/day, stops for the day at −2%, kills itself at −6% total.

## Files

| File | Purpose |
|---|---|
| `STRATEGY.md` | Full strategy, sizing, return projections |
| `config.py` | All settings (capital, risk, strategy params, mode) |
| `strategy.py` | Indicators + entry/exit signal logic |
| `delta_client.py` | Delta India REST API wrapper (auth, orders, candles) |
| `bot.py` | The live loop — run this |
| `backtest.py` | Test the strategy on real historical candles first |

## Setup (do in this order)

```bash
pip install requests
```

**Step 1 — Backtest** (no account needed, public data):
```bash
python backtest.py 60        # last 60 days
```

**Step 2 — Paper trade** (no account needed, simulated fills on live prices):
```bash
python bot.py                # MODE defaults to "paper"
```
Let it run during 17:30–23:30 IST for 2–4 weeks. Check `trades.csv`.

**Step 3 — Testnet** (real orders, fake money):
1. Create a demo account at https://testnet.delta.exchange/
2. Generate API key + secret there.
3. Run:
```bash
set BOT_MODE=testnet
set DELTA_API_KEY=your_key
set DELTA_API_SECRET=your_secret
python bot.py
```

**Step 4 — Live** — only after paper + testnet results match the backtest for several weeks. Create API keys on https://india.delta.exchange (trading permission only, NO withdrawal permission), set `BOT_MODE=live`. Start with the smallest size.

## Warnings

- Past performance ≠ future returns. Expect losing weeks and months.
- Never give an API key withdrawal permission.
- The bot needs your computer on and connected during session hours (or deploy to a small cloud VM).
- Update `USDINR` in config.py occasionally.
- Futures trading is high risk — you can lose the full ₹50,000. Not financial advice.
