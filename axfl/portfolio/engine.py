from typing import TYPE_CHECKING
"""Portfolio engine for multi-strategy, multi-symbol live trading."""

import json
import time
import uuid
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
# (removed) eager import caused circular ref
from ..strategies.choch_ob import CHOCHOBStrategy
from ..strategies.breaker import BreakerStrategy
from ..config.defaults import resolve_params
from .scheduler import now_in_any_window, SessionWindow, check_send_performance_alerts
from ..monitor import alerts
from ..risk.allocator import compute_budgets
from ..risk.position_sizing import units_from_risk
from ..risk.vol import inv_vol_weights
from ..data.symbols import pip_size
from ..hooks import on_trade_opened, on_trade_closed

# Journal imports
try:
    from ..journal import store as journal
    HAS_JOURNAL = True
except ImportError:
    HAS_JOURNAL = False

# Reconciliation imports
try:
    from ..reconcile.engine import ReconcileEngine
    HAS_RECONCILE = True
except ImportError:
    HAS_RECONCILE = False

# Optional imports for live features
try:
    from ..live.ws_finnhub import FinnhubWebSocket, FinnhubWSUnavailable
    HAS_FINNHUB_WS = True
except ImportError:
    HAS_FINNHUB_WS = False

try:
    from ..brokers.oanda import OandaPractice
    HAS_OANDA = True
except ImportError:
    HAS_OANDA = False

try:
    from ..news.calendar import load_events_csv, upcoming_windows, is_in_event_window
    HAS_NEWS = True
except ImportError:
    HAS_NEWS = False


