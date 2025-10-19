"""Portfolio engine for multi-strategy, multi-symbol live trading."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd

from ..data.provider import DataProvider
from ..live.aggregator import CascadeAggregator
from ..live.paper import LivePaperEngine
from ..core.risk import RiskManager, RiskRules
from ..strategies.arls import ARLSStrategy
from ..strategies.orb import ORBStrategy
from ..strategies.lsg import LSGStrategy
from ..strategies.choch_ob import CHOCHOBStrategy
from ..strategies.breaker import BreakerStrategy
from ..config.defaults import resolve_params
from .scheduler import now_in_any_window, SessionWindow


STRATEGY_MAP = {
    'arls': ARLSStrategy,
    'orb': ORBStrategy,
    'lsg': LSGStrategy,
    'choch_ob': CHOCHOBStrategy,
    'breaker': BreakerStrategy,
}


class PortfolioEngine:
    """
    Multi-strategy, multi-symbol portfolio live trading engine.
    
    - Runs multiple strategies across one or more symbols
    - Session-aware: only trades during configured UTC windows
    - Portfolio-level risk: global daily R stop, per-strategy limits
    - Unified AXFL LIVE PORT JSON status blocks
    """
    
    def __init__(self, schedule_cfg: Dict[str, Any], mode: str = 'replay'):
        self.cfg = schedule_cfg
        self.mode = mode
        
        # Portfolio config
        self.symbols = schedule_cfg['symbols']
        self.interval = schedule_cfg['interval']
        self.source = schedule_cfg['source']
        self.venue = schedule_cfg['venue']
        
        # Per-symbol spreads (if provided) or fallback to single spread_pips
        self.spreads = schedule_cfg.get('spreads', {})
        self.spread_pips = schedule_cfg.get('spread_pips', 0.6)  # Default fallback
        
        self.warmup_days = schedule_cfg['warmup_days']
        self.status_every_s = schedule_cfg['status_every_s']
        
        # Risk config
        risk_cfg = schedule_cfg['risk']
        self.global_daily_stop_r = risk_cfg.get('global_daily_stop_r', -5.0)
        self.max_open_positions = risk_cfg.get('max_open_positions', 1)
        self.per_strategy_daily_trades = risk_cfg.get('per_strategy_daily_trades', 3)
        self.per_strategy_daily_stop_r = risk_cfg.get('per_strategy_daily_stop_r', -2.0)
        
        # Strategies config
        self.strategies_cfg = schedule_cfg['strategies']
        
        # State
        self.engines: Dict[tuple, LivePaperEngine] = {}  # (symbol, strategy_name) -> engine
        self.aggregators: Dict[str, CascadeAggregator] = {}  # symbol -> aggregator
        self.halted = False
        self.ws_connected = False
        self.ws_errors = 0
        self.actual_source = None
        
        # Timestamps
        self.first_bar_time = None
        self.last_bar_time = None
        self.last_tick_time = None
        
        # Persistence
        self.logs_dir = Path('logs')
        self.logs_dir.mkdir(exist_ok=True)
        
        print("=== AXFL Portfolio Live Trading ===")
        print(f"Symbols: {', '.join(self.symbols)}")
        print(f"Strategies: {', '.join([s['name'] for s in self.strategies_cfg])}")
        print(f"Interval: {self.interval}")
        print(f"Source: {self.source}")
        print(f"Venue: {self.venue}")
        print(f"Mode: {self.mode}")
        if self.spreads:
            print(f"Spreads: {self.spreads}")
        else:
            print(f"Spread: {self.spread_pips} pips")
        print(f"Status every: {self.status_every_s}s")
        print(f"Global daily stop: {self.global_daily_stop_r}R")
        print()
        
    def _initialize_engines(self):
        """Initialize all (symbol, strategy) engines with warmup data."""
        print("=== Portfolio Warmup Phase ===")
        
        # Shared data provider to avoid duplicate downloads
        provider = DataProvider(source=self.source, rotate=True)
        
        # Load warmup data per symbol
        warmup_data = {}
        for symbol in self.symbols:
            print(f"Loading {self.warmup_days} days of 1m data for {symbol}...")
            df_1m = provider.get_intraday(symbol, interval='1m', days=self.warmup_days)
            
            if df_1m is None or df_1m.empty:
                raise ValueError(f"Failed to load warmup data for {symbol}")
            
            # Resample to target interval
            df_5m = df_1m.resample('5min').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum',
            }).dropna()
            
            warmup_data[symbol] = df_5m
            print(f"  ✓ {symbol}: {len(df_1m)} bars 1m → {len(df_5m)} bars 5m")
            
            self.actual_source = provider.last_source_used
            
            # Track timestamps
            if self.first_bar_time is None:
                self.first_bar_time = df_5m.index[0]
            self.last_bar_time = df_5m.index[-1]
        
        print()
        
        # Create engines for each (symbol, strategy) pair
        for symbol in self.symbols:
            for strat_cfg in self.strategies_cfg:
                strategy_name = strat_cfg['name']
                strategy_class = STRATEGY_MAP.get(strategy_name)
                
                if strategy_class is None:
                    raise ValueError(f"Unknown strategy: {strategy_name}")
                
                # Resolve params (tuned defaults + user overrides)
                user_params = strat_cfg['params']
                params = resolve_params(user_params, strategy_name, symbol, self.interval)
                
                # Create strategy instance
                strategy = strategy_class(symbol, params)
                
                # Create risk manager with per-strategy limits
                risk_rules = RiskRules(
                    max_trades_per_day=self.per_strategy_daily_trades,
                    daily_loss_stop_r=self.per_strategy_daily_stop_r,
                )
                risk_manager = RiskManager(rules=risk_rules)
                
                # Get symbol-specific spread or fallback
                symbol_spread = self.spreads.get(symbol, self.spread_pips)
                
                # Create engine (reuse LivePaperEngine internals)
                engine = LivePaperEngine(
                    strategy_class=strategy_class,
                    symbol=symbol,
                    interval=self.interval,
                    source=self.source,
                    venue=self.venue,
                    spread_pips=symbol_spread,
                    warmup_days=0,  # We already loaded data
                    mode=self.mode,
                    status_every_s=self.status_every_s,
                    base_params=params,
                )
                
                # Override with shared warmup data
                engine.df = warmup_data[symbol].copy()
                engine.df = strategy.prepare(engine.df)
                engine.strategy = strategy
                engine.risk_manager = risk_manager
                engine.first_bar_time = self.first_bar_time
                engine.last_bar_time = self.last_bar_time
                engine.actual_source = self.actual_source
                
                # Track metadata for this engine
                engine.strategy_name = strategy_name
                engine.windows = strat_cfg['windows']
                engine.live_overrides = bool(user_params)  # Has LIVE param overrides
                engine.symbol_spread = symbol_spread
                
                # Store
                key = (symbol, strategy_name)
                self.engines[key] = engine
                
                print(f"Initialized: {symbol} / {strategy_name}")
                print(f"  Windows: {strat_cfg['windows']}")
                print(f"  Params: {params}")
        
        print(f"\nPortfolio warmup complete: {len(self.engines)} engines ready")
        print(f"Date range: {self.first_bar_time} to {self.last_bar_time}")
        print()
        
    def _process_bar(self, symbol: str, bar_dict: Dict):
        """Process a completed 5m bar for a symbol across all its strategies."""
        bar_time = bar_dict['time']
        self.last_bar_time = bar_time
        self.last_tick_time = bar_time
        
        # Get current UTC time for window checks (ensure UTC timezone)
        if bar_time.tz is None:
            ts_utc = pd.Timestamp(bar_time, tz='UTC')
        else:
            ts_utc = bar_time.tz_convert('UTC') if bar_time.tz != 'UTC' else bar_time
        
        # Count open positions for this symbol
        open_positions = sum(
            1 for (sym, _), engine in self.engines.items()
            if sym == symbol and engine.position is not None
        )
        
        # Process each strategy for this symbol
        for strat_cfg in self.strategies_cfg:
            strategy_name = strat_cfg['name']
            windows = strat_cfg['windows']
            key = (symbol, strategy_name)
            engine = self.engines.get(key)
            
            if engine is None:
                continue
            
            # Update engine's DataFrame with new bar
            bar = pd.Series({
                'Open': bar_dict['Open'],
                'High': bar_dict['High'],
                'Low': bar_dict['Low'],
                'Close': bar_dict['Close'],
                'Volume': bar_dict.get('Volume', 0),
            }, name=bar_time)
            
            new_row = pd.DataFrame([bar]).set_index(pd.DatetimeIndex([bar_time]))
            engine.df = pd.concat([engine.df, new_row])
            
            # Only re-prepare for LSG (stateless indicator updates)
            # ORB/ARLS have session-based prepare() that can't be called incrementally
            if strategy_name == 'lsg':
                engine.df = engine.strategy.prepare(engine.df)
            
            engine.last_bar_time = bar_time
            
            # Check if we're in a valid session window
            in_window = now_in_any_window(ts_utc, windows)
            
            # Handle existing position
            if engine.position is not None:
                # Check SL/TP
                pos = engine.position
                side = pos['side']
                sl = pos['sl']
                tp = pos['tp']
                
                if side == 'long':
                    if bar_dict['Low'] <= sl:
                        engine._close_position(bar, bar_time, 'SL', sl)
                    elif bar_dict['High'] >= tp:
                        engine._close_position(bar, bar_time, 'TP', tp)
                else:  # short
                    if bar_dict['High'] >= sl:
                        engine._close_position(bar, bar_time, 'SL', sl)
                    elif bar_dict['Low'] <= tp:
                        engine._close_position(bar, bar_time, 'TP', tp)
                
                # If outside window, close position (time stop)
                if not in_window and engine.position is not None:
                    print(f"[{bar_time}] {symbol}/{strategy_name}: Outside window, closing position (time stop)")
                    engine._close_position(bar, bar_time, 'TIME', engine.position['entry'])
                
                continue  # Don't generate new signals if in position
            
            # Check if we can open new positions
            today = bar_time.date()
            can_trade = (
                in_window and
                not self.halted and
                engine.risk_manager.can_open(today) and
                open_positions < self.max_open_positions
            )
            
            if not can_trade:
                continue
            
            # Generate signals
            i = len(engine.df) - 1
            row = engine.df.iloc[i]
            signals = engine.strategy.generate_signals(i, row, engine.strategy_state)
            
            for signal in signals:
                if signal['action'] == 'open' and engine.position is None:
                    engine._open_position(signal, bar, bar_time)
                    open_positions += 1
                    break  # One position per bar
    
    def _check_global_risk(self):
        """Check portfolio-level risk limits."""
        if self.halted:
            return
        
        # Sum today's R across all engines
        today = datetime.now().date()
        total_r = sum(
            engine.risk_manager._get_state(today).cum_r
            for engine in self.engines.values()
        )
        
        # Check global daily stop
        if total_r <= self.global_daily_stop_r:
            self.halted = True
            print(f"\n⚠️  PORTFOLIO HALTED: Global daily stop hit ({total_r:.2f}R <= {self.global_daily_stop_r}R)")
    
    def _get_portfolio_stats(self) -> Dict[str, Any]:
        """Get aggregated portfolio statistics."""
        total_r = 0.0
        total_pnl = 0.0
        
        # Initialize all strategies from config
        by_strategy = {}
        for strat_cfg in self.strategies_cfg:
            by_strategy[strat_cfg['name']] = {'r': 0.0, 'trades': 0, 'pnl': 0.0}
        
        today = datetime.now().date()
        
        for (symbol, strategy_name), engine in self.engines.items():
            state = engine.risk_manager._get_state(today)
            r = state.cum_r
            pnl = sum(t['pnl'] for t in engine.trades)
            trades = len(engine.trades)
            
            total_r += r
            total_pnl += pnl
            
            by_strategy[strategy_name]['r'] += r
            by_strategy[strategy_name]['trades'] += trades
            by_strategy[strategy_name]['pnl'] += pnl
        
        by_strategy_list = [
            {'name': name, 'r': round(stats['r'], 2), 'trades': stats['trades'], 'pnl': round(stats['pnl'], 2)}
            for name, stats in by_strategy.items()
        ]
        
        return {
            'r_total': round(total_r, 2),
            'pnl_total': round(total_pnl, 2),
            'by_strategy': by_strategy_list,
        }
    
    def _get_open_positions(self) -> List[Dict[str, Any]]:
        """Get list of all open positions."""
        positions = []
        
        for (symbol, strategy_name), engine in self.engines.items():
            if engine.position is not None:
                pos = engine.position
                positions.append({
                    'symbol': symbol,
                    'strategy': strategy_name,
                    'side': pos['side'],
                    'entry': round(pos['entry'], 5),
                    'sl': round(pos['sl'], 5),
                    'tp': round(pos['tp'], 5),
                    'r': round(pos.get('r', 0.0), 2),
                })
        
        return positions
    
    def _get_engines_roster(self) -> List[Dict[str, Any]]:
        """Get roster of all engines with metadata."""
        roster = []
        
        for (symbol, strategy_name), engine in self.engines.items():
            windows_str = [f"{w.start_h:02d}:{w.start_m:02d}-{w.end_h:02d}:{w.end_m:02d}" 
                          for w in engine.windows]
            roster.append({
                'symbol': symbol,
                'strategy': strategy_name,
                'windows': windows_str,
                'active': True,  # Could check if in window
                'spread_pips': engine.symbol_spread,
                'live_overrides': engine.live_overrides,
            })
        
        return roster
    
    def _print_status(self):
        """Print unified AXFL LIVE PORT status block."""
        now = datetime.now(tz=pd.Timestamp.now(tz='UTC').tz)
        
        status = {
            'ok': True,
            'mode': self.mode,
            'source': self.actual_source or self.source,
            'interval': self.interval,
            'since': str(self.first_bar_time),
            'now': str(self.last_bar_time),
            'symbols': self.symbols,
            'engines': self._get_engines_roster(),
            'positions': self._get_open_positions(),
            'today': self._get_portfolio_stats(),
            'risk': {
                'halted': self.halted,
                'global_daily_stop_r': self.global_daily_stop_r,
            },
            'costs': {
                'spreads': self.spreads if self.spreads else {'default': self.spread_pips},
                'slippage_model': 'max(1 pip, ATR/1000)',
            },
            'ws': {
                'connected': self.ws_connected,
                'errors': self.ws_errors,
            },
        }
        
        # Print single-line JSON block
        status_json = json.dumps(status, separators=(',', ':'))
        print("\n###BEGIN-AXFL-LIVE-PORT###")
        print(status_json)
        print("###END-AXFL-LIVE-PORT###\n")
        
        # Log to file
        log_file = self.logs_dir / f"portfolio_live_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, 'a') as f:
            f.write(status_json + '\n')
    
    def run_replay(self):
        """Run in replay mode (historical 1m data → 5m aggregation)."""
        print(f"=== Replay Mode ===")
        
        # Load 1 day of 1m data for replay
        provider = DataProvider(source=self.source, rotate=True)
        
        replay_data = {}
        for symbol in self.symbols:
            df_replay = provider.get_intraday(symbol, interval='1m', days=1)
            
            if df_replay is None or df_replay.empty:
                print(f"⚠️  No replay data for {symbol}, skipping")
                continue
            
            replay_data[symbol] = df_replay
            print(f"Loaded {len(df_replay)} 1m bars for {symbol}")
            print(f"Replay period: {df_replay.index[0]} to {df_replay.index[-1]}")
            
            # Create aggregator for this symbol
            self.aggregators[symbol] = CascadeAggregator()
        
        print()
        
        last_status_time = time.time()
        
        # Replay all symbols in chronological order
        # Merge all dataframes by timestamp
        all_ticks = []
        for symbol, df in replay_data.items():
            for ts, row in df.iterrows():
                all_ticks.append((ts, symbol, row))
        
        all_ticks.sort(key=lambda x: x[0])
        
        # Process ticks
        for ts, symbol, row in all_ticks:
            self.last_tick_time = ts
            
            # Push to aggregator
            aggregator = self.aggregators.get(symbol)
            if aggregator is None:
                continue
            
            bars_5m = aggregator.push_tick(ts, last=row['Close'])
            
            # Process completed 5m bars
            for bar_5m in bars_5m:
                self._process_bar(symbol, bar_5m)
                self._check_global_risk()
            
            # Status updates
            if time.time() - last_status_time >= self.status_every_s:
                self._print_status()
                last_status_time = time.time()
            
            # Fast replay speed
            time.sleep(0.002)
        
        # Final status
        self._print_status()
        
        print(f"\nReplay complete. Portfolio stats:")
        stats = self._get_portfolio_stats()
        print(f"  Total R: {stats['r_total']}")
        print(f"  Total PnL: ${stats['pnl_total']}")
        for s in stats['by_strategy']:
            print(f"    {s['name']}: {s['r']}R, {s['trades']} trades")
    
    def run(self):
        """Main entry point."""
        self._initialize_engines()
        
        if self.mode == 'replay':
            self.run_replay()
        elif self.mode == 'ws':
            print("⚠️  Websocket mode not yet implemented, falling back to replay")
            self.mode = 'replay'
            self.run_replay()
        else:
            raise ValueError(f"Unknown mode: {self.mode}")
