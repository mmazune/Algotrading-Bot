#!/usr/bin/env python3
"""
Quick script to run just the repurposing function
"""

# Import the needed functions from main data collector
from main_data_collector import repurpose_twelvedata_as_finnhub

if __name__ == "__main__":
    print("Running repurposing function...")
    repurpose_twelvedata_as_finnhub()
    print("Done!")
