"""Configuration for the Delta India BTC bot. Keys come from environment variables."""
import os

# --- Mode: "paper" (simulated fills, no orders sent) or "testnet" (real orders on demo) or "live"
MODE = os.getenv("BOT_MODE", "paper")

BASE_URLS = {
    "paper":   "https://api.india.delta.exchange",        # public data only
    "testnet": "https://cdn-ind.testnet.deltaex.org",     # demo account API keys
    "live":    "https://api.india.delta.exchange",
}
BASE_URL = BASE_URLS[MODE]

API_KEY = os.getenv("DELTA_API_KEY", "")
API_SECRET = os.getenv("DELTA_API_SECRET", "")

# --- Instrument
SYMBOL = "BTCUSD"
PRODUCT_ID = 27          # BTCUSD perpetual on Delta India
LOT_BTC = 0.001          # 1 contract = 0.001 BTC
USDINR = 87.0            # used only to convert risk; update periodically

# --- Strategy parameters (TP-15)
RESOLUTION = "15m"
EMA_FAST, EMA_SLOW = 20, 50
RSI_LEN = 14
RSI_PULLBACK_LONG = 45   # RSI must have dipped below this recently (long)
RSI_PULLBACK_SHORT = 55
PULLBACK_LOOKBACK = 6    # bars
ATR_LEN = 14
SL_ATR_MULT = 1.2
SL_MIN_PCT = 0.0045      # minimum stop distance: 0.45% of price
TP1_R, TP2_R = 1.5, 3.0  # take-profit multiples of risk

# --- Risk management
CAPITAL_INR = 50_000
RISK_PCT = 0.01          # 1% = Rs 500 per trade
MAX_TRADES_PER_DAY = 3
MAX_DAILY_LOSS_PCT = 0.02
MAX_DRAWDOWN_KILL = 0.06  # stop the bot entirely

# --- Session filter (IST). US session = best BTC liquidity.
SESSION_START = "17:30"
SESSION_END = "23:30"
TIMEZONE = "Asia/Kolkata"

# --- v2: fees, entry blackout, higher-timeframe trend filter
FEE_TAKER = 0.0005 * 1.18    # market orders (SL exits)
FEE_MAKER = 0.0002 * 1.18    # limit orders (entries, TP exits)
BLACKOUT_START = "20:00"     # no NEW entries during NY-open whipsaw
BLACKOUT_END = "22:30"       # (existing positions keep running)
HTF_MINUTES = 60             # 1h trend must agree with 15m signal
HTF_EMA_FAST, HTF_EMA_SLOW = 20, 50
ENTRY_FILL_BARS = 1          # cancel limit entry if not filled within N bars
