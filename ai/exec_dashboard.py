"""Local dashboard for testnet executor trades -> ai/executor_dashboard.html"""
import csv
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
HERE = os.path.dirname(os.path.abspath(__file__))
TRADES_CSV = os.path.join(HERE, "executor_trades.csv")
STATE = os.path.join(HERE, "executor_state.json")
OUT = os.path.join(HERE, "executor_dashboard.html")
CAPITAL = 50_000
TAX_RATE = 0.30

CSS = """body{font-family:system-ui,sans-serif;background:#0f1419;color:#e6e6e6;margin:0;padding:16px}
h1{font-size:1.2em}.sub{color:#8b98a5;font-size:.85em}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:14px 0}
.card{background:#1a2129;border-radius:10px;padding:12px}.card .v{font-size:1.2em;font-weight:700;margin-top:4px}
.green{color:#4caf7d}.red{color:#e0245e}.amber{color:#ffad1f}
table{width:100%;border-collapse:collapse;font-size:.85em}
th,td{padding:7px 8px;text-align:right;border-bottom:1px solid #222c36}
th{color:#8b98a5;font-weight:600}td:first-child,th:first-child{text-align:left}
tr.open{background:#16202b}"""


def load_trades():
    if not os.path.exists(TRADES_CSV):
        return []
    with open(TRADES_CSV) as f:
        return list(csv.DictReader(f))


def build():
    rows = load_trades()
    try:
        st = json.load(open(STATE))
    except (FileNotFoundError, json.JSONDecodeError):
        st = {}
    pnl = [float(r["net_pnl"]) for r in rows]
    net = sum(pnl)
    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) else (9.99 if wins else 0)
    fees = sum(float(r["fees"]) for r in rows)
    tax = max(net, 0) * TAX_RATE
    cls = "green" if net >= 0 else "red"

    open_html = ""
    if st.get("active"):
        open_html = (f'<tr class="open"><td>OPEN</td><td>{st["side"]}</td>'
                     f'<td>—</td><td>{st["lots"]}</td><td>${st["entry"]:,.0f}</td>'
                     f'<td>SL {st.get("sl", 0):,.0f}</td><td>running</td><td class="amber">…</td></tr>')

    body_rows = "\n".join(
        f'<tr><td>{r["open_time"]}</td><td>{r["side"]}</td><td>{r["close_time"]}</td>'
        f'<td>{r["lots"]}</td><td>${float(r["entry"]):,.0f}</td>'
        f'<td>${float(r["exit_price"]):,.0f}</td><td>{r["outcome"]}</td>'
        f'<td class="{"green" if float(r["net_pnl"]) > 0 else "red"}">'
        f'₹{float(r["net_pnl"]):+,.0f}</td></tr>'
        for r in reversed(rows))

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="120">
<title>Testnet Executor</title><style>{CSS}</style></head><body>
<h1>Testnet executor — real orders, demo money</h1>
<div class="sub">Updated {datetime.now(IST).strftime('%d %b %Y %I:%M %p IST')} ·
session 5:30 PM – 11:30 PM IST · auto-refreshes every 2 min</div>
<div class="cards">
<div class="card">Net P&L<div class="v {cls}">₹{net:+,.0f}</div></div>
<div class="card">Trades closed<div class="v">{len(rows)}</div></div>
<div class="card">Win rate<div class="v">{(len(wins) / len(rows) * 100) if rows else 0:.0f}%</div></div>
<div class="card">Profit factor<div class="v">{pf:.2f}</div></div>
<div class="card">Fees (est)<div class="v">₹{fees:,.0f}</div></div>
<div class="card">Tax reserve 30%<div class="v amber">₹{tax:,.0f}</div></div>
<div class="card">After-tax<div class="v {cls}">₹{net - tax:+,.0f}</div></div>
</div>
<table><tr><th>Open (IST)</th><th>Side</th><th>Close (IST)</th><th>Lots</th>
<th>Entry</th><th>Exit</th><th>Outcome</th><th>Net P&L</th></tr>
{open_html}
{body_rows}</table>
<p class="sub">Source: actual fills on Delta India testnet. Fees estimated
(maker entries/TPs, taker stops, 18% GST). Not financial advice.</p>
</body></html>"""
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    return OUT


def append_trade(row):
    new = not os.path.exists(TRADES_CSV)
    with open(TRADES_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["open_time", "side", "lots", "entry",
                                          "close_time", "exit_price", "outcome",
                                          "gross_pnl", "fees", "net_pnl"])
        if new:
            w.writeheader()
        w.writerow(row)
