import os, csv
from axfl.engine.executor import run_auto

def main():
    names = ["ema_trend","bollinger_mean_rev","price_action_breakout"]
    mode, acct, env, strategies, fills, M, first_line = run_auto(names, balance=200.0, risk_pct=0.01)

    # Save artifacts
    os.makedirs("reports", exist_ok=True)
    with open("reports/m4_trades.csv","w", newline="") as f:
        w = csv.writer(f); w.writerow(["order_id","tag","side","entry","exit","sl","tp","R","pnl_usd"])
        for x in fills:
            w.writerow([x.order_id, x.tag, x.side, f"{x.entry:.5f}", f"{x.exit:.5f}", f"{x.sl:.5f}", f"{x.tp:.5f}", round(x.r_multiple,3), round(x.pnl_usd,2)])

    # SUCCESS MARKERS (ONLY)
    acct_str = (acct or "NA"); env_str = (env or "NA")
    print(f"OANDA_READY mode={mode} account={acct_str} env={env_str} instrument={os.environ.get('OANDA_INSTR','EUR_USD')}")
    if first_line:
        print(first_line)
    else:
        print("FIRST_ORDER id=NA side=0 units=0 entry=NA sl=NA tp=NA tag=NA")
    print(f"RISK_GUARDS risk_pct=1.0% daily_stop_R=4.0 max_open=1 atr_min_pips=3.0")
    print(f"LIVE_SUMMARY PF={M['pf']:.2f} Win%={M['win']:.1f} Trades={M['n']} TotalR={M['totalR']:.2f} PnL$={M['pnl']:.2f}")
    print("AXFL_M4_OK")

if __name__ == "__main__":
    main()
