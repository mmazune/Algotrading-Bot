#!/usr/bin/env python3
"""
Test script to verify CSV generation with dummy data
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Create dummy data
dates = pd.date_range(start=datetime.now() - timedelta(days=100), end=datetime.now(), freq='D')
np.random.seed(42)

dummy_data = {
    'datetime': dates,
    'open': 150 + np.cumsum(np.random.randn(len(dates)) * 0.5),
    'high': 152 + np.cumsum(np.random.randn(len(dates)) * 0.5),
    'low': 148 + np.cumsum(np.random.randn(len(dates)) * 0.5),
    'close': 150 + np.cumsum(np.random.randn(len(dates)) * 0.5),
    'volume': np.random.randint(1000000, 5000000, len(dates)),
    'SMA_20': 150 + np.cumsum(np.random.randn(len(dates)) * 0.3),
    'SMA_50': 150 + np.cumsum(np.random.randn(len(dates)) * 0.2),
    'RSI_14': 30 + np.random.rand(len(dates)) * 40,
    'MACD_Line': np.random.randn(len(dates)) * 2,
    'MACD_Signal': np.random.randn(len(dates)) * 1.5,
    'MACD_Histogram': np.random.randn(len(dates)) * 0.5,
    'BB_Middle': 150 + np.cumsum(np.random.randn(len(dates)) * 0.3),
    'BB_Upper': 155 + np.cumsum(np.random.randn(len(dates)) * 0.3),
    'BB_Lower': 145 + np.cumsum(np.random.randn(len(dates)) * 0.3),
    'daily_return': np.random.randn(len(dates)) * 0.02,
    'symbol': 'AAPL'
}

df = pd.DataFrame(dummy_data)

# Save to CSV
df.to_csv('transformed_financial_data.csv', index=False)
print("✓ Test data saved to transformed_financial_data.csv")
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
