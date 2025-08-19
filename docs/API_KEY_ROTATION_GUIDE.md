# 🔄 Multi-API Key Rotation Setup Guide

## 🎯 Overview

Your enhanced automated trading pipeline now supports **automatic API key rotation** to handle rate limits efficiently. This system can manage multiple API keys for both Finnhub and TwelveData, automatically switching between them when limits are reached.

## 🔑 API Key Configuration Options

### Option 1: Single Keys (Basic Setup)
Set up one key per service:
```bash
# In GitHub Secrets:
FINNHUB_API_KEY = "your_primary_finnhub_key"
TWELVEDATA_API_KEY = "your_primary_twelvedata_key"
```

### Option 2: Multiple Keys (Recommended - Production Ready)
Set up multiple keys per service for automatic rotation:

```bash
# Finnhub Keys (add as many as you have)
FINNHUB_API_KEY_1 = "d18kaj9r01qg5218jce0d18kaj9r01qg5218jceg"  # Leticia's key
FINNHUB_API_KEY_2 = "d18kn6pr01qg5218lii0d18kn6pr01qg5218liig"  # Nicky's key  
FINNHUB_API_KEY_3 = "d18kilpr01qg5218kpjgd18kilpr01qg5218kpk0"  # Mark's key
FINNHUB_API_KEY_4 = "d18kci9r01qg5218jnvgd18kci9r01qg5218jo00"  # Pamella's key
FINNHUB_API_KEY_5 = "d18kcehr01qg5218jn5gd18kcehr01qg5218jn60"  # Elijah's key
FINNHUB_API_KEY_6 = "d16rlcpr01qkv5jctje0d16rlcpr01qkv5jctjeg"  # Katrina's key
FINNHUB_API_KEY_7 = "d13gq5pr01qs7glhghj0d13gq5pr01qs7glhghjg"  # Mine

# TwelveData Keys (add as many as you have)  
TWELVEDATA_API_KEY_1 = "509e81ce956741b48b5db02c7d4baeba"  # Elijah's key
TWELVEDATA_API_KEY_2 = "d7ca6bcdd1d247289088dd40a1cad1ac"  # Mark's key
TWELVEDATA_API_KEY_3 = "1f21fc9b320743f793737f7822cd5910"  # Pamella's key
TWELVEDATA_API_KEY_4 = "5cd89fc3c99d4e86bbf3db3fc633d14c"  # Nicky's key
TWELVEDATA_API_KEY_5 = "8cb1d203fde04aa18592197405b14280"  # Leticia's key
TWELVEDATA_API_KEY_6 = "5ebf17461c3946afb292f55a6f1b5c0b"  # Katrina's key
TWELVEDATA_API_KEY_7 = "9977c171aff74be9948775735805e5c0"  # Mine
```

## 🚀 GitHub Repository Setup

### Step 1: Add Secrets to GitHub
1. Go to your repository: https://github.com/mmazune/Algotrading-Bot
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** for each key above

### Step 2: Updated Files 
Your repository now has these enhanced files:

- ✅ `automated_data_pipeline_with_rotation.py` - Enhanced pipeline with key rotation
- ✅ `.github/workflows/data-pipeline.yml` - Updated workflow supporting multiple keys
- ✅ `test_api_keys.py` - Key testing and validation script
- ✅ `GITHUB_SECRETS_SETUP.md` - Updated setup guide

## 🔧 How API Rotation Works

### Rate Limit Management:
- **Finnhub**: 50 calls per minute per key (conservative limit)
- **TwelveData**: 8 calls per minute per key
- **Automatic rotation**: When a key hits its limit, system switches to next key
- **Fallback**: If one service fails completely, falls back to other service

### Key Selection Logic:
1. **Load all available keys** from environment variables
2. **Track usage** for each key individually  
3. **Auto-rotate** when rate limit reached
4. **Reset counters** every minute
5. **Log usage statistics** for monitoring

## 📊 Usage Examples

### Local Testing:
```bash
# Set up environment with multiple keys
export FINNHUB_API_KEY_1="your_first_finnhub_key"
export FINNHUB_API_KEY_2="your_second_finnhub_key" 
export TWELVEDATA_API_KEY_1="your_first_twelvedata_key"
export TWELVEDATA_API_KEY_2="your_second_twelvedata_key"

# Test all keys
python test_api_keys.py

# Run enhanced pipeline
python automated_data_pipeline_with_rotation.py
```

### GitHub Actions (Automatic):
The workflow will automatically:
- Use all configured API keys
- Rotate between them as needed
- Fall back between services if one fails
- Generate detailed logs showing which keys were used

## 📈 Expected Performance Improvements

### With Multiple Keys:
- **7x Finnhub capacity**: 350 calls/minute (vs 50 with single key)
- **7x TwelveData capacity**: 56 calls/minute (vs 8 with single key)  
- **Better reliability**: Automatic fallback if keys fail
- **Detailed monitoring**: Usage stats for each key

### Rate Limit Handling:
```
Example log output:
2025-08-19 09:45:11,336 - INFO - Initialized finnhub rotator with 7 keys
2025-08-19 09:45:11,336 - INFO - Initialized twelvedata rotator with 7 keys
...
2025-08-19 09:45:15,683 - INFO - Using finnhub key_1 (23/50 calls)
2025-08-19 09:45:16,841 - INFO - Rotated to finnhub key_2
2025-08-19 09:45:17,123 - INFO - Using finnhub key_2 (1/50 calls)
```

## ✅ Verification Steps

### 1. Test Your Keys:
```bash
python test_api_keys.py
```

### 2. Expected Output:
```
🔵 FINNHUB RESULTS:
   ✅ Valid keys: 7
   ❌ Invalid keys: 0

🟡 TWELVEDATA RESULTS:  
   ✅ Valid keys: 7
   ❌ Invalid keys: 0

🎯 OVERALL SUMMARY:
   Total valid keys: 14
   Success rate: 100.0%
```

### 3. Run Enhanced Pipeline:
```bash
python automated_data_pipeline_with_rotation.py
```

### 4. Check GitHub Actions:
- Go to **Actions** tab in your repository
- Run the **Automated Financial Data Pipeline** workflow
- Check logs for API rotation messages

## 🔒 Security Best Practices

- ✅ **Never commit API keys** to your repository
- ✅ **Use GitHub Secrets** for all sensitive data
- ✅ **Rotate keys regularly** if any become compromised
- ✅ **Monitor usage** through the test script
- ✅ **Use descriptive names** (like `_1`, `_2`) for organization

## 🎉 Ready for Production!

Your enhanced pipeline now provides:
- **Maximum throughput** with multiple API keys
- **Automatic failover** between data sources
- **Detailed logging** and monitoring
- **GitHub Actions integration** with full rotation support
- **Backward compatibility** with single-key setups

Simply add your API keys as GitHub Secrets and enjoy robust, high-volume data collection! 🚀

---
**Last Updated**: August 19, 2025  
**Status**: ✅ Enhanced Multi-Key Rotation System - Production Ready
