"""Generates the dashboard (docs/index.html) from paper_trades.db — served free by GitHub Pages."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

CAPITAL = 50_000
TAX_RATE = 0.30          # slab-rate reserve, conservative; confirm with your CA
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "docs", "index.html")

CSS = """
body{font-family:system-ui,Segoe UI,Roboto,sans-serif;background:#0f1419;color:#e6e6e6;margin:0;padding:16px}
h1{font-size:1.3em}.sub{color:#8b98a5;font-size:.85em}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}
.card{background:#1a2129;border-radius:10px;padding:12px}.card .v{font-size:1.25em;font-weight:700;margin-top:4px}
.green{color:#4caf7d}.red{color:#e0245e}.amber{color:#ffad1f}
table{width:100%;border-collapse:collapse;font-size:.85em}
th,td{padding:7px 8px;text-align:right;border-bottom:1px solid #222c36}
th{color:#8b98a5;font-weight:600}td:first-child,th:first-child{text-align:left}
tr.open{background:#16202b}a{color:#1d9bf0;text-decoration:none}
details{background:#1a2129;border-radius:8px;margin:6px 0;padding:8px 12px}
summary{cursor:pointer}.detail-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:6px;padding:8px 0;font-size:.85em}
.detail-grid div b{color:#8b98a5;font-weight:600;display:block;font-size:.8em}
"""


def fmt(v, money=False):
    if v is None:
        return "—"
    return f"₹{v:+,.0f}" if money else v


def build(con, last_price=None):
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM trades ORDER BY open_epoch DESC").fetchall()]
    closed = [r for r in rows if r["status"] == "CLOSED"]
    open_t = [r for r in rows if r["status"] == "OPEN"]
    net = sum(r["net_pnl"] or 0 for r in closed)
    fees = sum(r["fees"] or 0 for r in closed)
    wins = [r for r in closed if (r["net_pnl"] or 0) > 0]
    losses = [r for r in closed if (r["net_pnl"] or 0) <= 0]
    pf = (sum(r["net_pnl"] for r in wins) / abs(sum(r["net_pnl"] for r in losses))
          if losses and sum(r["net_pnl"] for r in losses) else 0)
    equity = CAPITAL + net
    tax = max(net, 0) * TAX_RATE
    cls = "green" if net >= 0 else "red"

    # equity curve points (chronological)
    eq, pts = CAPITAL, [CAPITAL]
    for r in sorted(closed, key=lambda r: r["close_epoch"] or 0):
        eq += r["net_pnl"] or 0
        pts.append(round(eq))

    def trade_rows():
        out = []
        for r in rows:
            pnl = r["net_pnl"]
            pcls = "green" if (pnl or 0) > 0 else ("red" if pnl is not None else "amber")
            out.append(f"""<tr class="{'open' if r['status'] == 'OPEN' else ''}">
<td><a href="#t{r['id']}">#{r['id']}</a></td><td>{r['side']}</td>
<td>{r['open_time']}</td><td>{r['close_time'] or 'OPEN'}</td>
<td>{r['lots']}</td><td>₹{r['notional_inr']:,.0f}</td>
<td>${r['entry']:,.0f}</td><td>{('$%s' % format(r['exit_price'], ',.0f')) if r['exit_price'] else '—'}</td>
<td>{r['outcome'] or '…'}</td><td class="{pcls}">{fmt(pnl, True) if pnl is not None else 'running'}</td></tr>""")
        return "\n".join(out)

    def trade_details():
        out = []
        for r in rows:
            items = [("Status", r["status"]), ("Side", r["side"]), ("Lots", r["lots"]),
                     ("Open", r["open_time"]), ("Close", r["close_time"] or "still open"),
                     ("Entry", f"${r['entry']:,.1f}"), ("Stop loss", f"${r['sl']:,.1f}"),
                     ("TP1", f"${r['tp1']:,.1f}"), ("TP2", f"${r['tp2']:,.1f}"),
                     ("Exit", f"${r['exit_price']:,.1f}" if r["exit_price"] else "—"),
                     ("Outcome", r["outcome"] or "—"),
                     ("Capital used (notional)", f"₹{r['notional_inr']:,.0f}"),
                     ("Margin @10x approx", f"₹{r['notional_inr'] / 10:,.0f}"),
                     ("Gross P&L", fmt(r["gross_pnl"], True)),
                     ("Fees+GST", f"₹{r['fees']:,.0f}" if r["fees"] else "—"),
                     ("Net P&L", fmt(r["net_pnl"], True)),
                     ("AI edge", f"{r['edge']:+.1%}"), ("Market phase", r["phase"])]
            grid = "".join(f"<div><b>{k}</b>{v}</div>" for k, v in items)
            out.append(f'<details id="t{r["id"]}"><summary>Trade #{r["id"]} — {r["side"]} '
                       f'{r["open_time"]} — {r["outcome"] or "OPEN"}</summary>'
                       f'<div class="detail-grid">{grid}</div></details>')
        return "\n".join(out)

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BTC AI Paper Trading</title><style>{CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script></head><body>
<h1>BTC AI Paper Trading — Delta India (simulated)</h1>
<div class="sub">Updated {datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%d %b %Y %H:%M IST')}
{f" · BTC ${last_price:,.0f}" if last_price else ""} · capital ₹{CAPITAL:,} · paper money only</div>
<div class="cards">
<div class="card">Equity<div class="v {cls}">₹{equity:,.0f}</div></div>
<div class="card">Net P&L<div class="v {cls}">{fmt(net, True)}</div></div>
<div class="card">Trades<div class="v">{len(closed)} closed / {len(open_t)} open</div></div>
<div class="card">Win rate<div class="v">{(len(wins) / len(closed) * 100) if closed else 0:.0f}%</div></div>
<div class="card">Profit factor<div class="v">{pf:.2f}</div></div>
<div class="card">Fees paid<div class="v">₹{fees:,.0f}</div></div>
<div class="card">Tax reserve (30%)<div class="v amber">₹{tax:,.0f}</div></div>
<div class="card">After-tax P&L<div class="v {cls}">{fmt(net - tax, True)}</div></div>
</div>
<canvas id="eq" height="90"></canvas>
<h3>Trades</h3>
<table><tr><th>ID</th><th>Side</th><th>Open time</th><th>Close time</th><th>Lots</th>
<th>Capital used</th><th>Entry</th><th>Exit</th><th>Outcome</th><th>Net P&L</th></tr>
{trade_rows()}</table>
<h3>Trade details</h3>
{trade_details()}
<p class="sub">Simulated fills with maker/taker fees + 18% GST and 1-tick slippage. Tax reserve
assumes 30% slab on profits (futures = business income; confirm with a CA). Not financial advice.</p>
<script>
new Chart(document.getElementById('eq'),{{type:'line',
data:{{labels:{list(range(len(pts)))},datasets:[{{data:{pts},borderColor:'#1d9bf0',
backgroundColor:'rgba(29,155,240,.15)',fill:true,tension:.25,pointRadius:0}}]}},
options:{{plugins:{{legend:{{display:false}}}},scales:{{x:{{display:false}},
y:{{grid:{{color:'#222c36'}}}}}}}}}});
</script></body></html>"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  dashboard -> {OUT}")
