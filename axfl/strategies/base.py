"""
Base strategy interface.
"""
from abc import ABC, abstractmethod
import pandas as pd
from typing import List, Dict, Any


class Strategy(ABC):
    """
    Abstract base class for trading strategies.
    """
    
    name: str = "BaseStrategy"
    
    def __init__(self, symbol: str, params: Dict[str, Any]):
        """
        Initialize strategy.
        
        Args:
            symbol: Trading symbol
            params: Strategy parameters
        """
        self.symbol = symbol
        self.params = params
    
    @abstractmethod
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare data by adding indicators and other derived columns.
        
        Args:
            df: OHLCV DataFrame
        
        Returns:
            DataFrame with additional columns
        """
        pass
    
    @abstractmethod
    def generate_signals(self, i: int, row: pd.Series, state: Dict) -> List[Dict]:
        """
        Generate trading signals for the current bar.
        
        Args:
            i: Current bar index
            row: Current bar data
            state: Strategy state dictionary (mutable)
        
        Returns:
            List of order dictionaries with keys:
            - action: 'open' or 'close'
            - side: 'long' or 'short'
            - price: float or None (None = market)
            - sl: stop-loss price or None
            - tp: take-profit price or None
            - notes: string with trade notes
        """
        pass
    
    def on_fill(self, trade_state: Dict) -> None:
        """
        Optional callback when a trade is filled.
        
        Args:
            trade_state: Dictionary with trade information
        """
        pass
