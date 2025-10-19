"""
Multi-provider data facade with automatic fallback.
"""
import sys
import os
import time
import pandas as pd
import numpy as np
from typing import Literal, Optional
from datetime import datetime, timedelta

# Add scripts path for API modules
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'scripts'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'apis'))

from .symbols import normalize
from .yf_loader import get_intraday as yf_get_intraday


class DataProvider:
    """
    Multi-source data provider with automatic fallback.
    
    Supports TwelveData, Finnhub, and yfinance with intelligent routing.
    """
    
    def __init__(
        self,
        source: Literal["auto", "twelvedata", "finnhub", "yf"] = "auto",
        venue: Optional[str] = None,
        rotate: bool = True
    ):
        """
        Initialize data provider.
        
        Args:
            source: Data source selection
            venue: Venue for Finnhub (e.g., "OANDA")
            rotate: Enable API key rotation
        """
        self.source = source
        self.venue = venue
        self.rotate = rotate
        self.last_source_used = None
        self.last_symbol_used = None
    
    def get_intraday(
        self,
        symbol: str,
        interval: str = "1m",
        days: int = 20
    ) -> pd.DataFrame:
        """
        Get intraday OHLCV data with automatic provider selection.
        
        Args:
            symbol: Trading symbol
            interval: Time interval (1m, 2m, 5m, etc.)
            days: Number of days of history
        
        Returns:
            DataFrame with DatetimeIndex (UTC) and columns: Open, High, Low, Close, Volume
        """
        if self.source == "auto":
            # Try providers in order: TwelveData -> Finnhub -> yfinance
            providers = ["twelvedata", "finnhub", "yf"]
        else:
            providers = [self.source]
        
        last_error = None
        
        for provider in providers:
            try:
                print(f"[DataProvider] Attempting {provider}...")
                
                if provider == "twelvedata":
                    df = self._get_twelvedata(symbol, interval, days)
                elif provider == "finnhub":
                    df = self._get_finnhub(symbol, interval, days)
                elif provider == "yf":
                    df = self._get_yfinance(symbol, interval, days)
                else:
                    continue
                
                if df is not None and not df.empty and len(df) > 10:
                    self.last_source_used = provider
                    print(f"[DataProvider] ✓ Success with {provider}: {len(df)} bars")
                    return df
                else:
                    print(f"[DataProvider] {provider} returned insufficient data")
                    
            except Exception as e:
                last_error = e
                print(f"[DataProvider] {provider} failed: {e}")
                continue
        
        # All providers failed
        raise ValueError(f"All data providers failed. Last error: {last_error}")
    
    def _get_twelvedata(self, symbol: str, interval: str, days: int) -> pd.DataFrame:
        """Fetch data from TwelveData API."""
        try:
            from api_rotation import twelvedata_manager
            import requests
        except ImportError as e:
            raise ImportError(f"TwelveData dependencies not available: {e}")
        
        # Normalize symbol
        normalized_symbol = normalize(symbol, "twelvedata", self.venue)
        self.last_symbol_used = normalized_symbol
        
        print(f"[TwelveData] Normalized symbol: {normalized_symbol}")
        
        # Map interval
        interval_map = {
            "1m": "1min",
            "2m": "2min",
            "5m": "5min",
            "15m": "15min",
            "30m": "30min",
            "1h": "1h",
        }
        td_interval = interval_map.get(interval, "1min")
        
        # TwelveData limits historical data for free tier
        # Use time_series endpoint with outputsize
        api_key = twelvedata_manager.get_key()
        
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": normalized_symbol,
            "interval": td_interval,
            "apikey": api_key,
            "outputsize": min(5000, days * 1440),  # Max bars
            "format": "JSON"
        }
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if "status" in data and data["status"] == "error":
            raise ValueError(f"TwelveData API error: {data.get('message', 'Unknown error')}")
        
        if "values" not in data or not data["values"]:
            raise ValueError(f"No data returned from TwelveData for {normalized_symbol}")
        
        # Parse response
        records = data["values"]
        df = pd.DataFrame(records)
        
        # Rename and convert columns
        df = df.rename(columns={
            "datetime": "time",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        })
        
        # Convert to numeric
        for col in ["Open", "High", "Low", "Close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # Handle missing Volume (common in TwelveData FX)
        if "Volume" not in df.columns or df["Volume"].isna().all():
            df["Volume"] = 0
        else:
            df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)
        
        # Parse time and set as index
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time")
        df = df.sort_index()
        
        # Ensure UTC
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        
        # Select required columns
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        
        return df
    
    def _get_finnhub(self, symbol: str, interval: str, days: int) -> pd.DataFrame:
        """Fetch data from Finnhub API."""
        try:
            from api_rotation import finnhub_rest_manager
            import requests
        except ImportError as e:
            raise ImportError(f"Finnhub dependencies not available: {e}")
        
        # Normalize symbol
        normalized_symbol = normalize(symbol, "finnhub", self.venue)
        self.last_symbol_used = normalized_symbol
        
        print(f"[Finnhub] Normalized symbol: {normalized_symbol}")
        
        # Map interval to resolution (in minutes)
        interval_map = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "30m": "30",
            "60m": "60",
            "1h": "60",
        }
        resolution = interval_map.get(interval, "1")
        
        # Calculate time range
        end_time = int(time.time())
        start_time = end_time - (days * 86400)
        
        api_key = finnhub_rest_manager.get_key("rest")
        
        url = "https://finnhub.io/api/v1/forex/candle"
        params = {
            "symbol": normalized_symbol,
            "resolution": resolution,
            "from": start_time,
            "to": end_time,
            "token": api_key
        }
        
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code != 200:
            raise ValueError(f"Finnhub API error: HTTP {response.status_code} for {normalized_symbol}")
        
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("s") == "no_data":
            raise ValueError(f"No data returned from Finnhub for {normalized_symbol}")
        
        if "t" not in data or not data["t"]:
            raise ValueError(f"Invalid response from Finnhub for {normalized_symbol}")
        
        # Build DataFrame
        df = pd.DataFrame({
            "time": pd.to_datetime(data["t"], unit="s", utc=True),
            "Open": data["o"],
            "High": data["h"],
            "Low": data["l"],
            "Close": data["c"],
            "Volume": data.get("v", [0] * len(data["t"]))
        })
        
        df = df.set_index("time").sort_index()
        
        # Ensure numeric dtypes
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        df = df.dropna()
        
        return df
    
    def _get_yfinance(self, symbol: str, interval: str, days: int) -> pd.DataFrame:
        """Fetch data from yfinance (fallback)."""
        # Normalize symbol
        normalized_symbol = normalize(symbol, "yf", self.venue)
        self.last_symbol_used = normalized_symbol
        
        print(f"[yfinance] Normalized symbol: {normalized_symbol}")
        
        return yf_get_intraday(normalized_symbol, interval, days)
