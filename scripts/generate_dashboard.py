import os, json, math, datetime as dt
from pathlib import Path

def load_events(p="reports/live_events.jsonl"):
    ev=[]; 
    if not os.path.exists(p): return ev
    with open(p,"r") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try: ev.append(json.loads(line))
            except: pass
    return ev

def sparkline_svg(series, w=600, h=120, pad=6):
    if not series: 
        return f'<svg width="{w}" height="{h}"></svg>'
    xs=list(range(len(series))); ys=series
    miny=min(ys); maxy=max(ys)
    rng=(maxy-miny) or 1.0
    def sx(i): 
        return pad + (w-2*pad) * (i/(len(xs)-1 if len(xs)>1 else 1))
    def sy(y): 
        return h-pad - (h-2*pad) * ((y-miny)/rng)
    path="M " + " ".join(f"{sx(i):.1f},{sy(ys[i]):.1f}" for i in range(len(xs)))
    zero_y = sy(0.0) if (miny<=0<=maxy) else None
    zero_line = f'<line x1="{pad}" y1="{zero_y:.1f}" x2="{w-pad}" y2="{zero_y:.1f}" stroke="#bbb" stroke-dasharray="3,3"/>' if zero_y is not None else ""
    return f'<svg width="{w}" height="{h}"><path d="{path}" fill="none" stroke="#0a0" stroke-width="2"/>{zero_line}</svg>'

def main():
    os.makedirs("reports", exist_ok=True)
    ev = load_events()
    last = ev[-1] if ev else {}
    eqR = [e.get("day_total_R",0.0) for e in ev]
    svg = sparkline_svg(eqR[-120:])  # recent window
    rows=""
    for e in ev[-20:][::-1]:
        rows += "<tr>" + "".join([
            f"<td>{e.get('ts','')}</td>",
            f"<td>{e.get('mode','')}</td>",
            f"<td>{e.get('trading','')}</td>",
            f"<td>{e.get('strategy','')}</td>",
            f"<td>{e.get('side','')}</td>",
            f"<td>{e.get('units','')}</td>",
            f"<td>{e.get('action','')}</td>",
            f"<td>{e.get('reason','')}</td>",
            f"<td>{e.get('day_total_R','')}</td>",
            f"<td>{e.get('trades_today','')}</td>",
        ]) + "</tr>\n"
    html=f"""<!doctype html>
<html><head><meta charset="utf-8"><title>AXFL Dashboard</title>
<style>
body{{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;background:#0b0d10;color:#e6e9ef;margin:20px}}
h1{{margin:0 0 8px 0}} .card{{background:#111418;border:1px solid #1a1f24;border-radius:12px;padding:16px;margin:10px 0}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
table{{width:100%;border-collapse:collapse}} th,td{{padding:6px 8px;border-bottom:1px solid #1f252b;font-size:12px}}
th{{text-align:left;color:#aab2bd}} .muted{{color:#aab2bd;font-size:12px}}
.badge{{display:inline-block;padding:2px 8px;border-radius:999px;background:#1d3b2a;color:#c7f0c2;border:1px solid #2b5a3c;font-weight:600}}
</style>
</head><body>
<h1>AXFL Live Dashboard</h1>
<div class="muted">Updated: {dt.datetime.utcnow().isoformat(timespec='seconds')}Z</div>

<div class="grid">
  <div class="card">
    <div><span class="badge">Latest</span></div>
    <div class="muted">Mode/Trading:</div>
    <div style="font-size:14px;margin:4px 0 8px 0">{last.get('mode','NA')} / {last.get('trading','NA')}</div>
    <div class="muted">Strategy / Action:</div>
    <div style="font-size:14px;margin:4px 0 8px 0">{last.get('strategy','NONE')} / {last.get('action','NA')} ({last.get('reason','')})</div>
    <div class="muted">Day Risk R / Trades Today:</div>
    <div style="font-size:14px;margin:4px 0 8px 0">{last.get('day_total_R',0.0)} / {last.get('trades_today',0)}</div>
  </div>
  <div class="card">
    <div><span class="badge">Day R Sparkline</span></div>
    {svg}
  </div>
</div>

<div class="card">
  <div style="margin-bottom:8px"><span class="badge">Recent Events</span></div>
  <table>
    <thead><tr>
      <th>Time (UTC)</th><th>Mode</th><th>Trading</th><th>Strategy</th><th>Side</th>
      <th>Units</th><th>Action</th><th>Reason</th><th>Day R</th><th>Trades</th>
    </tr></thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</div>
</body></html>"""
    Path("reports/m6_dashboard.html").write_text(html, encoding="utf-8")
    # Print a concise marker for the scheduler
    print(f"DASHBOARD_READY path=reports/m6_dashboard.html entries={len(ev)}")

if __name__=="__main__":
    main()