STRATEGY_MAP = {
    'arls': ARLSStrategy,
    'orb': ORBStrategy,
    'lsg': 'axfl.strategies.adapters.lsg:LSGStrategy',
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
    - Optional WebSocket streaming (Finnhub)
    - Optional broker mirroring (OANDA Practice)
    """
    
    def __init__(self, schedule_cfg: Dict[str, Any], mode: str = 'replay',
                 broker: Optional[Any] = None):
        self.cfg = schedule_cfg
        self.mode = mode
        self.broker = broker  # Optional OANDA broker for mirroring
        
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
        
        # Portfolio risk budgets
        strategy_names = [s['name'] for s in self.strategies_cfg]
        self.budgets = compute_budgets(
            symbols=self.symbols,
            strategies=strategy_names,
            spreads=self.spreads,
            equity_usd=100000.0,  # Starting equity
            daily_risk_fraction=0.02,  # 2% daily risk
            per_trade_fraction=0.005   # 0.5% per trade
        )
        self.equity_usd = self.budgets['equity_usd']
        self.daily_r_used_by_strategy = {s: 0.0 for s in strategy_names}  # Track daily R by strategy
        
        # News guard configuration
        news_guard_cfg = schedule_cfg.get('news_guard', {})
        self.news_guard_enabled = news_guard_cfg.get('enabled', False) and HAS_NEWS
        self.news_guard_csv_path = news_guard_cfg.get('csv_path', '')
        self.news_guard_pad_before_m = news_guard_cfg.get('pad_before_m', 30)
        self.news_guard_pad_after_m = news_guard_cfg.get('pad_after_m', 30)
        self.news_events_df = None
        self.news_blocked_entries = 0
        self.news_active_windows = []
        
        # Load news events if enabled
        if self.news_guard_enabled:
            try:
                self.news_events_df = load_events_csv(self.news_guard_csv_path)
                print(f"✓ News guard enabled: {len(self.news_events_df)} events loaded")
            except Exception as e:
                print(f"⚠️  News guard disabled: {e}")
                self.news_guard_enabled = False
        
        # Risk-parity allocation configuration
        risk_parity_cfg = schedule_cfg.get('risk_parity', {})
        self.risk_parity_enabled = risk_parity_cfg.get('enabled', False)
        self.risk_parity_lookback_d = risk_parity_cfg.get('lookback_d', 20)
        self.risk_parity_floor = risk_parity_cfg.get('floor', 0.15)
        self.risk_parity_cap = risk_parity_cfg.get('cap', 0.60)
        self.weights = {}  # Will be computed after warmup
        self.symbol_vols = {}  # Diagnostic volatilities
        
        # Drawdown lock configuration
        dd_lock_cfg = schedule_cfg.get('dd_lock', {})
        self.dd_lock_enabled = dd_lock_cfg.get('enabled', False)
        self.dd_lock_trailing_pct = dd_lock_cfg.get('trailing_pct', 5.0)
        self.dd_lock_cooloff_min = dd_lock_cfg.get('cooloff_min', 120)
        self.peak_equity = self.equity_usd  # Track peak for DD calculation
        self.dd_lock_active = False
        self.dd_lock_since = None  # Timestamp when DD lock triggered
        self.dd_lock_cooloff_until = None  # Timestamp when cooloff ends
        self.current_dd_pct = 0.0  # Current drawdown %
        
        # Journal tracking (for OANDA mirroring reconciliation)
        self.journal_enabled = HAS_JOURNAL and self.broker is not None
        self.mapped_trades = 0  # Count of trades successfully mapped to broker
        self.unmapped_trades = 0  # Count of trades pending mapping
        
        # State
        self.engines: Dict[tuple, LivePaperEngine] = {}  # (symbol, strategy_name) -> engine
        self.aggregators: Dict[str, CascadeAggregator] = {}  # symbol -> aggregator
        self.halted = False
        self.ws_connected = False
        self.ws_errors = 0
        self.ws_client = None  # FinnhubWebSocket instance
        self.actual_source = None
        self._first_ws_connect = True  # Track first WS connection for alert
        self._first_trade_today = True  # Track first trade of the day
        
        # Timestamps
        self.first_bar_time = None
        self.last_bar_time = None
        self.last_tick_time = None
        self._bar_processed = False  # Track if any bar has been processed
        
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
        print(f"Equity: ${self.equity_usd:,.0f}")
        print(f"Per-trade risk: ${self.budgets['per_trade_r']:,.0f} ({self.budgets['per_trade_fraction']*100:.1f}%)")
        if self.news_guard_enabled:
            print(f"News guard: Enabled ({len(self.news_events_df)} events)")
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
        
        # Compute risk-parity weights if enabled
        if self.risk_parity_enabled:
            print("\n=== Risk-Parity Allocation ===")
            try:
                pip_map = {sym: pip_size(sym) for sym in self.symbols}
                self.weights, self.symbol_vols = inv_vol_weights(
                    symbols=self.symbols,
                    data_map=warmup_data,
                    lookback_d=self.risk_parity_lookback_d,
                    pip_map=pip_map,
                    floor=self.risk_parity_floor,
                    cap=self.risk_parity_cap
                )
                
                print(f"Lookback: {self.risk_parity_lookback_d} days")
                print(f"Floor: {self.risk_parity_floor:.0%}, Cap: {self.risk_parity_cap:.0%}")
                print("\nSymbol Volatilities (pips):")
                for sym, vol in self.symbol_vols.items():
                    print(f"  {sym}: {vol:.2f}")
                print("\nRisk-Parity Weights:")
                for sym, w in self.weights.items():
                    print(f"  {sym}: {w:.2%}")
                print()
            except Exception as e:
                print(f"⚠️  Risk-parity computation failed: {e}")
                # Fallback to equal weights
                self.weights = {sym: 1.0 / len(self.symbols) for sym in self.symbols}
                self.symbol_vols = {sym: 0.0 for sym in self.symbols}
        else:
            # Equal weights if risk-parity disabled
            self.weights = {sym: 1.0 / len(self.symbols) for sym in self.symbols}
            self.symbol_vols = {sym: 0.0 for sym in self.symbols}
        
        print()
        
    def _process_bar(self, symbol: str, bar_dict: Dict):
        """Process a completed 5m bar for a symbol across all its strategies."""
        bar_time = bar_dict['time']
        
        # Track first bar
        if not self._bar_processed:
            self.first_bar_time = bar_time
            self._bar_processed = True
        
        self.last_bar_time = bar_time
        self.last_tick_time = bar_time
        
        # Get current UTC time for window checks (ensure UTC timezone)
        if bar_time.tz is None:
            ts_utc = pd.Timestamp(bar_time, tz='UTC')
        else:
            ts_utc = bar_time.tz_convert('UTC') if bar_time.tz != 'UTC' else bar_time
        
        # Check DD lock cooloff timer
        if self.dd_lock_active and self.dd_lock_cooloff_until:
            if ts_utc >= self.dd_lock_cooloff_until:
                # Cooloff period expired, check if we can resume
                # Re-compute current DD to see if we're still in trouble
                self.current_dd_pct = ((self.peak_equity - self.equity_usd) / self.peak_equity) * 100.0
                
                if self.current_dd_pct < self.dd_lock_trailing_pct:
                    # DD has recovered below threshold, resume trading
                    self.dd_lock_active = False
                    self.halted = False
                    self.dd_lock_since = None
                    self.dd_lock_cooloff_until = None
                    
                    print(f"\n✓ DD LOCK CLEARED")
                    print(f"  Current equity: ${self.equity_usd:,.2f}")
                    print(f"  Drawdown: {self.current_dd_pct:.2f}% (below {self.dd_lock_trailing_pct:.1f}% threshold)")
                    
                    alerts.send_event("DD_LOCK_CLEARED", {
                        "equity": self.equity_usd,
                        "dd_pct": self.current_dd_pct,
                        "threshold": self.dd_lock_trailing_pct
                    })
                else:
                    # Still above threshold, extend cooloff
                    self.dd_lock_cooloff_until = ts_utc + pd.Timedelta(minutes=self.dd_lock_cooloff_min)
                    print(f"\n⚠️  DD still elevated ({self.current_dd_pct:.2f}%), extending cooloff until {self.dd_lock_cooloff_until}")
        
        # Weekday gating: skip weekends (Sat=5, Sun=6)
        if ts_utc.weekday() >= 5:
            return  # Skip weekend trading
        
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
                        self._close_position_with_mirror(engine, bar, bar_time, 'SL', sl, symbol, strategy_name)
                    elif bar_dict['High'] >= tp:
                        self._close_position_with_mirror(engine, bar, bar_time, 'TP', tp, symbol, strategy_name)
                else:  # short
                    if bar_dict['High'] >= sl:
                        self._close_position_with_mirror(engine, bar, bar_time, 'SL', sl, symbol, strategy_name)
                    elif bar_dict['Low'] <= tp:
                        self._close_position_with_mirror(engine, bar, bar_time, 'TP', tp, symbol, strategy_name)
                
                # If outside window, close position (time stop)
                if not in_window and engine.position is not None:
                    print(f"[{bar_time}] {symbol}/{strategy_name}: Outside window, closing position (time stop)")
                    self._close_position_with_mirror(engine, bar, bar_time, 'TIME', engine.position['entry'], symbol, strategy_name)
                
                continue  # Don't generate new signals if in position
            
            # Update news guard windows
            if self.news_guard_enabled and self.news_events_df is not None:
                self.news_active_windows = upcoming_windows(
                    self.news_events_df,
                    ts_utc,
                    pad_before_m=self.news_guard_pad_before_m,
                    pad_after_m=self.news_guard_pad_after_m,
                    lookahea_hours=4
                )
            
            # Check if we can open new positions
            today = bar_time.date()
            
            # News guard: block new entries during high-impact events
            news_blocked = False
            if self.news_guard_enabled and self.news_active_windows:
                news_blocked = is_in_event_window(symbol, ts_utc, self.news_active_windows)
                if news_blocked:
                    self.news_blocked_entries += 1
            
            # Risk budget: check if strategy has exceeded daily budget
            budget_blocked = False
            daily_r_for_strategy = self.daily_r_used_by_strategy.get(strategy_name, 0.0)
            strategy_budget = self.budgets['per_strategy'].get(strategy_name, float('inf'))
            if abs(daily_r_for_strategy) >= abs(strategy_budget):
                budget_blocked = True
            
            can_trade = (
                in_window and
                not self.halted and
                not news_blocked and
                not budget_blocked and
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
                    self._open_position_with_mirror(engine, signal, bar, bar_time, symbol, strategy_name)
                    open_positions += 1
                    break  # One position per bar
    
    def _open_position_with_mirror(self, engine, signal, bar, bar_time, symbol, strategy_name):
        """Open position in AXFL and optionally mirror to broker."""
        # Open in AXFL (source of truth)
        engine._open_position(signal, bar, bar_time)
        
        # Generate unique AXFL trade ID
        axfl_id = f"{symbol}_{strategy_name}_{int(bar_time.timestamp())}_{uuid.uuid4().hex[:8]}"
        
        # Write AXFL trade to journal
        if self.journal_enabled and engine.position and HAS_JOURNAL:
            pos = engine.position
            ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            client_tag = f"AXFL::{strategy_name}::{symbol}::{ts}::{uuid.uuid4().hex[:8]}"
            
            # Compute entry price: try signal.entry, then entry_price, then fallback to bar close
            entry_px = signal.get('entry') or signal.get('price')
            if entry_px is None:
                entry_px = pos.get('entry_price') or pos.get('entry')
            if entry_px is None:
                try:
                    entry_px = float(bar['Close'])
                except Exception:
                    try:
                        entry_px = float(bar.Close)
                    except Exception:
                        # Last resort: use position entry_price which must exist
                        entry_px = float(pos['entry_price'])
            entry_px = float(entry_px)
            
            journal.upsert_axfl_trade(
                axfl_id=axfl_id,
                symbol=symbol,
                strategy=strategy_name,
                side=pos['side'],
                entry=entry_px,
                sl=pos['sl'],
                tp=pos.get('tp'),
                opened_at=bar_time.isoformat(),
                extra={'client_tag': client_tag}
            )
            
            # Store axfl_id and client_tag in position for later use
            pos['axfl_id'] = axfl_id
            pos['client_tag'] = client_tag
        
        # Send alert for first trade of the day
        if self._first_trade_today and engine.position:
            self._first_trade_today = False
            pos = engine.position
            alerts.send_event("TRADE_OPEN", {
                "symbol": symbol,
                "strategy": strategy_name,
                "side": pos['side'],
                "entry": pos['entry'],
                "sl": pos['sl'],
                "time": str(bar_time),
                "first_of_day": True
            })
        elif engine.position:
            # Send regular trade alert
            pos = engine.position
            alerts.send_event("TRADE_OPEN", {
                "symbol": symbol,
                "strategy": strategy_name,
                "side": pos['side'],
                "entry": pos['entry'],
                "sl": pos['sl'],
                "time": str(bar_time)
            })
        
        # Mirror to broker if configured
        if self.broker and engine.position:
            try:
                pos = engine.position
                side = pos['side']
                entry = pos['entry']
                sl = pos['sl']
                client_tag = pos.get('client_tag', f"{symbol}_{strategy_name}_{int(bar_time.timestamp())}")
                
                # Calculate position size using risk-based sizing
                # Scale per-trade risk by symbol weight (risk-parity allocation)
                symbol_weight = self.weights.get(symbol, 1.0 / len(self.symbols))
                scaled_risk_fraction = self.budgets['per_trade_fraction'] * symbol_weight
                
                units = units_from_risk(
                    symbol=symbol,
                    entry=entry,
                    sl=sl,
                    equity_usd=self.equity_usd,
                    risk_fraction=scaled_risk_fraction
                )
                
                # Place order with client tag (idempotent)
                result = self.broker.place_market(
                    symbol=symbol,
                    side=side,
                    units=units,
                    sl=sl,
                    tp=pos.get('tp'),
                    client_tag=client_tag
                )
                
                if result['success']:
                    pos['broker_order_id'] = result['order_id']
                    pos['units'] = units  # Store units for later use in close hook
                    print(f"  ✓ Broker mirror: {result['order_id']} ({units} units, weight={symbol_weight:.2%})")
                    
                    # Write broker order to journal and link
                    if self.journal_enabled and HAS_JOURNAL:
                        journal.upsert_broker_order(
                            order_id=result['order_id'],
                            client_tag=client_tag,
                            symbol=symbol,
                            side=side,
                            units=units,
                            entry=entry,
                            sl=sl,
                            tp=pos.get('tp'),
                            status='open',
                            opened_at=bar_time.isoformat()
                        )
                        journal.link(axfl_id, result['order_id'])
                        self.mapped_trades += 1
                    
                    # Call trade opened hook for Discord notification and SQLite persistence
                    try:
                        # Get spread if available
                        spread_pips = None
                        if symbol in self.spreads:
                            spread_pips = self.spreads[symbol]
                        elif hasattr(self, 'spread_pips'):
                            spread_pips = self.spread_pips
                        
                        opened_at_iso = on_trade_opened(
                            trade_id=result.get('trade_id') or result['order_id'],
                            order_id=result['order_id'],
                            instrument=symbol,
                            strategy=strategy_name,
                            side=side,
                            units=units,
                            entry=entry,
                            sl=sl,
                            tp=pos.get('tp'),
                            spread_pips=spread_pips,
                            reason="signal"
                        )
                        # Store opened_at_iso for later use in close
                        pos['opened_at_iso'] = opened_at_iso
                    except Exception as hook_err:
                        print(f"  ⚠️  Trade open hook error: {hook_err}")
                else:
                    print(f"  ⚠️  Broker mirror failed: {result['error']}")
                    if self.journal_enabled:
                        self.unmapped_trades += 1
                    
            except Exception as e:
                print(f"  ⚠️  Broker mirror error: {e}")
                if self.journal_enabled:
                    self.unmapped_trades += 1
    
    def _close_position_with_mirror(self, engine, bar, bar_time, reason, exit_price, symbol, strategy_name):
        """Close position in AXFL and optionally mirror to broker."""
        # Store broker order ID, axfl_id, and position data before closing
        broker_order_id = None
        axfl_id = None
        realized_r = 0.0
        # Store position data needed for close hook
        pos_side = None
        pos_units = None
        pos_entry = None
        pos_opened_at_iso = None
        if engine.position:
            broker_order_id = engine.position.get('broker_order_id')
            axfl_id = engine.position.get('axfl_id')
            pos_side = engine.position.get('side')
            pos_entry = engine.position.get('entry')
            pos_opened_at_iso = engine.position.get('opened_at_iso')
            # Try to get units from position if stored
            pos_units = engine.position.get('units')
        
        # Close in AXFL (source of truth)
        engine._close_position(bar, bar_time, reason, exit_price)
        
        # Update equity and budget tracking
        if engine.trades:
            last_trade = engine.trades[-1]
            realized_r = last_trade.get('r', 0.0)
            realized_pnl = last_trade.get('pnl', 0.0)
            
            # Update equity
            self.equity_usd += realized_pnl
            
            # Update peak equity for drawdown tracking
            if self.equity_usd > self.peak_equity:
                self.peak_equity = self.equity_usd
            
            # Update strategy daily R usage
            self.daily_r_used_by_strategy[strategy_name] += realized_r
            
            # Update journal with trade results
            if self.journal_enabled and axfl_id and HAS_JOURNAL:
                # Ensure entry is not None - it should always be present in last_trade
                entry_px = last_trade.get('entry')
                if entry_px is None:
                    # Fallback: this should not happen but be defensive
                    try:
                        entry_px = float(bar['Close'])
                    except Exception:
                        entry_px = float(bar.Close)
                entry_px = float(entry_px)
                
                journal.upsert_axfl_trade(
                    axfl_id=axfl_id,
                    symbol=symbol,
                    strategy=strategy_name,
                    side=last_trade.get('side', 'unknown'),
                    entry=entry_px,
                    sl=last_trade.get('sl'),
                    tp=last_trade.get('tp'),
                    r=realized_r,
                    pnl=realized_pnl,
                    opened_at=last_trade.get('entry_time', bar_time).isoformat(),
                    closed_at=bar_time.isoformat()
                )
                
                # Update broker order status if mapped
                if broker_order_id:
                    journal.upsert_broker_order(
                        order_id=broker_order_id,
                        client_tag=f"{symbol}_{strategy_name}",  # Simplified
                        symbol=symbol,
                        side=last_trade.get('side', 'unknown'),
                        units=0,  # Don't have units here, but required field
                        status='closed',
                        closed_at=bar_time.isoformat()
                    )
            
            # Check drawdown lock if enabled
            if self.dd_lock_enabled:
                self.current_dd_pct = ((self.peak_equity - self.equity_usd) / self.peak_equity) * 100.0
                
                # Trigger DD lock if threshold exceeded and not already locked
                if self.current_dd_pct >= self.dd_lock_trailing_pct and not self.dd_lock_active:
                    self.dd_lock_active = True
                    self.dd_lock_since = pd.Timestamp.now(tz='UTC')
                    self.dd_lock_cooloff_until = self.dd_lock_since + pd.Timedelta(minutes=self.dd_lock_cooloff_min)
                    self.halted = True
                    
                    print(f"\n⚠️  DRAWDOWN LOCK TRIGGERED")
                    print(f"  Peak equity: ${self.peak_equity:,.2f}")
                    print(f"  Current equity: ${self.equity_usd:,.2f}")
                    print(f"  Drawdown: {self.current_dd_pct:.2f}%")
                    print(f"  Cooloff until: {self.dd_lock_cooloff_until}")
                    
                    # Send alert
                    alerts.send_event("DD_LOCK", {
                        "peak_equity": self.peak_equity,
                        "current_equity": self.equity_usd,
                        "dd_pct": self.current_dd_pct,
                        "threshold": self.dd_lock_trailing_pct,
                        "cooloff_min": self.dd_lock_cooloff_min,
                        "cooloff_until": str(self.dd_lock_cooloff_until)
                    })
        
        # Send trade close alert (check last trade for result)
        if engine.trades:
            last_trade = engine.trades[-1]
            alerts.send_event("TRADE_CLOSE", {
                "symbol": symbol,
                "strategy": strategy_name,
                "side": last_trade.get('side', 'unknown'),
                "entry": last_trade.get('entry', 0),
                "exit": last_trade.get('exit', 0),
                "r": last_trade.get('r', 0),
                "pnl": last_trade.get('pnl', 0),
                "reason": reason,
                "time": str(bar_time)
            })
        
        # Mirror to broker if configured and we have an order ID
        if self.broker and broker_order_id:
            try:
                result = self.broker.close_all(symbol)
                if result['success']:
                    print(f"  ✓ Broker close: {symbol}")
                    
                    # Call trade closed hook for Discord notification and SQLite persistence
                    try:
                        # Get trade data from last_trade if available
                        if engine.trades:
                            last_trade = engine.trades[-1]
                            # Use stored position data or fallback to last_trade
                            side = pos_side or last_trade.get('side', 'unknown')
                            entry = pos_entry or last_trade.get('entry', 0.0)
                            # Units: try position, then estimate from last_trade or use 1000 as fallback
                            units = pos_units
                            if units is None:
                                # Try to estimate from PnL if available
                                units = 1000  # Default fallback
                            
                            # Get opened_at_iso from stored position or generate from entry_time
                            opened_at = pos_opened_at_iso
                            if not opened_at:
                                entry_time = last_trade.get('entry_time', bar_time)
                                if hasattr(entry_time, 'isoformat'):
                                    opened_at = entry_time.isoformat()
                                else:
                                    opened_at = str(entry_time)
                            
                            on_trade_closed(
                                trade_id=result.get('trade_id') or broker_order_id,
                                order_id=broker_order_id,
                                instrument=symbol,
                                strategy=strategy_name,
                                side=side,
                                units=units,
                                entry=entry,
                                exit_price=exit_price,
                                opened_at_iso=opened_at,
                                reason=reason
                            )
                    except Exception as hook_err:
                        print(f"  ⚠️  Trade close hook error: {hook_err}")
                else:
                    print(f"  ⚠️  Broker close failed: {result['error']}")
            except Exception as e:
                print(f"  ⚠️  Broker close error: {e}")

    
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
            
            # Send alert
            alerts.send_warn("DAILY_STOP_HIT", {
                "r_total": round(total_r, 2),
                "threshold": self.global_daily_stop_r,
                "time": str(datetime.now())
            })
    
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
        # Only print status if at least one bar has been processed
        if not self._bar_processed or self.first_bar_time is None:
            return
        
        now = datetime.now(tz=pd.Timestamp.now(tz='UTC').tz)
        
        # Broker stats
        broker_stats = {
            'mirror': 'oanda' if self.broker else 'none',
            'connected': False,
            'errors': 0
        }
        if self.broker:
            stats = self.broker.get_stats()
            broker_stats['connected'] = stats.get('connected', False)
            broker_stats['errors'] = stats.get('errors', 0)
        
        # WS stats
        ws_stats = {
            'connected': self.ws_connected,
            'errors': self.ws_errors,
        }
        if self.ws_client:
            client_stats = self.ws_client.get_stats()
            ws_stats['connected'] = client_stats.get('connected', False)
            ws_stats['errors'] = client_stats.get('errors', 0)
            ws_stats['key_index'] = client_stats.get('key_index', 0)
        
        # Ensure since <= now (handle replay edge cases)
        since_time = self.first_bar_time
        now_time = self.last_bar_time
        if since_time and now_time and since_time > now_time:
            since_time = now_time
        
        status = {
            'ok': True,
            'mode': self.mode,
            'source': self.actual_source or self.source,
            'interval': self.interval,
            'since': str(since_time),
            'now': str(now_time),
            'symbols': self.symbols,
            'engines': self._get_engines_roster(),
            'positions': self._get_open_positions(),
            'today': self._get_portfolio_stats(),
            'risk': {
                'halted': self.halted,
                'global_daily_stop_r': self.global_daily_stop_r,
            },
            'budgets': {
                'equity_usd': round(self.equity_usd, 2),
                'daily_r_total': round(self.budgets['daily_r_total'], 2),
                'per_strategy': {k: round(v, 2) for k, v in self.budgets['per_strategy'].items()},
                'per_trade_r': round(self.budgets['per_trade_r'], 2),
                'daily_r_used': {k: round(v, 2) for k, v in self.daily_r_used_by_strategy.items()}
            },
            'weights': {k: round(v, 4) for k, v in self.weights.items()} if self.weights else {},
            'volatilities_pips': {k: round(v, 2) for k, v in self.symbol_vols.items()} if self.symbol_vols else {},
            'news_guard': {
                'enabled': self.news_guard_enabled,
                'blocked_entries': self.news_blocked_entries,
                'active_windows': len(self.news_active_windows) if self.news_active_windows else 0
            },
            'dd_lock': {
                'enabled': self.dd_lock_enabled,
                'active': self.dd_lock_active,
                'dd_pct': round(self.current_dd_pct, 2) if hasattr(self, 'current_dd_pct') else 0.0,
                'peak_equity': round(self.peak_equity, 2),
                'threshold_pct': round(self.dd_lock_trailing_pct, 1) if self.dd_lock_enabled else 0.0,
                'cooloff_min': self.dd_lock_cooloff_min if self.dd_lock_enabled else 0,
                'since': str(self.dd_lock_since) if self.dd_lock_since else None,
                'cooloff_until': str(self.dd_lock_cooloff_until) if self.dd_lock_cooloff_until else None
            },
            'journal': {
                'enabled': self.journal_enabled,
                'mapped': self.mapped_trades,
                'unmapped': self.unmapped_trades
            },
            'costs': {
                'spreads': self.spreads if self.spreads else {'default': self.spread_pips},
                'slippage_model': 'max(1 pip, ATR/1000)',
            },
            'broker': broker_stats,
            'ws': ws_stats,
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
                # Check for scheduled performance alerts
                check_send_performance_alerts()
                last_status_time = time.time()
            
            # Fast replay speed
            time.sleep(0.002)
        
        # Final status
        self._print_status()
        
        # Send graceful shutdown alert
        alerts.send_info("ENGINE_STOP", {"reason": "replay_complete"})
        
        print(f"\nReplay complete. Portfolio stats:")
        stats = self._get_portfolio_stats()
        print(f"  Total R: {stats['r_total']}")
        print(f"  Total PnL: ${stats['pnl_total']}")
        for s in stats['by_strategy']:
            print(f"    {s['name']}: {s['r']}R, {s['trades']} trades")
    
    def run_ws(self):
        """Run in WebSocket mode (live Finnhub streaming → 5m aggregation)."""
        if not HAS_FINNHUB_WS:
            print("⚠️  Finnhub WebSocket not available, falling back to replay")
            return self.run_replay()
        
        print(f"=== WebSocket Mode (Finnhub) ===")
        
        # Initialize WebSocket client
        try:
            import os
            keys_env = os.getenv('FINNHUB_API_KEYS', '')
            api_keys = [k.strip() for k in keys_env.split(',') if k.strip()]
            
            if not api_keys:
                print("⚠️  FINNHUB_API_KEYS not set, falling back to replay")
                return self.run_replay()
            
            self.ws_client = FinnhubWebSocket(
                venue=self.venue,
                symbols=self.symbols,
                api_keys=api_keys
            )
            
            self.ws_client.connect()
            self.ws_connected = self.ws_client.connected
            print(f"✓ WebSocket connected")
            
            # Send first connection alert
            if self._first_ws_connect and self.ws_connected:
                self._first_ws_connect = False
                alerts.send_info("WS_CONNECTED", {
                    "source": "finnhub",
                    "symbols": self.symbols,
                    "time": str(datetime.now())
                })
            
        except FinnhubWSUnavailable as e:
            print(f"⚠️  WebSocket unavailable: {e}, falling back to replay")
            return self.run_replay()
        except Exception as e:
            print(f"⚠️  WebSocket init failed: {e}, falling back to replay")
            return self.run_replay()
        
        # Create aggregators for each symbol
        for symbol in self.symbols:
            self.aggregators[symbol] = CascadeAggregator()
        
        print(f"Streaming ticks for: {', '.join(self.symbols)}")
        print(f"Press Ctrl+C to stop\n")
        
        last_status_time = time.time()
        tick_count = 0
        
        try:
            # Stream ticks from WebSocket
            for symbol, timestamp, bid, ask in self.ws_client.next_tick():
                tick_count += 1
                self.last_tick_time = timestamp
                
                # Use mid price for now
                mid_price = (bid + ask) / 2
                
                # Push to aggregator
                aggregator = self.aggregators.get(symbol)
                if aggregator is None:
                    continue
                
                bars_5m = aggregator.push_tick(timestamp, last=mid_price)
                
                # Process completed 5m bars
                for bar_5m in bars_5m:
                    self._process_bar(symbol, bar_5m)
                    self._check_global_risk()
                
                # Status updates
                if time.time() - last_status_time >= self.status_every_s:
                    print(f"[WS] Ticks processed: {tick_count}")
                    self._print_status()
                    # Check for scheduled performance alerts
                    check_send_performance_alerts()
                    last_status_time = time.time()
                
                # Update WS stats
                if self.ws_client:
                    ws_stats = self.ws_client.get_stats()
                    self.ws_connected = ws_stats.get('connected', False)
                    self.ws_errors = ws_stats.get('errors', 0)
                
        except KeyboardInterrupt:
            print("\n⚠️  Interrupted by user")
            alerts.send_info("ENGINE_STOP", {"reason": "user_interrupt"})
        except Exception as e:
            print(f"\n⚠️  WebSocket error: {e}")
            self.ws_errors += 1
            alerts.send_error("ENGINE_ERROR", {"error": str(e)})
        finally:
            # Final status
            self._print_status()
            
            # Disconnect
            if self.ws_client:
                self.ws_client.disconnect()
            
            # Send graceful shutdown alert
            alerts.send_info("ENGINE_STOP", {"reason": "shutdown"})
            
            print(f"\nWebSocket session complete. Portfolio stats:")
            stats = self._get_portfolio_stats()
            print(f"  Total R: {stats['r_total']}")
            print(f"  Total PnL: ${stats['pnl_total']}")
            for s in stats['by_strategy']:
                print(f"    {s['name']}: {s['r']}R, {s['trades']} trades")
    
    def run(self):
        """Main entry point."""
        # Run reconciliation before starting if broker mirroring enabled
        if self.broker and HAS_RECONCILE and HAS_JOURNAL:
            print("=== Reconciliation on Startup ===")
            try:
                reconcile_engine = ReconcileEngine(self.broker)
                summary = reconcile_engine.on_start()
                print(f"✓ Reconciliation complete:")
                print(f"  Broker positions: {summary['broker_positions']}")
                print(f"  Journal positions: {summary['journal_positions']}")
                print(f"  Flattened: {summary['flattened']}")
                print(f"  Errors: {len(summary['errors'])}")
                if summary['errors']:
                    for err in summary['errors']:
                        print(f"    ⚠️  {err}")
                print()
            except Exception as e:
                print(f"⚠️  Reconciliation failed: {e}\n")
        
        self._initialize_engines()
        
        if self.mode == 'replay':
            self.run_replay()
        elif self.mode == 'ws':
            self.run_ws()
        else:
            raise ValueError(f"Unknown mode: {self.mode}")

if TYPE_CHECKING:
    from ..strategies.lsg import LSGStrategy  # type: ignore
