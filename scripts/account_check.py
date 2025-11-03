import os, json
from axfl.brokers.oanda_api import oanda_detect, OandaClient

def main():
    key, acct, env = oanda_detect()
    if not key or not acct:
        print("TEST_ACCOUNT mode=SIM balance=NA nav=NA marginAvail=NA currency=NA reason=no_creds")
        return
    cli = OandaClient(key, acct, env)
    code, payload = cli._req("GET", f"/v3/accounts/{acct}/summary")
    if code != 200:
        print(f"TEST_ACCOUNT mode=OANDA error=http_{code}")
        return
    a = payload.get("account", {})
    bal = a.get("balance","NA")
    nav = a.get("NAV","NA")
    ma  = a.get("marginAvailable","NA")
    cur = a.get("currency","NA")
    try:
        balf=float(bal); ok = (90.0 <= balf <= 110.0)
        ok_txt = "OK" if ok else "WARN"
    except Exception:
        ok_txt="NA"
    print(f"TEST_ACCOUNT mode=OANDA balance={bal} nav={nav} marginAvail={ma} currency={cur} approx100={ok_txt}")

if __name__ == "__main__":
    main()
