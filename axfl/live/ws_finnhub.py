"""
Finnhub WebSocket client for real-time FX streaming.

Connects to Finnhub's WebSocket API to stream forex ticks from OANDA venue.
Implements automatic key rotation on rate limits and reconnection logic.

Environment Variables:
    FINNHUB_API_KEYS: Comma-separated list of Finnhub API keys for rotation
"""

import os
import json
import time
import threading
from datetime import datetime
from typing import List, Optional, Dict, Any, Generator, Tuple
import websocket


class FinnhubWSUnavailable(Exception):
    """Raised when WebSocket connection fails after all retries."""
    pass


class FinnhubWebSocket:
    """
    Finnhub WebSocket client for real-time forex streaming.
    
    Connects to Finnhub's WebSocket API and streams forex ticks for specified symbols.
    Implements automatic reconnection, key rotation on rate limits, and heartbeat monitoring.
    """
    
    WS_URL = "wss://ws.finnhub.io"
    
    def __init__(self, venue: str = "OANDA", symbols: List[str] = None, 
                 api_keys: List[str] = None):
        """
        Initialize Finnhub WebSocket client.
        
        Args:
            venue: Forex venue (default: OANDA)
            symbols: List of AXFL symbols (EURUSD, GBPUSD, XAUUSD)
            api_keys: List of Finnhub API keys for rotation
        """
        self.venue = venue
        self.symbols = symbols or ['EURUSD', 'GBPUSD', 'XAUUSD']
        
        # Get API keys from parameter or environment
        if api_keys:
            self.api_keys = api_keys
        else:
            keys_env = os.getenv('FINNHUB_API_KEYS', '')
            self.api_keys = [k.strip() for k in keys_env.split(',') if k.strip()]
        
        if not self.api_keys:
            raise ValueError("No Finnhub API keys provided")
        
        self.key_index = 0
        self.ws = None
        self.connected = False
        self.errors = 0
        self.last_error = None
        
        # Tick buffer (thread-safe)
        self.tick_buffer = []
        self.buffer_lock = threading.Lock()
        
        # Connection management
        self.max_retries = len(self.api_keys) * 3
        self.retry_count = 0
        self.should_reconnect = True
        
        # Heartbeat tracking
        self.last_heartbeat = time.time()
        self.heartbeat_timeout = 30  # seconds
    
    def _get_current_key(self) -> str:
        """Get current API key."""
        return self.api_keys[self.key_index]
    
    def _rotate_key(self) -> None:
        """Rotate to next API key."""
        self.key_index = (self.key_index + 1) % len(self.api_keys)
        print(f"[WS] Rotated to key index {self.key_index}")
    
    def _format_symbol(self, symbol: str) -> str:
        """
        Convert AXFL symbol to Finnhub WebSocket format.
        
        Args:
            symbol: AXFL symbol (EURUSD, GBPUSD, XAUUSD)
            
        Returns:
            Finnhub symbol (OANDA:EUR_USD, OANDA:GBP_USD, OANDA:XAU_USD)
        """
        mapping = {
            'EURUSD': f'{self.venue}:EUR_USD',
            'GBPUSD': f'{self.venue}:GBP_USD',
            'XAUUSD': f'{self.venue}:XAU_USD'
        }
        return mapping.get(symbol, f'{self.venue}:{symbol}')
    
    def _unformat_symbol(self, finnhub_symbol: str) -> str:
        """
        Convert Finnhub symbol back to AXFL format.
        
        Args:
            finnhub_symbol: Finnhub symbol (OANDA:EUR_USD)
            
        Returns:
            AXFL symbol (EURUSD)
        """
        # Remove venue prefix
        if ':' in finnhub_symbol:
            _, pair = finnhub_symbol.split(':', 1)
        else:
            pair = finnhub_symbol
        
        # Remove underscores
        return pair.replace('_', '')
    
    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)
            
            # Handle different message types
            if data.get('type') == 'ping':
                self.last_heartbeat = time.time()
                return
            
            if data.get('type') == 'trade':
                # Forex tick format: {'type':'trade','data':[{'s':'OANDA:EUR_USD','p':1.0850,'t':1234567890,'v':1}]}
                for tick in data.get('data', []):
                    symbol = self._unformat_symbol(tick.get('s', ''))
                    price = tick.get('p')  # Last trade price (use as mid)
                    timestamp = tick.get('t', 0) / 1000  # Convert ms to seconds
                    
                    if symbol and price:
                        # For forex, approximate bid/ask with small spread
                        spread = 0.0001 if symbol in ['EURUSD', 'GBPUSD'] else 0.1
                        bid = price - spread / 2
                        ask = price + spread / 2
                        
                        ts_utc = datetime.utcfromtimestamp(timestamp)
                        
                        with self.buffer_lock:
                            self.tick_buffer.append({
                                'symbol': symbol,
                                'timestamp': ts_utc,
                                'bid': bid,
                                'ask': ask
                            })
                        
        except Exception as e:
            self.errors += 1
            self.last_error = f"Message parse error: {str(e)}"
            print(f"[WS] Error parsing message: {e}")
    
    def _on_error(self, ws, error):
        """Handle WebSocket errors."""
        self.errors += 1
        self.last_error = str(error)
        print(f"[WS] Error: {error}")
        
        # Check for rate limit errors
        if '429' in str(error) or '403' in str(error):
            print(f"[WS] Rate limit hit, rotating key...")
            self._rotate_key()
    
    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close."""
        self.connected = False
        print(f"[WS] Connection closed: {close_status_code} - {close_msg}")
        
        if self.should_reconnect and self.retry_count < self.max_retries:
            self.retry_count += 1
            wait_time = min(2 ** self.retry_count, 60)
            print(f"[WS] Reconnecting in {wait_time}s (attempt {self.retry_count}/{self.max_retries})...")
            time.sleep(wait_time)
            self.connect()
    
    def _on_open(self, ws):
        """Handle WebSocket open - subscribe to symbols."""
        self.connected = True
        self.retry_count = 0
        self.last_heartbeat = time.time()
        print(f"[WS] Connected using key index {self.key_index}")
        
        # Subscribe to all symbols
        for symbol in self.symbols:
            finnhub_symbol = self._format_symbol(symbol)
            subscribe_msg = {'type': 'subscribe', 'symbol': finnhub_symbol}
            ws.send(json.dumps(subscribe_msg))
            print(f"[WS] Subscribed to {finnhub_symbol}")
    
    def connect(self) -> None:
        """
        Connect to Finnhub WebSocket.
        
        Raises:
            FinnhubWSUnavailable: If connection fails after all retries
        """
        if self.retry_count >= self.max_retries:
            raise FinnhubWSUnavailable(f"Failed to connect after {self.max_retries} attempts")
        
        api_key = self._get_current_key()
        ws_url = f"{self.WS_URL}?token={api_key}"
        
        try:
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open
            )
            
            # Run in separate thread
            wst = threading.Thread(target=self.ws.run_forever, daemon=True)
            wst.start()
            
            # Wait for connection
            timeout = 10
            start = time.time()
            while not self.connected and time.time() - start < timeout:
                time.sleep(0.1)
            
            if not self.connected:
                raise Exception("Connection timeout")
            
        except Exception as e:
            self.errors += 1
            self.last_error = str(e)
            print(f"[WS] Connection failed: {e}")
            
            # Try rotating key
            if self.retry_count < self.max_retries:
                self._rotate_key()
            raise
    
    def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        self.should_reconnect = False
        if self.ws:
            self.ws.close()
        self.connected = False
    
    def next_tick(self) -> Generator[Tuple[str, datetime, float, float], None, None]:
        """
        Generator yielding ticks from buffer.
        
        Yields:
            Tuple of (symbol, timestamp, bid, ask)
        """
        while True:
            # Check heartbeat
            if time.time() - self.last_heartbeat > self.heartbeat_timeout:
                print(f"[WS] Heartbeat timeout, reconnecting...")
                self.connected = False
                self.connect()
            
            # Yield buffered ticks
            with self.buffer_lock:
                while self.tick_buffer:
                    tick = self.tick_buffer.pop(0)
                    yield (tick['symbol'], tick['timestamp'], tick['bid'], tick['ask'])
            
            # Small sleep to avoid busy-waiting
            time.sleep(0.01)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket connection stats."""
        return {
            'connected': self.connected,
            'errors': self.errors,
            'key_index': self.key_index,
            'last_error': self.last_error,
            'buffer_size': len(self.tick_buffer)
        }
