"""
OANDA Practice broker adapter for mirroring AXFL trades.

This adapter provides best-effort mirroring of AXFL paper trades to OANDA Practice.
AXFL remains the source of truth for PnL - broker mirroring failures are logged but
do not affect AXFL position tracking.

Environment Variables:
    OANDA_API_KEY: Practice API token
    OANDA_ACCOUNT_ID: Practice account ID
    OANDA_ENV: Environment (practice/live, default: practice)
"""

import os
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import requests
from pathlib import Path


class OandaPractice:
    """
    OANDA Practice broker adapter for trade mirroring.
    
    Implements netting mode with one position per instrument.
    All methods are defensive - failures are logged but not raised.
    """
    
    BASE_URLS = {
        'practice': 'https://api-fxpractice.oanda.com',
        'live': 'https://api-fxtrade.oanda.com'
    }
    
    def __init__(self, api_key: Optional[str] = None, 
                 account_id: Optional[str] = None,
                 env: str = 'practice'):
        """
        Initialize OANDA Practice adapter.
        
        Args:
            api_key: OANDA API token (defaults to OANDA_API_KEY env var)
            account_id: OANDA account ID (defaults to OANDA_ACCOUNT_ID env var)
            env: Environment ('practice' or 'live', default: 'practice')
        """
        self.api_key = api_key or os.getenv('OANDA_API_KEY')
        self.account_id = account_id or os.getenv('OANDA_ACCOUNT_ID')
        self.env = env or os.getenv('OANDA_ENV', 'practice')
        
        if not self.api_key or not self.account_id:
            raise ValueError("OANDA_API_KEY and OANDA_ACCOUNT_ID must be set")
        
        self.base_url = self.BASE_URLS.get(self.env, self.BASE_URLS['practice'])
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        # Stats tracking
        self.connected = False
        self.errors = 0
        self.last_error = None
        
        # Setup logging
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        date_str = datetime.now().strftime('%Y%m%d')
        self.log_path = log_dir / f'broker_oanda_{date_str}.jsonl'
        
        self._test_connection()
    
    def _test_connection(self) -> bool:
        """Test connection to OANDA API."""
        try:
            response = requests.get(
                f'{self.base_url}/v3/accounts/{self.account_id}',
                headers=self.headers,
                timeout=10
            )
            self.connected = response.status_code == 200
            if not self.connected:
                self.errors += 1
                self.last_error = f"Connection test failed: {response.status_code}"
                self._log_event('connection_test_failed', {'status': response.status_code})
            else:
                self._log_event('connection_test_success', {})
            return self.connected
        except Exception as e:
            self.connected = False
            self.errors += 1
            self.last_error = str(e)
            self._log_event('connection_test_error', {'error': str(e)})
            return False
    
    def _log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log broker event to JSONL file."""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'event': event_type,
            'data': data
        }
        try:
            with open(self.log_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception:
            pass  # Silent fail on logging
    
    def instrument(self, symbol: str) -> str:
        """
        Convert AXFL symbol to OANDA instrument name.
        
        Args:
            symbol: AXFL symbol (EURUSD, GBPUSD, XAUUSD)
            
        Returns:
            OANDA instrument (EUR_USD, GBP_USD, XAU_USD)
        """
        mapping = {
            'EURUSD': 'EUR_USD',
            'GBPUSD': 'GBP_USD',
            'XAUUSD': 'XAU_USD'
        }
        return mapping.get(symbol, symbol)
    
    def calc_units(self, symbol: str, entry: float, sl: float, 
                   risk_amount_usd: float) -> int:
        """
        Calculate position size in units for given risk.
        
        Position sizing formula:
        - EURUSD/GBPUSD: ~$10 per pip per 100k units (0.0001 move)
        - XAUUSD: ~$1 per $0.1 move per 100 units
        
        Args:
            symbol: Trading symbol
            entry: Entry price
            sl: Stop loss price
            risk_amount_usd: Risk amount in USD
            
        Returns:
            Position size in units (positive integer)
        """
        risk_pips = abs(entry - sl)
        
        if symbol in ['EURUSD', 'GBPUSD']:
            # FX majors: $10 per pip per 100k units
            pip_value_per_100k = 10.0
            pips = risk_pips / 0.0001
            units = (risk_amount_usd / pips) / pip_value_per_100k * 100000
        elif symbol == 'XAUUSD':
            # Gold: $1 per $0.1 move per 100 units
            dollar_value_per_100_units = 1.0
            dollar_moves = risk_pips / 0.1
            units = (risk_amount_usd / dollar_moves) / dollar_value_per_100_units * 100
        else:
            # Fallback: simple proportional
            units = int(risk_amount_usd / risk_pips)
        
        return max(1, int(units))
    
    def place_market(self, symbol: str, side: str, units: int,
                     sl: Optional[float] = None, tp: Optional[float] = None,
                     client_tag: Optional[str] = None) -> Dict[str, Any]:
        """
        Place market order with optional SL/TP. Idempotent via client_tag.
        
        Args:
            symbol: Trading symbol
            side: 'long' or 'short'
            units: Position size (always positive)
            sl: Stop loss price
            tp: Take profit price
            client_tag: Client order tag (AXFL::strategy::symbol::ts::uuid)
            
        Returns:
            Dict with 'success', 'order_id', 'error' keys
        """
        instrument_name = self.instrument(symbol)
        signed_units = units if side == 'long' else -units
        
        # Generate client tag if not provided
        if not client_tag:
            ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            client_tag = f"AXFL::manual::{symbol}::{ts}::{uuid.uuid4().hex[:8]}"
        
        # Check for existing order with same client tag (idempotency)
        existing = self._find_order_by_client_tag(client_tag)
        if existing:
            return {
                'success': True,
                'order_id': existing['order_id'],
                'error': None,
                'idempotent': True
            }
        
        order_spec = {
            'order': {
                'type': 'MARKET',
                'instrument': instrument_name,
                'units': str(signed_units),
                'timeInForce': 'FOK',
                'positionFill': 'DEFAULT',
                'clientExtensions': {'tag': client_tag}
            }
        }
        
        # Attach SL/TP if provided
        if sl is not None:
            order_spec['order']['stopLossOnFill'] = {'price': str(sl)}
        if tp is not None:
            order_spec['order']['takeProfitOnFill'] = {'price': str(tp)}
        
        result = {'success': False, 'order_id': None, 'error': None, 'idempotent': False}
        
        try:
            response = requests.post(
                f'{self.base_url}/v3/accounts/{self.account_id}/orders',
                headers=self.headers,
                json=order_spec,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                if 'orderFillTransaction' in data:
                    result['success'] = True
                    result['order_id'] = data['orderFillTransaction'].get('id')
                    self._log_event('order_placed', {
                        'symbol': symbol,
                        'side': side,
                        'units': units,
                        'order_id': result['order_id'],
                        'client_tag': client_tag
                    })
                elif 'orderCreateTransaction' in data:
                    result['success'] = True
                    result['order_id'] = data['orderCreateTransaction'].get('id')
                    self._log_event('order_placed', {
                        'symbol': symbol,
                        'side': side,
                        'units': units,
                        'order_id': result['order_id'],
                        'client_tag': client_tag
                    })
                else:
                    result['error'] = 'Order placed but no transaction ID'
                    self.errors += 1
            else:
                result['error'] = f"HTTP {response.status_code}: {response.text}"
                self.errors += 1
                self._log_event('order_failed', {
                    'symbol': symbol,
                    'status': response.status_code,
                    'error': response.text
                })
                
        except Exception as e:
            result['error'] = str(e)
            self.errors += 1
            self.last_error = str(e)
            self._log_event('order_error', {'symbol': symbol, 'error': str(e)})
        
        return result
    
    def close_all(self, symbol: str) -> Dict[str, Any]:
        """
        Close all positions for symbol (netting mode).
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dict with 'success', 'error' keys
        """
        instrument_name = self.instrument(symbol)
        result = {'success': False, 'error': None}
        
        try:
            response = requests.put(
                f'{self.base_url}/v3/accounts/{self.account_id}/positions/{instrument_name}/close',
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                result['success'] = True
                self._log_event('position_closed', {'symbol': symbol})
            else:
                result['error'] = f"HTTP {response.status_code}: {response.text}"
                self.errors += 1
                self._log_event('close_failed', {
                    'symbol': symbol,
                    'status': response.status_code,
                    'error': response.text
                })
                
        except Exception as e:
            result['error'] = str(e)
            self.errors += 1
            self.last_error = str(e)
            self._log_event('close_error', {'symbol': symbol, 'error': str(e)})
        
        return result
    
    def fetch_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch current position for symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dict with 'size', 'avg_price', 'unrealized' or None if no position
        """
        instrument_name = self.instrument(symbol)
        
        try:
            response = requests.get(
                f'{self.base_url}/v3/accounts/{self.account_id}/positions/{instrument_name}',
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                position = data.get('position', {})
                
                long_units = float(position.get('long', {}).get('units', 0))
                short_units = float(position.get('short', {}).get('units', 0))
                net_units = long_units + short_units
                
                if net_units == 0:
                    return None
                
                avg_price = float(position.get('long' if long_units else 'short', {}).get('averagePrice', 0))
                unrealized = float(position.get('unrealizedPL', 0))
                
                return {
                    'size': net_units,
                    'avg_price': avg_price,
                    'unrealized': unrealized
                }
            
        except Exception as e:
            self.errors += 1
            self.last_error = str(e)
            self._log_event('fetch_position_error', {'symbol': symbol, 'error': str(e)})
        
        return None
    
    def _find_order_by_client_tag(self, client_tag: str) -> Optional[Dict[str, Any]]:
        """
        Find order by client tag (for idempotency).
        
        Args:
            client_tag: Client order tag
            
        Returns:
            Dict with order_id or None
        """
        try:
            # Get recent transactions (last 24h)
            since = (datetime.utcnow() - timedelta(hours=24)).isoformat() + 'Z'
            response = requests.get(
                f'{self.base_url}/v3/accounts/{self.account_id}/transactions',
                headers=self.headers,
                params={'from': since},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                for txn in data.get('transactions', []):
                    if txn.get('type') == 'MARKET_ORDER' and \
                       txn.get('clientExtensions', {}).get('tag') == client_tag:
                        return {'order_id': txn.get('id')}
        except Exception as e:
            self._log_event('find_order_error', {'client_tag': client_tag, 'error': str(e)})
        
        return None
    
    def get_open_positions(self) -> List[Dict[str, Any]]:
        """
        Get all open positions.
        
        Returns:
            List of position dicts with 'instrument', 'units', 'avg_price', 'unrealized'
        """
        result = []
        try:
            response = requests.get(
                f'{self.base_url}/v3/accounts/{self.account_id}/openPositions',
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                for pos in data.get('positions', []):
                    instrument = pos.get('instrument', '')
                    long_units = float(pos.get('long', {}).get('units', 0))
                    short_units = float(pos.get('short', {}).get('units', 0))
                    net_units = long_units + short_units
                    
                    if net_units != 0:
                        avg_price = float(pos.get('long' if long_units else 'short', {}).get('averagePrice', 0))
                        unrealized = float(pos.get('unrealizedPL', 0))
                        result.append({
                            'instrument': instrument,
                            'units': net_units,
                            'avg_price': avg_price,
                            'unrealized': unrealized
                        })
        except Exception as e:
            self.errors += 1
            self.last_error = str(e)
            self._log_event('get_open_positions_error', {'error': str(e)})
        
        return result
    
    def get_trades_since(self, since_ts: str) -> List[Dict[str, Any]]:
        """
        Get trades since timestamp.
        
        Args:
            since_ts: ISO timestamp
            
        Returns:
            List of trade dicts
        """
        result = []
        try:
            response = requests.get(
                f'{self.base_url}/v3/accounts/{self.account_id}/transactions',
                headers=self.headers,
                params={'from': since_ts},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                for txn in data.get('transactions', []):
                    if txn.get('type') in ['ORDER_FILL', 'MARKET_ORDER']:
                        result.append({
                            'id': txn.get('id'),
                            'type': txn.get('type'),
                            'instrument': txn.get('instrument'),
                            'units': float(txn.get('units', 0)),
                            'price': float(txn.get('price', 0)),
                            'time': txn.get('time'),
                            'client_tag': txn.get('clientExtensions', {}).get('tag')
                        })
        except Exception as e:
            self.errors += 1
            self.last_error = str(e)
            self._log_event('get_trades_since_error', {'error': str(e)})
        
        return result
    
    def ping_auth(self) -> Dict[str, Any]:
        """
        Ping authentication (for reconciliation health checks).
        
        Returns:
            Dict with 'ok', 'error'
        """
        try:
            response = requests.get(
                f'{self.base_url}/v3/accounts/{self.account_id}',
                headers=self.headers,
                timeout=10
            )
            if response.status_code == 200:
                return {'ok': True, 'error': None}
            else:
                return {'ok': False, 'error': f"HTTP {response.status_code}"}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
    
    def get_account(self) -> Dict[str, Any]:
        """
        Get minimal account info to verify auth.
        
        Returns:
            Dict with 'ok', 'id', 'balance', 'currency', 'error' (never raises)
        """
        try:
            response = requests.get(
                f'{self.base_url}/v3/accounts/{self.account_id}',
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                account = data.get('account', {})
                return {
                    'ok': True,
                    'id': account.get('id', self.account_id),
                    'balance': float(account.get('balance', 0)),
                    'currency': account.get('currency', 'USD'),
                    'error': None
                }
            else:
                return {
                    'ok': False,
                    'id': None,
                    'balance': 0,
                    'currency': None,
                    'error': f"HTTP {response.status_code}: {response.text}"
                }
        except Exception as e:
            return {
                'ok': False,
                'id': None,
                'balance': 0,
                'currency': None,
                'error': str(e)
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get broker connection stats."""
        return {
            'connected': self.connected,
            'errors': self.errors,
            'last_error': self.last_error,
            'env': self.env
        }
