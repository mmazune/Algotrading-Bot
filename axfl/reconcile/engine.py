"""
AXFL Reconciliation Engine - compare broker vs journal, resolve drift, safe flatten.

Recovery flow:
1. on_start(): Compare broker open positions vs journal open positions
2. If mismatches and flatten_on_conflict=True: close orphaned broker positions
3. link_pending(): Attempt to link unmapped AXFL trades to broker orders by client_tag
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from ..journal import store as journal
from ..brokers.oanda import OandaPractice


class ReconcileEngine:
    """
    Reconciliation engine for broker vs journal sync.
    
    Ensures broker positions match journal, handles drift, and provides safe recovery.
    """
    
    def __init__(
        self,
        broker: OandaPractice,
        safety: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize reconciliation engine.
        
        Args:
            broker: Broker adapter (OandaPractice)
            safety: Safety config with 'flatten_on_conflict', 'max_retries'
        """
        self.broker = broker
        self.safety = safety or {
            'flatten_on_conflict': True,
            'max_retries': 3
        }
        
        self.flatten_on_conflict = self.safety.get('flatten_on_conflict', True)
        self.max_retries = self.safety.get('max_retries', 3)
        
        # Stats
        self.flattened = 0
        self.linked = 0
        self.errors = []
    
    def on_start(self) -> Dict[str, Any]:
        """
        Reconcile on startup: compare broker vs journal, flatten conflicts.
        
        Returns:
            Summary dict with 'broker_positions', 'journal_positions', 'flattened', 'errors'
        """
        journal.log_event('INFO', 'reconcile_start', {})
        
        # Get broker open positions
        broker_positions = self.broker.get_open_positions()
        
        # Get journal open positions
        journal_data = journal.open_positions()
        journal_broker_orders = journal_data['broker_orders']
        journal_axfl_trades = journal_data['axfl_trades']
        mappings = journal_data['mappings']
        
        # Build sets for comparison
        broker_instruments = {pos['instrument'] for pos in broker_positions}
        journal_order_ids = {order['order_id'] for order in journal_broker_orders}
        
        # Find orphaned broker positions (not in journal)
        orphaned = []
        for pos in broker_positions:
            # Check if this position has a corresponding journal entry
            # (simplified: check by instrument, could enhance with order_id matching)
            is_orphaned = True
            for order in journal_broker_orders:
                if self.broker.instrument(order['symbol']) == pos['instrument']:
                    is_orphaned = False
                    break
            
            if is_orphaned:
                orphaned.append(pos)
        
        # Flatten orphaned positions if enabled
        flattened_count = 0
        if self.flatten_on_conflict and orphaned:
            for pos in orphaned:
                instrument = pos['instrument']
                # Convert instrument back to symbol
                symbol_map = {
                    'EUR_USD': 'EURUSD',
                    'GBP_USD': 'GBPUSD',
                    'XAU_USD': 'XAUUSD'
                }
                symbol = symbol_map.get(instrument, instrument)
                
                journal.log_event('WARN', 'flatten_orphan', {
                    'instrument': instrument,
                    'units': pos['units'],
                    'reason': 'not_in_journal'
                })
                
                result = self.broker.close_all(symbol)
                if result['success']:
                    flattened_count += 1
                    journal.log_event('INFO', 'flattened', {'symbol': symbol})
                else:
                    self.errors.append({
                        'action': 'flatten',
                        'symbol': symbol,
                        'error': result['error']
                    })
                    journal.log_event('ERROR', 'flatten_failed', {
                        'symbol': symbol,
                        'error': result['error']
                    })
        
        self.flattened = flattened_count
        
        summary = {
            'broker_positions': len(broker_positions),
            'journal_positions': len(journal_broker_orders),
            'flattened': flattened_count,
            'orphaned': len(orphaned),
            'errors': self.errors
        }
        
        journal.log_event('INFO', 'reconcile_complete', summary)
        
        return summary
    
    def link_pending(self, axfl_trades_recent: Optional[List[Dict[str, Any]]] = None) -> int:
        """
        Link pending AXFL trades to broker orders.
        
        Attempts to find broker orders by:
        1. Client tag match (AXFL::strategy::symbol::ts::uuid)
        2. Time/price proximity (fallback)
        
        Args:
            axfl_trades_recent: Recent AXFL trades to link (if None, uses journal.pending_mappings())
        
        Returns:
            Number of trades linked
        """
        if axfl_trades_recent is None:
            axfl_trades_recent = journal.pending_mappings()
        
        if not axfl_trades_recent:
            return 0
        
        # Get recent broker trades (last 24h)
        since_ts = (datetime.utcnow() - timedelta(hours=24)).isoformat() + 'Z'
        broker_trades = self.broker.get_trades_since(since_ts)
        
        linked_count = 0
        
        for axfl_trade in axfl_trades_recent:
            axfl_id = axfl_trade['axfl_id']
            symbol = axfl_trade['symbol']
            
            # Try to find matching broker trade
            matched_broker_trade = None
            
            # Strategy 1: Match by client tag (if available in extra)
            extra = axfl_trade.get('extra', {})
            if isinstance(extra, str):
                import json
                try:
                    extra = json.loads(extra)
                except:
                    extra = {}
            
            client_tag = extra.get('client_tag')
            if client_tag:
                for bt in broker_trades:
                    if bt.get('client_tag') == client_tag:
                        matched_broker_trade = bt
                        break
            
            # Strategy 2: Match by instrument + time proximity (within 5 minutes)
            if not matched_broker_trade:
                axfl_time = datetime.fromisoformat(axfl_trade['opened_at'].replace('Z', ''))
                instrument = self.broker.instrument(symbol)
                
                for bt in broker_trades:
                    if bt['instrument'] == instrument:
                        bt_time = datetime.fromisoformat(bt['time'].replace('Z', ''))
                        time_diff = abs((axfl_time - bt_time).total_seconds())
                        if time_diff < 300:  # 5 minutes
                            matched_broker_trade = bt
                            break
            
            # Link if found
            if matched_broker_trade:
                journal.link(axfl_id, matched_broker_trade['id'])
                linked_count += 1
                journal.log_event('INFO', 'linked', {
                    'axfl_id': axfl_id,
                    'order_id': matched_broker_trade['id'],
                    'symbol': symbol
                })
        
        self.linked = linked_count
        return linked_count
    
    def reconcile(self) -> Dict[str, Any]:
        """
        Full reconciliation: on_start + link_pending.
        
        Returns:
            Summary dict
        """
        start_summary = self.on_start()
        linked = self.link_pending()
        
        return {
            'ok': len(self.errors) == 0,
            'broker_positions': start_summary['broker_positions'],
            'journal_positions': start_summary['journal_positions'],
            'flattened': start_summary['flattened'],
            'linked': linked,
            'errors': self.errors
        }
