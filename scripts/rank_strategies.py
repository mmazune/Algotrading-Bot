import os, json, math, datetime as dt
import pandas as pd
from pathlib import Path
try:
    from axfl.notify.discord import send_discord, GREEN, RED, BLUE
except Exception:
    def send_discord(*a, **k): return 0
    GREEN=0x16A34A; RED=0xDC2626; BLUE=0x3B82F6

PIP=0.0001

def _load_ledger():
    p=Path("reports/m10_ledger.json")
    if not p.exists(): return []
    try:
        L=json.loads(p.read_text())
    except Exception:
        return []
    return L.get("closed",[])

def _to_df(closed):
    rows=[]
    for r in closed:
        try:
            ts = pd.to_datetime(r.get("ts"))
            strat = r.get("strategy","UNK")
            side  = int(r.get("side",0))
            entry = float(r.get("entry"))
            sl    = float(r.get("sl"))
            exitp = float(r.get("exit_price")) if r.get("exit_price") is not None else None
            lastR = float(r.get("lastR", "nan")) if r.get("lastR") is not None else None
            if (lastR is None or math.isnan(lastR)) and exitp:
                denom = (entry-sl) if side==1 else (sl-entry)
                if denom>0:
                    num = (exitp-entry) if side==1 else (entry-exitp)
                    lastR = num/denom
            rows.append({"ts":ts,"strategy":strat,"lastR":lastR})
        except Exception:
            pass
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["ts","strategy","lastR"])

def _periods(now=None):
    now = now or pd.Timestamp.utcnow()
    # last 7 days (inclusive of today)
    week_from = now.normalize() - pd.Timedelta(days=6)
    # previous month
    first_this = now.normalize().replace(day=1)
    last_month_end = first_this - pd.Timedelta(days=1)
    first_prev = last_month_end.replace(day=1)
    return (week_from, now), (first_prev, last_month_end)

def _rank(df, start, end):
    if df.empty: return pd.DataFrame(columns=["strategy","sumR","trades","rank"])
    m = (df["ts"]>=start) & (df["ts"]<=end) & df["lastR"].notna()
    g = df.loc[m].groupby("strategy")["lastR"].agg(["sum","count"]).reset_index()
    g.columns=["strategy","sumR","trades"]
    g["rank"]=g["sumR"].rank(ascending=False, method="dense")
    return g.sort_values(["sumR","trades"], ascending=[False,False])

def _embed(title, tbl, start, end, color):
    lines=[]
    for _,row in tbl.head(5).iterrows():
        lines.append(f"**{row['strategy']}** — {row['sumR']:.2f}R  ({int(row['trades'])} trades)")
    if not lines:
        lines=["No closed trades in period."]
    desc="\n".join(lines)
    return {"title":title, "description":f"{start.date()} → {end.date()}\n{desc}"}, color

def main():
    os.makedirs("reports", exist_ok=True)
    closed=_load_ledger()
    df=_to_df(closed)
    (w_from, w_to), (m_from, m_to) = _periods()
    wk=_rank(df, w_from, w_to); mo=_rank(df, m_from, m_to)
    wk.to_csv("reports/strat_rank_week.csv", index=False)
    mo.to_csv("reports/strat_rank_month.csv", index=False)

    emb,color = _embed("WEEKLY RANK (R total)", wk, w_from, w_to, GREEN)
    send_discord("**WEEKLY_RANK**", embeds=[emb], color=color)
    emb2,color2 = _embed("MONTHLY RANK (R total)", mo, m_from, m_to, BLUE)
    send_discord("**MONTHLY_RANK**", embeds=[emb2], color=color2)

    win = wk["strategy"].iloc[0] if len(wk)>0 else "NA"
    mwin= mo["strategy"].iloc[0] if len(mo)>0 else "NA"
    print(f"RANK_WEEK top={win} rows={len(wk)} file=reports/strat_rank_week.csv")
    print(f"RANK_MONTH top={mwin} rows={len(mo)} file=reports/strat_rank_month.csv")
    print("AXFL_RANK_OK")

if __name__ == "__main__":
    main()
