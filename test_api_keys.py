#!/usr/bin/env python3
"""
API Key Management and Testing Script
This script helps test and manage multiple API keys for the automated pipeline.
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_finnhub_key(api_key, key_name="Unknown"):
    """Test a Finnhub API key"""
    try:
        url = "https://finnhub.io/api/v1/quote"
        params = {'symbol': 'AAPL', 'token': api_key}
        
        start_time = time.time()
        response = requests.get(url, params=params, timeout=10)
        response_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            if 'c' in data and data['c'] is not None:
                logger.info(f"✅ Finnhub {key_name}: VALID (Response time: {response_time:.2f}s)")
                return True, response_time, data.get('c', 'N/A')
            else:
                logger.warning(f"❌ Finnhub {key_name}: Invalid response - {data}")
                return False, response_time, str(data)
        else:
            logger.error(f"❌ Finnhub {key_name}: HTTP {response.status_code} - {response.text}")
            return False, response_time, f"HTTP {response.status_code}"
            
    except Exception as e:
        logger.error(f"❌ Finnhub {key_name}: Exception - {e}")
        return False, 0, str(e)

def test_twelvedata_key(api_key, key_name="Unknown"):
    """Test a TwelveData API key"""
    try:
        url = "https://api.twelvedata.com/quote"
        params = {'symbol': 'AAPL', 'apikey': api_key}
        
        start_time = time.time()
        response = requests.get(url, params=params, timeout=10)
        response_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            if 'close' in data and data['close'] is not None:
                logger.info(f"✅ TwelveData {key_name}: VALID (Response time: {response_time:.2f}s)")
                return True, response_time, data.get('close', 'N/A')
            else:
                logger.warning(f"❌ TwelveData {key_name}: Invalid response - {data}")
                return False, response_time, str(data)
        else:
            logger.error(f"❌ TwelveData {key_name}: HTTP {response.status_code} - {response.text}")
            return False, response_time, f"HTTP {response.status_code}"
            
    except Exception as e:
        logger.error(f"❌ TwelveData {key_name}: Exception - {e}")
        return False, 0, str(e)

def load_keys_from_environment():
    """Load all API keys from environment variables"""
    keys = {
        'finnhub': {},
        'twelvedata': {}
    }
    
    # Load Finnhub keys
    single_key = os.getenv('FINNHUB_API_KEY')
    if single_key:
        keys['finnhub']['primary'] = single_key
    
    # Load numbered Finnhub keys
    key_index = 1
    while True:
        key = os.getenv(f'FINNHUB_API_KEY_{key_index}')
        if not key:
            break
        keys['finnhub'][f'key_{key_index}'] = key
        key_index += 1
    
    # Load TwelveData keys
    single_key = os.getenv('TWELVEDATA_API_KEY')
    if single_key:
        keys['twelvedata']['primary'] = single_key
    
    # Load numbered TwelveData keys
    key_index = 1
    while True:
        key = os.getenv(f'TWELVEDATA_API_KEY_{key_index}')
        if not key:
            break
        keys['twelvedata'][f'key_{key_index}'] = key
        key_index += 1
    
    return keys

def test_all_keys():
    """Test all available API keys"""
    logger.info("🔍 Testing all available API keys...")
    
    keys = load_keys_from_environment()
    results = {
        'finnhub': {'valid': 0, 'invalid': 0, 'details': []},
        'twelvedata': {'valid': 0, 'invalid': 0, 'details': []}
    }
    
    # Test Finnhub keys
    logger.info(f"\n📊 Testing {len(keys['finnhub'])} Finnhub keys...")
    for key_name, api_key in keys['finnhub'].items():
        is_valid, response_time, result = test_finnhub_key(api_key, key_name)
        results['finnhub']['details'].append({
            'name': key_name,
            'valid': is_valid,
            'response_time': response_time,
            'result': result
        })
        if is_valid:
            results['finnhub']['valid'] += 1
        else:
            results['finnhub']['invalid'] += 1
        
        time.sleep(1)  # Rate limiting between tests
    
    # Test TwelveData keys
    logger.info(f"\n📊 Testing {len(keys['twelvedata'])} TwelveData keys...")
    for key_name, api_key in keys['twelvedata'].items():
        is_valid, response_time, result = test_twelvedata_key(api_key, key_name)
        results['twelvedata']['details'].append({
            'name': key_name,
            'valid': is_valid,
            'response_time': response_time,
            'result': result
        })
        if is_valid:
            results['twelvedata']['valid'] += 1
        else:
            results['twelvedata']['invalid'] += 1
        
        time.sleep(1)  # Rate limiting between tests
    
    return results

def generate_report(results):
    """Generate a comprehensive test report"""
    logger.info("\n" + "="*50)
    logger.info("📋 API KEY TEST REPORT")
    logger.info("="*50)
    
    # Finnhub summary
    logger.info(f"\n🔵 FINNHUB RESULTS:")
    logger.info(f"   ✅ Valid keys: {results['finnhub']['valid']}")
    logger.info(f"   ❌ Invalid keys: {results['finnhub']['invalid']}")
    
    if results['finnhub']['details']:
        logger.info(f"   📝 Details:")
        for detail in results['finnhub']['details']:
            status = "✅ VALID" if detail['valid'] else "❌ INVALID"
            logger.info(f"      {detail['name']}: {status} ({detail['response_time']:.2f}s)")
    
    # TwelveData summary
    logger.info(f"\n🟡 TWELVEDATA RESULTS:")
    logger.info(f"   ✅ Valid keys: {results['twelvedata']['valid']}")
    logger.info(f"   ❌ Invalid keys: {results['twelvedata']['invalid']}")
    
    if results['twelvedata']['details']:
        logger.info(f"   📝 Details:")
        for detail in results['twelvedata']['details']:
            status = "✅ VALID" if detail['valid'] else "❌ INVALID"
            logger.info(f"      {detail['name']}: {status} ({detail['response_time']:.2f}s)")
    
    # Overall summary
    total_valid = results['finnhub']['valid'] + results['twelvedata']['valid']
    total_invalid = results['finnhub']['invalid'] + results['twelvedata']['invalid']
    
    logger.info(f"\n🎯 OVERALL SUMMARY:")
    logger.info(f"   Total valid keys: {total_valid}")
    logger.info(f"   Total invalid keys: {total_invalid}")
    logger.info(f"   Success rate: {(total_valid/(total_valid+total_invalid)*100):.1f}%" if (total_valid+total_invalid) > 0 else "N/A")

def main():
    """Main function"""
    if len(sys.argv) > 1 and sys.argv[1] == '--help':
        print("""
