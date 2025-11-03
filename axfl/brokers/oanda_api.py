from __future__ import annotations
import os, json, time, urllib.request, urllib.error, urllib.parse
from typing import Optional, Tuple, Dict, Any, List
import pandas as pd

OANDA_PRACTICE = "https://api-fxpractice.oanda.com"
OANDA_LIVE = "https://api-fxtrade.oanda.com"

def oanda_detect() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    key = os.environ.get("OANDA_API_KEY") or os.environ.get("OANDA_TOKEN")
    acct = os.environ.get("OANDA_ACCOUNT_ID")
    env = (os.environ.get("OANDA_ENV") or "practice").lower()
    if env not in ("practice","live"):
        env = "practice"
    return key, acct, env

class OandaClient:
    def __init__(self, api_key: str, account_id: str, env: str = "practice"):
        self.api_key = api_key
        self.account_id = account_id
        self.base = OANDA_LIVE if env == "live" else OANDA_PRACTICE

    def _req(self, method: str, path: str, data: Dict[str, Any] | None = None) -> Tuple[int, Dict[str, Any]]:
        url = f"{self.base}{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                code = r.getcode()
                text = r.read().decode("utf-8")
                return code, (json.loads(text) if text else {})
        except urllib.error.HTTPError as e:
            try:
                text = e.read().decode("utf-8")
                return e.code, (json.loads(text) if text else {"error": text})
            except Exception:
                return e.code, {"error": str(e)}
        except Exception as e:
            return 0, {"error": str(e)}

    def account_summary(self) -> Tuple[int, Dict[str, Any]]:
        return self._req("GET", f"/v3/accounts/{self.account_id}/summary")

    # === NEW: Orders/Trades ===
    def place_market_order(self, instrument: str, units: int, sl: float | None = None, tp: float | None = None, tag: str = "") -> Tuple[int, Dict[str, Any]]:
        order: Dict[str, Any] = {
            "order": {
                "units": str(units),  # positive buy, negative sell per OANDA v20
                "instrument": instrument,
                "timeInForce": "FOK",
                "type": "MARKET",
                "positionFill": "DEFAULT",
                "clientExtensions": {"tag": tag} if tag else {},
            }
        }
        if sl is not None:
            order["order"]["stopLossOnFill"] = {"price": f"{sl:.5f}"}
        if tp is not None:
            order["order"]["takeProfitOnFill"] = {"price": f"{tp:.5f}"}
        return self._req("POST", f"/v3/accounts/{self.account_id}/orders", order)

    def open_trades(self) -> Tuple[int, Dict[str, Any]]:
        return self._req("GET", f"/v3/accounts/{self.account_id}/openTrades")

    def close_trade(self, trade_id: str) -> Tuple[int, Dict[str, Any]]:
        return self._req("PUT", f"/v3/accounts/{self.account_id}/trades/{trade_id}/close", {"units":"ALL"})

    def close_trade_units(self, trade_id: str, units: str = "ALL") -> Tuple[int, Dict[str, Any]]:
        return self._req("PUT", f"/v3/accounts/{self.account_id}/trades/{trade_id}/close", {"units": units})

    def close_position(self, instrument: str, side: str) -> Tuple[int, Dict[str, Any]]:
        # side in {"long","short"}
        payload = {"longUnits":"ALL"} if side=="long" else {"shortUnits":"ALL"}
        return self._req("PUT", f"/v3/accounts/{self.account_id}/positions/{instrument}/close", payload)

    def latest_m5(self, instrument: str = "EUR_USD") -> tuple[int, dict]:
        return self._req("GET", f"/v3/instruments/{instrument}/candles?granularity=M5&count=2&price=M")

def _parse_oanda_candles(payload: Dict[str, Any], granularity: str) -> pd.DataFrame:
    c = payload.get("candles", [])
    if not c:
        return pd.DataFrame(columns=["open","high","low","close"])
    # OANDA returns time in RFC3339; prices in mid.{o,h,l,c}
    rows = []
    for bar in c:
        t = bar["time"]
        mid = bar.get("mid") or {}
        rows.append([t, float(mid.get("o","nan")), float(mid.get("h","nan")), float(mid.get("l","nan")), float(mid.get("c","nan"))])
    df = pd.DataFrame(rows, columns=["time","open","high","low","close"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    return df

def fetch_oanda_candles(client: OandaClient, instrument: str = "EUR_USD", granularity: str = "M5", count: int = 1500) -> Tuple[int, pd.DataFrame]:
    path = f"/v3/instruments/{instrument}/candles?granularity={granularity}&count={count}&price=M"
    code, payload = client._req("GET", path)
    if code != 200:
        return code, pd.DataFrame()
    df = _parse_oanda_candles(payload, granularity)
    return code, df
