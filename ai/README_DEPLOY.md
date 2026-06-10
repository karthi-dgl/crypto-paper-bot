# Put the Paper-Trading Bot Online — FREE (no server, no credit card)

The trick: **GitHub Actions** is a free computer in the cloud that runs our engine every
15 minutes, and **GitHub Pages** hosts the dashboard as a free website. Your PC can be
off, power can fail — nothing stops.

## One-time setup (~15 minutes)

1. **Create a GitHub account** (free): https://github.com/signup

2. **Create a new repository**: click "+" → New repository → name it `crypto-paper-bot`
   → select **Public** (public = unlimited free Actions minutes) → Create.
   The repo is public, but it contains NO API keys and NO real money — only paper trades.

3. **Upload the project**. Easiest way (no git knowledge needed):
   - On the repo page: "uploading an existing file"
   - Drag the ENTIRE contents of your `CRYPTO_BOT` folder
     (including the hidden `.github` folder, `requirements.txt`, and the whole `ai\` folder
     with `model.pkl` and `threshold.txt`) → Commit.
   - If drag-drop skips the `.github` folder, create the two files manually:
     repo → Add file → Create new file → name `.github/workflows/trade.yml` → paste contents;
     same for `retrain.yml`.

4. **Enable the dashboard website**: repo → Settings → Pages →
   Source: "Deploy from a branch" → Branch: `main`, folder `/docs` → Save.

5. **Allow the bot to save results**: repo → Settings → Actions → General →
   Workflow permissions → select "Read and write permissions" → Save.

6. **Test it now**: repo → Actions tab → "paper-trade" → "Run workflow".
   Green tick = it worked. After ~2 minutes your dashboard is live at:

   **https://YOUR-USERNAME.github.io/crypto-paper-bot/**

   Bookmark that on your phone. That's your link.

## What happens automatically after that

| When | What |
|---|---|
| Every 15 min, 17:30–23:30 IST | Engine wakes up, updates open trades, asks the AI, records to DB, refreshes dashboard |
| Every Sunday 16:00 IST | Re-downloads 1 year of data, retrains the ensemble, re-validates, commits the new model |
| Always | Dashboard shows equity, every trade with open/close time, lots, capital used, P&L, fees, tax reserve |

## Notes & limits (honest ones)

- GitHub cron is not exact — runs can start 2–10 min late. For 15-minute candles this is
  fine (the engine always evaluates the last CLOSED candle, and replays anything it missed).
- Everything is paper. No keys, no withdrawals possible, nothing to hack.
- To stop it: repo → Actions → paper-trade → "…" → Disable workflow.
- To change capital/risk: edit `engine.py` (CAPITAL) and `signal_logger.py` (RISK).
- After 3–4 weeks, judge it: dashboard profit factor > 1.3 → we build the real testnet
  executor. Below 1.1 → back to research, and it cost you ₹0 to find out.