API Key Management Script

Usage:
  python test_api_keys.py              # Test all keys from environment
  python test_api_keys.py --help       # Show this help

Environment Variables:
  FINNHUB_API_KEY         # Single Finnhub key
  FINNHUB_API_KEY_1       # Multiple Finnhub keys (_1, _2, _3, etc.)
  TWELVEDATA_API_KEY      # Single TwelveData key  
  TWELVEDATA_API_KEY_1    # Multiple TwelveData keys (_1, _2, _3, etc.)

Example setup:
  export FINNHUB_API_KEY_1="your_first_key"
  export FINNHUB_API_KEY_2="your_second_key"
  export TWELVEDATA_API_KEY_1="your_first_key"
  export TWELVEDATA_API_KEY_2="your_second_key"
        """)
        return
    
    logger.info("🚀 Starting API Key Management System")
    
    # Load and validate keys
    keys = load_keys_from_environment()
    
    total_keys = len(keys['finnhub']) + len(keys['twelvedata'])
    if total_keys == 0:
        logger.error("❌ No API keys found in environment variables!")
        logger.info("💡 Set keys using: FINNHUB_API_KEY_1, TWELVEDATA_API_KEY_1, etc.")
        sys.exit(1)
    
    logger.info(f"🔑 Found {len(keys['finnhub'])} Finnhub keys and {len(keys['twelvedata'])} TwelveData keys")
    
    # Test all keys
    results = test_all_keys()
    
    # Generate report
    generate_report(results)
    
    # Check if we have enough valid keys
    valid_finnhub = results['finnhub']['valid']
    valid_twelvedata = results['twelvedata']['valid']
    
    if valid_finnhub == 0 and valid_twelvedata == 0:
        logger.error("❌ No valid API keys found! Pipeline will fail.")
        sys.exit(1)
    elif valid_finnhub == 0:
        logger.warning("⚠️  No valid Finnhub keys - pipeline will rely only on TwelveData")
    elif valid_twelvedata == 0:
        logger.warning("⚠️  No valid TwelveData keys - pipeline will rely only on Finnhub")
    else:
        logger.info("✅ Pipeline ready with multiple valid data sources!")

if __name__ == "__main__":
    main()
