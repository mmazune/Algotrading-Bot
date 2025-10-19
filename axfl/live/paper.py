"""
Live paper trading engine with websocket and replay modes.
"""
import pandas as pd
import numpy as np
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path

from .aggregator import CascadeAggregator
from ..data.provider import DataProvider
from ..data.symbols import normalize, pip_size
from ..core.execution import apply_costs
from ..core.risk import RiskManager, RiskRules
from ..config.defaults import resolve_params


class LivePaperEngine:
    """
    Live paper trading engine with websocket and replay modes.
    """
    
    def __init__(self, strategy_class, symbol: str, interval: str = '5m',
                 source: str = 'finnhub', venue: str = 'OANDA',
                 spread_pips: float = 0.6, warmup_days: int = 3,
                 mode: str = 'ws', status_every_s: int = 300,
                 base_params: Optional[Dict] = None):
        """
        Initialize live paper trading engine.
        
        Args:
            strategy_class: Strategy class to instantiate
            symbol: Trading symbol
            interval: Timeframe (currently only '5m' supported)
            source: Data source ('finnhub', 'twelvedata', 'auto')
            venue: Venue for websocket (e.g., 'OANDA')
            spread_pips: Bid-ask spread in pips
            warmup_days: Days of historical data for warmup
            mode: 'ws' for websocket, 'replay' for historical replay
            status_every_s: Seconds between status updates
            base_params: User parameters (will be merged with defaults)
        """
        self.symbol = symbol
        self.interval = interval
        self.source = source
        self.venue = venue
        self.spread_pips = spread_pips
        self.warmup_days = warmup_days
        self.mode = mode
        self.status_every_s = status_every_s
        
        self.pip = pip_size(symbol)
        self.strategy_class = strategy_class
        
        # Resolve parameters with tuned defaults
        self.params = resolve_params(base_params, strategy_class.name.lower(), symbol, interval)
        
        # State
        self.df = None  # Working 5m DataFrame
        self.strategy = None
        self.strategy_state = {}
        self.position = None
        self.trades = []
        self.equity = 100000.0
        self.risk_manager = RiskManager(RiskRules())
        
        # Live tracking
        self.normalized_symbol = None
        self.actual_source = None
        self.first_bar_time = None
        self.last_bar_time = None
        self.last_tick_time = None
        self.ws_connected = False
        self.ws_errors = 0
        
        # Aggregator
        self.aggregator = CascadeAggregator()
        
        # Persistence
        self.trades_dir = Path('data/trades')
        self.logs_dir = Path('logs')
        self.trades_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def warmup(self):
        """Load historical data and initialize strategy."""
        print(f"\n=== Warmup Phase ===")
        print(f"Loading {self.warmup_days} days of 1m data...")
        
        # Load historical 1m data
        provider = DataProvider(source=self.source, venue=self.venue, rotate=True)
        
        try:
            df_1m = provider.get_intraday(self.symbol, interval='1m', days=self.warmup_days)
            self.normalized_symbol = provider.last_symbol_used
            self.actual_source = provider.last_source_used
            print(f"Loaded {len(df_1m)} bars from {self.actual_source}")
        except Exception as e:
            print(f"Warmup failed: {e}")
            raise
        
        # Resample to 5m
        df_5m = df_1m.resample('5min').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum',
        }).dropna()
        
        print(f"Resampled to {len(df_5m)} 5m bars")
        print(f"Date range: {df_5m.index[0]} to {df_5m.index[-1]}")
        
        # Initialize strategy
        self.strategy = self.strategy_class(self.symbol, self.params)
        self.df = self.strategy.prepare(df_5m)
        
        self.first_bar_time = self.df.index[0]
        self.last_bar_time = self.df.index[-1]
        
        print(f"Strategy initialized: {self.strategy.name}")
        print(f"Parameters: {self.params}")
        print("Warmup complete\n")
    
    def _open_position(self, signal: Dict, bar: pd.Series, current_time: pd.Timestamp):
        """Open a new position."""
        if self.position is not None:
            return  # Already in position
        
        # Check risk limits
        date = current_time.date()
        if not self.risk_manager.can_open(date):
            if 'risk_blocked_entries' in self.strategy.debug:
                self.strategy.debug['risk_blocked_entries'] += 1
            return
        
        side = signal.get('side', 'long')
        entry_price = signal.get('price', bar['Close'])
        sl = signal.get('sl')
        tp = signal.get('tp')
        notes = signal.get('notes', '')
        
        # Apply spread + slippage
        atr = bar.get('ATR', 0)
        entry_price = apply_costs(entry_price, side, self.pip, 'open', self.spread_pips, atr)
        
        # Calculate position size
        if sl is not None:
            risk_amount = self.equity * 0.005  # 0.5%
            sl_distance = abs(entry_price - sl)
            size = risk_amount / sl_distance if sl_distance > 0 else 0
        else:
            size = 0
        
        if size <= 0:
            return
        
        self.position = {
            'side': side,
            'entry_time': current_time,
            'entry_price': entry_price,
            'sl': sl,
            'tp': tp,
            'initial_sl': sl,
            'size': size,
            'notes': notes,
        }
        
        print(f"[{current_time}] OPEN {side.upper()} @ {entry_price:.5f}, SL={sl:.5f}, TP={tp:.5f}")
    
    def _close_position(self, bar: pd.Series, current_time: pd.Timestamp, reason: str, 
                       exit_price: Optional[float] = None):
        """Close the current position."""
        if self.position is None:
            return
        
        side = self.position['side']
        entry_price = self.position['entry_price']
        size = self.position['size']
        initial_sl = self.position['initial_sl']
        
        if exit_price is None:
            exit_price = bar['Close']
        
        # Apply spread + slippage
        atr = bar.get('ATR', 0)
        exit_price = apply_costs(exit_price, side, self.pip, 'close', self.spread_pips, atr)
        
        # Calculate P&L
        if side == 'long':
            pnl = (exit_price - entry_price) * size
        else:
            pnl = (entry_price - exit_price) * size
        
        self.equity += pnl
        
        # Calculate R-multiple
        if initial_sl is not None:
            risk = abs(entry_price - initial_sl) * size
            r_multiple = pnl / risk if risk > 0 else 0
        else:
            r_multiple = 0
        
        # Record trade
        trade = {
            'entry_time': self.position['entry_time'],
            'exit_time': current_time,
            'side': side,
            'entry': entry_price,
            'exit': exit_price,
            'pnl': pnl,
            'r_multiple': r_multiple,
            'reason': reason,
            'notes': self.position['notes'],
        }
        self.trades.append(trade)
        
        # Update risk manager
        self.risk_manager.on_close(current_time.date(), r_multiple)
        
        print(f"[{current_time}] CLOSE {side.upper()} @ {exit_price:.5f}, "
              f"PnL=${pnl:.2f}, R={r_multiple:.2f}, Reason={reason}")
        
        self.position = None
    
    def _process_bar(self, bar_dict: Dict):
        """Process a completed 5m bar."""
        # Convert to Series
        bar_time = bar_dict['time']
        bar = pd.Series({
            'Open': bar_dict['Open'],
            'High': bar_dict['High'],
            'Low': bar_dict['Low'],
            'Close': bar_dict['Close'],
            'Volume': bar_dict['Volume'],
        }, name=bar_time)
        
        # Append to working DataFrame
        new_row = pd.DataFrame([bar]).set_index(pd.DatetimeIndex([bar_time]))
        self.df = pd.concat([self.df, new_row])
        
        # Re-prepare (update indicators)
        self.df = self.strategy.prepare(self.df)
        
        self.last_bar_time = bar_time
        
        # Check position management
        if self.position is not None:
            side = self.position['side']
            sl = self.position['sl']
            tp = self.position['tp']
            
            # Check SL
            if side == 'long' and bar['Low'] <= sl:
                self._close_position(bar, bar_time, 'SL', sl)
                return
            elif side == 'short' and bar['High'] >= sl:
                self._close_position(bar, bar_time, 'SL', sl)
                return
            
            # Check TP
            if tp is not None:
                if side == 'long' and bar['High'] >= tp:
                    self._close_position(bar, bar_time, 'TP', tp)
                    return
                elif side == 'short' and bar['Low'] <= tp:
                    self._close_position(bar, bar_time, 'TP', tp)
                    return
        
        # Generate signals
        i = len(self.df) - 1
        row = self.df.iloc[i]
        
        signals = self.strategy.generate_signals(i, row, self.strategy_state)
        
        for signal in signals:
            if signal['action'] == 'open':
                self._open_position(signal, bar, bar_time)
    
    def _get_today_stats(self) -> Dict:
        """Get today's trading statistics."""
        if not self.trades:
            return {'trades': 0, 'cum_r': 0.0, 'pnl': 0.0}
        
        today = datetime.now().date()
        today_trades = [t for t in self.trades if t['exit_time'].date() == today]
        
        if not today_trades:
            return {'trades': 0, 'cum_r': 0.0, 'pnl': 0.0}
        
        cum_r = sum([t['r_multiple'] for t in today_trades])
        pnl = sum([t['pnl'] for t in today_trades])
        
        return {'trades': len(today_trades), 'cum_r': round(cum_r, 2), 'pnl': round(pnl, 2)}
    
    def _print_status(self):
        """Print AXFL LIVE status block."""
        now = datetime.now(tz=pd.Timestamp.now(tz='UTC').tz)
        
        # Get today's risk state
        risk_state = self.risk_manager.get_summary()
        today_date = now.date()
        risk_today = risk_state.get(today_date, {'trades': 0, 'cum_r': 0.0, 'halted': False})
        
        # Build status dict
        status = {
            'ok': True,
            'mode': self.mode,
            'strategy': self.strategy.name.lower(),
            'symbol': self.symbol,
            'normalized_symbol': self.normalized_symbol or self.symbol,
            'source': self.actual_source or self.source,
            'interval': self.interval,
            'since': str(self.first_bar_time) if self.first_bar_time else None,
            'now': str(self.last_bar_time) if self.last_bar_time else None,
            'today': self._get_today_stats(),
            'open_position': None,
            'debug': self.strategy.debug if hasattr(self.strategy, 'debug') else {},
            'risk': {
                'date': str(today_date),
                'trades': risk_today['trades'],
                'cum_r': risk_today['cum_r'],
                'halted': risk_today['halted'],
            },
            'costs': {
                'spread_pips': self.spread_pips,
                'slippage_model': 'max(1 pip, ATR/1000)',
            },
            'heartbeat_s': 0,
            'ws': {
                'connected': self.ws_connected,
                'errors': self.ws_errors,
            },
        }
        
        # Add open position if exists
        if self.position is not None:
            status['open_position'] = {
                'side': self.position['side'],
                'entry': round(self.position['entry_price'], 5),
                'sl': round(self.position['sl'], 5) if self.position['sl'] else None,
                'tp': round(self.position['tp'], 5) if self.position['tp'] else None,
                'duration_s': int((now - self.position['entry_time']).total_seconds()),
            }
        
        # Calculate heartbeat
        if self.last_tick_time:
            status['heartbeat_s'] = int((now - self.last_tick_time).total_seconds())
        
        # Print JSON block
        status_json = json.dumps(status, separators=(',', ':'))
        print("\n###BEGIN-AXFL-LIVE###")
        print(status_json)
        print("###END-AXFL-LIVE###\n")
        
        # Also log to file
        log_file = self.logs_dir / f"live_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, 'a') as f:
            f.write(status_json + '\n')
    
    def run_replay(self):
        """Run in replay mode (5x speed on historical data)."""
        print(f"\n=== Replay Mode (5x speed) ===")
        
        # Get recent historical 1m data (last 1 day beyond warmup for faster demo)
        provider = DataProvider(source='auto', rotate=True)
        
        try:
            df_replay = provider.get_intraday(self.symbol, interval='1m', days=1)
            print(f"Loaded {len(df_replay)} 1m bars for replay")
            print(f"Replay period: {df_replay.index[0]} to {df_replay.index[-1]}\n")
        except Exception as e:
            print(f"Failed to load replay data: {e}")
            return
        
        self.actual_source = provider.last_source_used
        
        last_status_time = time.time()
        
        for idx, (ts, row) in enumerate(df_replay.iterrows()):
            # Emit synthetic tick
            self.last_tick_time = ts
            
            bars_5m = self.aggregator.push_tick(ts, last=row['Close'])
            
            for bar_5m in bars_5m:
                self._process_bar(bar_5m)
            
            # Status updates
            if time.time() - last_status_time >= self.status_every_s:
                self._print_status()
                last_status_time = time.time()
            
            # 5x speed: sleep 2ms per 1m bar (faster for demo)
            time.sleep(0.002)
        
        # Final status
        self._print_status()
        print(f"\nReplay complete. Total trades: {len(self.trades)}")
    
    def run(self):
        """Main entry point."""
        try:
            self.warmup()
            
            if self.mode == 'ws':
                print("WebSocket mode not fully implemented - falling back to replay")
                self.mode = 'replay'
                self.run_replay()
            else:
                self.run_replay()
                
        except KeyboardInterrupt:
            print("\n\nShutdown requested...")
            self._print_status()
            print(f"Total trades: {len(self.trades)}")
            
            # Save trades
            if self.trades:
                trades_df = pd.DataFrame(self.trades)
                filename = f"live_{self.strategy.name.lower()}_{self.symbol}_{datetime.now().strftime('%Y%m%d')}.csv"
                trades_df.to_csv(self.trades_dir / filename, index=False)
                print(f"Trades saved to {self.trades_dir / filename}")
