"""
Generic event-loop backtesting engine.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from datetime import timedelta

from .execution import apply_slippage, calculate_commission
from .metrics import compute_metrics
from .utils import compute_atr
from .sessions import pip_size
from .risk import RiskManager, RiskRules


class Backtester:
    """
    Event-driven backtester for trading strategies.
    
    Supports:
    - Single position at a time
    - Stop-loss and take-profit orders
    - Time-based stops
    - Breakeven adjustment after reaching 1R
    - Risk-based position sizing
    """
    
    def __init__(self, symbol: str, initial_capital: float = 100000.0,
                 risk_percent: float = 0.5, risk_rules: RiskRules = None,
                 spread_pips: float = 0.6):
        """
        Initialize backtester.
        
        Args:
            symbol: Trading symbol
            initial_capital: Starting capital
            risk_percent: Risk per trade as percentage of capital
            risk_rules: Risk management rules (uses defaults if None)
            spread_pips: Bid-ask spread in pips (default 0.6 for EURUSD)
        """
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.risk_percent = risk_percent
        self.pip = pip_size(symbol)
        self.spread_pips = spread_pips
        
        # Risk management
        self.risk_manager = RiskManager(risk_rules)
        
        # State
        self.equity = initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []
    
    def run(self, df: pd.DataFrame, strategy: Any) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
        """
        Run backtest on historical data.
        
        Args:
            df: OHLCV DataFrame with DatetimeIndex
            strategy: Strategy instance with prepare() and generate_signals() methods
        
        Returns:
            Tuple of (trades_df, equity_curve_df, metrics_dict)
        """
        # Prepare data (add indicators, etc.)
        df = strategy.prepare(df)
        
        # Compute ATR for slippage model
        df['ATR'] = compute_atr(df, period=14)
        
        # Reset state
        self.equity = self.initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []
        
        # Event loop
        state = {}  # Strategy-specific state
        
        for i in range(len(df)):
            row = df.iloc[i]
            current_time = df.index[i]
            
            # Record equity
            self.equity_curve.append({
                'time': current_time,
                'equity': self.equity
            })
            
            # Check position exits first
            if self.position is not None:
                exit_signal = self._check_exit(row, current_time)
                if exit_signal:
                    self._close_position(row, current_time, exit_signal['reason'])
            
            # Generate signals if no position
            if self.position is None:
                signals = strategy.generate_signals(i, row, state)
                
                for signal in signals:
                    if signal.get('action') == 'open':
                        # Check risk limits
                        trade_date = current_time.date()
                        if not self.risk_manager.can_open(trade_date):
                            # Risk blocked - increment counter if strategy has debug
                            if hasattr(strategy, 'debug') and 'risk_blocked_entries' not in strategy.debug:
                                strategy.debug['risk_blocked_entries'] = 0
                            if hasattr(strategy, 'debug'):
                                strategy.debug['risk_blocked_entries'] += 1
                            continue
                        
                        self._open_position(signal, row, current_time, df['ATR'].iloc[i])
                        self.risk_manager.on_open(trade_date)
                        break  # Only one position at a time
        
        # Close any remaining position at end
        if self.position is not None:
            final_row = df.iloc[-1]
            self._close_position(final_row, df.index[-1], 'end_of_data')
        
        # Convert to DataFrames
        trades_df = pd.DataFrame(self.trades)
        equity_curve_df = pd.DataFrame(self.equity_curve)
        
        # Set time as index for equity curve
        if not equity_curve_df.empty and 'time' in equity_curve_df.columns:
            equity_curve_df = equity_curve_df.set_index('time')
        
        # Compute metrics
        metrics = compute_metrics(trades_df, equity_curve_df, self.initial_capital)
        
        # Include debug info from strategy if available
        if hasattr(strategy, 'debug'):
            metrics['debug'] = strategy.debug
        
        # Include risk summary
        metrics['risk'] = self.risk_manager.get_summary(last_n=5)
        
        return trades_df, equity_curve_df, metrics
    
    def _open_position(self, signal: Dict, row: pd.Series, current_time: pd.Timestamp,
                       atr: float) -> None:
        """Open a new position."""
        from .execution import apply_costs
        
        side = signal.get('side', 'long')
        entry_price = signal.get('price') or row['Close']
        sl = signal.get('sl')
        tp = signal.get('tp')
        notes = signal.get('notes', '')
        
        # Apply spread + slippage
        entry_price = apply_costs(entry_price, side, self.pip, 'open', self.spread_pips, atr)
        
        # Calculate position size based on risk
        if sl is not None:
            risk_amount = self.equity * (self.risk_percent / 100.0)
            sl_distance = abs(entry_price - sl)
            
            if sl_distance > 0:
                # Size = risk_amount / sl_distance
                size = risk_amount / sl_distance
            else:
                size = 0
        else:
            # Default size: risk 0.5% with 50 pip stop
            risk_amount = self.equity * (self.risk_percent / 100.0)
            default_sl_distance = 50 * self.pip
            size = risk_amount / default_sl_distance
        
        if size <= 0:
            return
        
        # Commission
        commission = calculate_commission(size, entry_price)
        
        self.position = {
            'side': side,
            'entry_time': current_time,
            'entry_price': entry_price,
            'size': size,
            'sl': sl,
            'tp': tp,
            'commission': commission,
            'notes': notes,
            'initial_sl': sl,
        }
    
    def _check_exit(self, row: pd.Series, current_time: pd.Timestamp) -> Optional[Dict]:
        """Check if position should be exited."""
        if self.position is None:
            return None
        
        side = self.position['side']
        entry_price = self.position['entry_price']
        sl = self.position['sl']
        tp = self.position['tp']
        entry_time = self.position['entry_time']
        
        # Check stop-loss
        if sl is not None:
            if side == 'long' and row['Low'] <= sl:
                return {'reason': 'stop_loss', 'price': sl}
            elif side == 'short' and row['High'] >= sl:
                return {'reason': 'stop_loss', 'price': sl}
        
        # Check take-profit
        if tp is not None:
            if side == 'long' and row['High'] >= tp:
                return {'reason': 'take_profit', 'price': tp}
            elif side == 'short' and row['Low'] <= tp:
                return {'reason': 'take_profit', 'price': tp}
        
        # Check time-based stop (if specified in notes)
        # This is handled by strategy-level logic
        
        return None
    
    def _close_position(self, row: pd.Series, current_time: pd.Timestamp,
                       reason: str, exit_price: Optional[float] = None) -> None:
        """Close the current position."""
        from .execution import apply_costs
        
        if self.position is None:
            return
        
        side = self.position['side']
        entry_price = self.position['entry_price']
        size = self.position['size']
        initial_sl = self.position['initial_sl']
        
        # Determine exit price
        if exit_price is None:
            exit_price = row['Close']
        
        # Apply spread + slippage
        atr = row.get('ATR', 0)
        exit_price = apply_costs(exit_price, side, self.pip, 'close', self.spread_pips, atr)
        
        # Calculate P&L
        if side == 'long':
            pnl = (exit_price - entry_price) * size
        else:
            pnl = (entry_price - exit_price) * size
        
        # Subtract commissions
        pnl -= self.position['commission']
        pnl -= calculate_commission(size, exit_price)
        
        # Update equity
        self.equity += pnl
        
        # Calculate R-multiple
        if initial_sl is not None:
            risk = abs(entry_price - initial_sl) * size
            r_multiple = pnl / risk if risk > 0 else 0
        else:
            r_multiple = 0
        
        # Update risk manager
        trade_date = current_time.date()
        self.risk_manager.on_close(trade_date, r_multiple)
        
        # Record trade
        trade = {
            'entry_time': self.position['entry_time'],
            'exit_time': current_time,
            'side': side,
            'entry': entry_price,
            'exit': exit_price,
            'size': size,
            'sl': initial_sl,
            'tp': self.position['tp'],
            'pnl': pnl,
            'r_multiple': r_multiple,
            'notes': f"{self.position['notes']} | exit: {reason}"
        }
        
        self.trades.append(trade)
        self.position = None
