#!/usr/bin/env python3
"""
Enhanced Automated Financial Data Pipeline with API Key Rotation
This script fetches financial data using multiple API sources with automatic key rotation
for better rate limit management.
"""

import os
import sys
import time
import logging
import pandas as pd
import requests
from datetime import datetime, timedelta
from collections import deque, defaultdict
import threading

# Install and import technical analysis library
try:
    import ta
except ImportError:
    print("Installing technical analysis library...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "ta>=0.10.2"], check=True)
    import ta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class APIKeyRotator:
    """Handles automatic rotation of API keys for rate limit management"""
    
    def __init__(self, service_name, rate_limit_per_minute=60):
        self.service_name = service_name
        self.rate_limit = rate_limit_per_minute
        self.keys = deque()
        self.usage_count = defaultdict(int)
        self.reset_times = defaultdict(float)
        self.lock = threading.Lock()
        
        # Load keys from environment variables
        self._load_keys_from_env()
        
        if not self.keys:
            logger.error(f"No API keys found for {service_name}")
            raise ValueError(f"No API keys configured for {service_name}")
            
        logger.info(f"Initialized {service_name} rotator with {len(self.keys)} keys")
    
    def _load_keys_from_env(self):
        """Load API keys from environment variables"""
        # Try single key first (backward compatibility)
        single_key = os.getenv(f'{self.service_name.upper()}_API_KEY')
        if single_key:
            self.keys.append(('primary', single_key))
            logger.info(f"Loaded primary {self.service_name} key")
        
        # Load numbered keys (_1, _2, _3, etc.)
        key_index = 1
        while True:
            key = os.getenv(f'{self.service_name.upper()}_API_KEY_{key_index}')
            if not key:
                break
            self.keys.append((f'key_{key_index}', key))
            logger.info(f"Loaded {self.service_name} key #{key_index}")
            key_index += 1
    
    def get_key(self):
        """Get the next available API key with automatic rotation"""
        with self.lock:
            if not self.keys:
                raise ValueError(f"No API keys available for {self.service_name}")
            
            current_time = time.time()
            current_key_name, current_key = self.keys[0]
            
            # Reset usage count if minute has passed
            if current_time - self.reset_times[current_key_name] > 60:
                self.usage_count[current_key_name] = 0
                self.reset_times[current_key_name] = current_time
            
            # Check if current key has reached rate limit
            if self.usage_count[current_key_name] >= self.rate_limit:
                # Rotate to next key
                self.keys.rotate(-1)
                current_key_name, current_key = self.keys[0]
                
                # Reset counter for new key if needed
                if current_time - self.reset_times[current_key_name] > 60:
                    self.usage_count[current_key_name] = 0
                    self.reset_times[current_key_name] = current_time
                
                logger.info(f"Rotated to {self.service_name} {current_key_name}")
            
            # Increment usage counter
            self.usage_count[current_key_name] += 1
            
            logger.debug(f"Using {self.service_name} {current_key_name} "
                        f"({self.usage_count[current_key_name]}/{self.rate_limit} calls)")
            
            return current_key
    
    def get_stats(self):
        """Get usage statistics for all keys"""
        stats = {}
        for key_name, _ in self.keys:
            stats[key_name] = {
                'usage': self.usage_count[key_name],
                'last_reset': self.reset_times[key_name]
            }
        return stats

# Initialize API key rotators
try:
    finnhub_rotator = APIKeyRotator('finnhub', rate_limit_per_minute=50)  # Conservative limit
    twelvedata_rotator = APIKeyRotator('twelvedata', rate_limit_per_minute=8)  # TwelveData limit
except ValueError as e:
    logger.error(f"Failed to initialize API rotators: {e}")
    sys.exit(1)

def fetch_finnhub_data(symbol='AAPL', days_back=90):
    """Fetch stock data from Finnhub with automatic key rotation"""
    try:
        api_key = finnhub_rotator.get_key()
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Convert to Unix timestamps
        start_timestamp = int(start_date.timestamp())
        end_timestamp = int(end_date.timestamp())
        
        url = "https://finnhub.io/api/v1/stock/candle"
        params = {
            'symbol': symbol,
            'resolution': 'D',  # Daily data
            'from': start_timestamp,
            'to': end_timestamp,
            'token': api_key
        }
        
        logger.info(f"Fetching Finnhub data for {symbol}")
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('s') == 'ok' and 'c' in data:
                df = pd.DataFrame({
                    'Date': pd.to_datetime(data['t'], unit='s'),
                    'Open': data['o'],
                    'High': data['h'],
                    'Low': data['l'],
                    'Close': data['c'],
                    'Volume': data['v']
                })
                df.set_index('Date', inplace=True)
                logger.info(f"Successfully fetched {len(df)} records from Finnhub")
                return df
            else:
                logger.warning(f"Finnhub returned status: {data.get('s')}")
                return None
        else:
            logger.error(f"Finnhub API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error fetching Finnhub data: {e}")
        return None

def fetch_twelvedata_data(symbol='AAPL', days_back=90):
    """Fetch stock data from TwelveData with automatic key rotation"""
    try:
        api_key = twelvedata_rotator.get_key()
        
        url = "https://api.twelvedata.com/time_series"
        params = {
            'symbol': symbol,
            'interval': '1day',
            'outputsize': min(days_back, 5000),  # TwelveData limit
            'apikey': api_key
        }
        
        logger.info(f"Fetching TwelveData data for {symbol}")
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'values' in data:
                df = pd.DataFrame(data['values'])
                df['datetime'] = pd.to_datetime(df['datetime'])
                df.set_index('datetime', inplace=True)
                df = df.sort_index()
                
                # Convert to numeric
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # Rename columns to match Finnhub format
                df.rename(columns={
                    'open': 'Open',
                    'high': 'High', 
                    'low': 'Low',
                    'close': 'Close',
                    'volume': 'Volume'
                }, inplace=True)
                
                logger.info(f"Successfully fetched {len(df)} records from TwelveData")
                return df
            else:
                logger.warning(f"TwelveData error: {data}")
                return None
        else:
            logger.error(f"TwelveData API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error fetching TwelveData data: {e}")
        return None

def calculate_technical_indicators(df):
    """Calculate technical indicators using ta library"""
    try:
        import ta
        
        # Simple Moving Averages
        df['SMA_20'] = ta.trend.sma_indicator(df['Close'], window=20)
        df['SMA_50'] = ta.trend.sma_indicator(df['Close'], window=50)
        
        # RSI
        df['RSI_14'] = ta.momentum.rsi(df['Close'], window=14)
        
        # MACD
        macd = ta.trend.MACD(df['Close'])
        df['MACD_Line'] = macd.macd()
        df['MACD_Signal'] = macd.macd_signal()
        df['MACD_Histogram'] = macd.macd_diff()
        
        # Bollinger Bands
        bollinger = ta.volatility.BollingerBands(df['Close'], window=20, window_dev=2)
        df['BB_Upper'] = bollinger.bollinger_hband()
        df['BB_Middle'] = bollinger.bollinger_mavg()
        df['BB_Lower'] = bollinger.bollinger_lband()
        
        # Daily Returns
        df['Daily_Return'] = df['Close'].pct_change()
        
        logger.info("Technical indicators calculated successfully")
        return df
        
    except ImportError:
        logger.error("ta library not found. Installing...")
        os.system("pip install ta")
        return calculate_technical_indicators(df)
    except Exception as e:
        logger.error(f"Error calculating technical indicators: {e}")
        return df

def save_to_csv(df, filename='transformed_financial_data.csv'):
    """Save dataframe to CSV with validation"""
    try:
        # Remove any timezone info for CSV compatibility
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        
        df.to_csv(filename)
        logger.info(f"Data saved to {filename}")
        logger.info(f"File contains {len(df)} rows and {len(df.columns)} columns")
        
        # Verify file was created
        if os.path.exists(filename):
            file_size = os.path.getsize(filename)
            logger.info(f"File size: {file_size} bytes")
            return True
        else:
            logger.error(f"Failed to create {filename}")
            return False
            
    except Exception as e:
        logger.error(f"Error saving to CSV: {e}")
        return False

def main():
    """Main pipeline execution"""
    logger.info("Starting Enhanced Financial Data Pipeline with API Rotation")
    
    # Get parameters from environment or use defaults
    symbol = os.getenv('STOCK_SYMBOL', 'AAPL')
    days_back = int(os.getenv('DAYS_BACK', '90'))
    
    logger.info(f"Processing symbol: {symbol}, Days back: {days_back}")
    
    # Try multiple data sources
    df = None
    
    # Try Finnhub first
    logger.info("Attempting to fetch data from Finnhub...")
    df = fetch_finnhub_data(symbol, days_back)
    
    # Fallback to TwelveData if Finnhub fails
    if df is None or len(df) == 0:
        logger.info("Finnhub failed, trying TwelveData...")
        df = fetch_twelvedata_data(symbol, days_back)
    
    if df is None or len(df) == 0:
        logger.error("Failed to fetch data from all sources")
        sys.exit(1)
    
    # Calculate technical indicators
    logger.info("Calculating technical indicators...")
    df = calculate_technical_indicators(df)
    
    # Save to CSV
    if save_to_csv(df):
        logger.info("Pipeline completed successfully!")
        
        # Print API usage statistics
        logger.info("API Usage Statistics:")
        logger.info(f"Finnhub: {finnhub_rotator.get_stats()}")
        logger.info(f"TwelveData: {twelvedata_rotator.get_stats()}")
        
    else:
        logger.error("Pipeline failed during CSV save")
        sys.exit(1)

if __name__ == "__main__":
    main()
