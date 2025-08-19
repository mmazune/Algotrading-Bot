#!/usr/bin/env python3
"""
Automated Financial Data Pipeline Script
Fetches financial data, transforms it, and saves to CSV for GitHub Actions workflow.
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import time
import warnings
warnings.filterwarnings('ignore')

def get_environment_variables():
    """Get configuration from environment variables."""
    config = {
        'stock_symbol': os.getenv('STOCK_SYMBOL', 'AAPL'),
        'data_interval': os.getenv('DATA_FETCH_INTERVAL', '1day'),
        'finnhub_api_key': os.getenv('FINNHUB_API_KEY'),
        'twelvedata_api_key': os.getenv('TWELVEDATA_API_KEY'),
        'minio_access_key': os.getenv('MINIO_ACCESS_KEY'),
        'minio_secret_key': os.getenv('MINIO_SECRET_KEY'),
        'minio_endpoint': os.getenv('MINIO_ENDPOINT')
    }
    
    print(f"Configuration loaded:")
    print(f"  Stock Symbol: {config['stock_symbol']}")
    print(f"  Data Interval: {config['data_interval']}")
    print(f"  Finnhub API Key: {'✓' if config['finnhub_api_key'] else '✗'}")
    print(f"  TwelveData API Key: {'✓' if config['twelvedata_api_key'] else '✗'}")
    
    return config

def fetch_finnhub_data(symbol, api_key, days_back=365):
    """Fetch historical data from Finnhub API."""
    if not api_key:
        print("Warning: Finnhub API key not provided, skipping Finnhub data...")
        return None
    
    try:
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Convert to Unix timestamps
        start_ts = int(start_date.timestamp())
        end_ts = int(end_date.timestamp())
        
        url = f"https://finnhub.io/api/v1/stock/candle"
        params = {
            'symbol': symbol,
            'resolution': 'D',  # Daily data
            'from': start_ts,
            'to': end_ts,
            'token': api_key
        }
        
        print(f"Fetching Finnhub data for {symbol}...")
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('s') == 'ok' and data.get('c'):
            df = pd.DataFrame({
                'timestamp': data['t'],
                'open': data['o'],
                'high': data['h'],
                'low': data['l'],
                'close': data['c'],
                'volume': data['v']
            })
            
            # Convert timestamp to datetime
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
            df = df.drop('timestamp', axis=1)
            df = df.set_index('datetime')
            
            print(f"✓ Finnhub data fetched successfully: {len(df)} records")
            return df
        else:
            print(f"✗ Finnhub API returned no data or error: {data}")
            return None
            
    except Exception as e:
        print(f"✗ Error fetching Finnhub data: {e}")
        return None

def fetch_twelvedata_data(symbol, api_key, interval='1day', days_back=365):
    """Fetch historical data from TwelveData API."""
    if not api_key:
        print("Warning: TwelveData API key not provided, skipping TwelveData data...")
        return None
    
    try:
        url = "https://api.twelvedata.com/time_series"
        params = {
            'symbol': symbol,
            'interval': interval,
            'outputsize': min(days_back, 5000),  # API limit
            'apikey': api_key
        }
        
        print(f"Fetching TwelveData data for {symbol} with interval {interval}...")
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if 'values' in data and data['values']:
            df = pd.DataFrame(data['values'])
            
            # Convert columns to appropriate types
            df['datetime'] = pd.to_datetime(df['datetime'])
            df = df.set_index('datetime')
            
            # Convert price columns to float
            price_cols = ['open', 'high', 'low', 'close']
            for col in price_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
            
            # Sort by date (newest first from API, we want oldest first)
            df = df.sort_index()
            
            print(f"✓ TwelveData data fetched successfully: {len(df)} records")
            return df
        else:
            print(f"✗ TwelveData API returned no data or error: {data}")
            return None
            
    except Exception as e:
        print(f"✗ Error fetching TwelveData data: {e}")
        return None

def calculate_technical_indicators(df):
    """Calculate technical indicators for the dataset."""
    try:
        print("Calculating technical indicators...")
        
        # Simple Moving Averages
        df['SMA_20'] = df['close'].rolling(window=20).mean()
        df['SMA_50'] = df['close'].rolling(window=50).mean()
        
        # RSI (Relative Strength Index)
        def calculate_rsi(prices, window=14):
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return rsi
        
        df['RSI_14'] = calculate_rsi(df['close'])
        
        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD_Line'] = exp1 - exp2
        df['MACD_Signal'] = df['MACD_Line'].ewm(span=9, adjust=False).mean()
        df['MACD_Histogram'] = df['MACD_Line'] - df['MACD_Signal']
        
        # Bollinger Bands
        df['BB_Middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
        df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)
        
        # Daily returns
        df['daily_return'] = df['close'].pct_change()
        
        # Add symbol column
        df['symbol'] = os.getenv('STOCK_SYMBOL', 'AAPL')
        
        print(f"✓ Technical indicators calculated successfully")
        return df
        
    except Exception as e:
        print(f"✗ Error calculating technical indicators: {e}")
        return df

def save_to_csv(df, filename='transformed_financial_data.csv'):
    """Save the transformed data to CSV file."""
    try:
        # Reset index to make datetime a column
        df_export = df.reset_index()
        
        # Round numeric columns for cleaner output
        numeric_columns = df_export.select_dtypes(include=[np.number]).columns
        df_export[numeric_columns] = df_export[numeric_columns].round(6)
        
        # Save to CSV
        df_export.to_csv(filename, index=False)
        
        print(f"✓ Data saved to {filename}")
        print(f"  Shape: {df_export.shape}")
        print(f"  Columns: {list(df_export.columns)}")
        print(f"  Date range: {df_export['datetime'].min()} to {df_export['datetime'].max()}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error saving data to CSV: {e}")
        return False

def main():
    """Main pipeline execution."""
    print("=" * 60)
    print("🚀 STARTING AUTOMATED FINANCIAL DATA PIPELINE")
    print("=" * 60)
    
    # Get configuration
    config = get_environment_variables()
    
    # Try to fetch data from available sources
    combined_df = None
    
    # Try TwelveData first (more reliable for this use case)
    if config['twelvedata_api_key']:
        df_twelve = fetch_twelvedata_data(
            config['stock_symbol'], 
            config['twelvedata_api_key'], 
            config['data_interval']
        )
        if df_twelve is not None and not df_twelve.empty:
            combined_df = df_twelve
    
    # Try Finnhub as backup
    if combined_df is None and config['finnhub_api_key']:
        df_finnhub = fetch_finnhub_data(config['stock_symbol'], config['finnhub_api_key'])
        if df_finnhub is not None and not df_finnhub.empty:
            combined_df = df_finnhub
    
    # Check if we have any data
    if combined_df is None or combined_df.empty:
        print("✗ PIPELINE FAILED: No data could be fetched from any source")
        print("  Please check your API keys and network connectivity")
        sys.exit(1)
    
    print(f"✓ Successfully fetched {len(combined_df)} records")
    
    # Calculate technical indicators
    combined_df = calculate_technical_indicators(combined_df)
    
    # Save to CSV
    success = save_to_csv(combined_df)
    
    if success:
        print("=" * 60)
        print("✅ PIPELINE COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print(f"Data for {config['stock_symbol']} has been processed and saved.")
        print("Check transformed_financial_data.csv for the results.")
    else:
        print("=" * 60)
        print("❌ PIPELINE FAILED!")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()
