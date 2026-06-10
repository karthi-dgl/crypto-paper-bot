# AI Model — How to Run It (4 commands)

Full design and the 27 strategy signals: see **STRATEGY_AI.md**.

```bash
cd CRYPTO_BOT\ai
pip install pandas scikit-learn numpy requests

python fetch_data.py 365      # 1) download 1 year of BTC 15m candles (use 730 for 2 yrs)
python train.py               # 2) build 30+ features, walk-forward train (a few minutes)
python backtest_ai.py         # 3) simulate Rs 50,000 on months the AI never saw
python predict.py             # 4) ask the AI: what trade NOW? (uses the margin step 3 selected automatically)
```

## How to read backtest_ai.py output

- **Tuning table** — picks the confidence threshold on the first half of unseen data.
- **FINAL VERDICT** — the only numbers that matter. Second half of unseen data,
  nothing was fitted on it. If net P&L is positive with profit factor > 1.3 and
  drawdown < 15%, the AI found a real edge. If negative — the honest answer is
  the edge isn't there yet; we add data/features, we do NOT trade it.
- **By market phase** — shows whether profits come from trends, accumulation or
  distribution. The AI learns this itself from the `phase` feature.

## What "good" looks like (so you can't be fooled)

| Metric | Good | Suspicious (overfit) |
|---|---|---|
| Win rate at 2R | 38–50% | > 65% |
| Profit factor | 1.3–1.8 | > 2.5 |
| Max drawdown | < 15% | < 3% |
| Trades/month | 15–60 | > 200 |

## Re-training

Re-run steps 1–3 monthly so the model learns recent market behaviour.
More history = better: `python fetch_data.py 1095` (3 years) if the API has it.

## Reality check

The model decides **when the odds favour a trade and when to sit out** — that's its
edge over fixed strategies. It cannot make 6x in a year on Rs 50,000 with 1% risk;
nothing legitimate can promise that. Taxes are paid on profit at your slab rate, so
ANY profit is real money in your pocket — you do not need Rs 3,00,000 to "break even".
