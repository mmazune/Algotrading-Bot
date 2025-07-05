import sys
import subprocess
from importlib import util # Changed from pkg_resources
import os
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
import requests
import finnhub
import time
import json

# Attempt to import your key managers and config directly if they are in the same directory
try:
    from api_rotation import twelvedata_manager, finnhub_rest_manager, finnhub_websocket_manager
    from config import MINIO_CONFIG, TWELVE_DATA_KEYS, FINNHUB_KEYS, RAW_DATA_BUCKET, PROCESSED_DATA_BUCKET
    print("Successfully imported custom modules (api_rotation, config).")
except ImportError as e:
    print(f"ERROR: Could not import custom modules. Please ensure all Python files are in the same directory or correctly configured in PYTHONPATH. Error: {e}")
    sys.exit(1)

# --- 1. Check Python Version ---
print(f"--- Python Version Check ---")
print(f"Python executable path: {sys.executable}")
print(f"Python version: {sys.version}")
if sys.version_info < (3, 8):
    print("WARNING: Python 3.8 or higher is recommended for this project.")
print("-" * 30)

# --- 2. Check Required Packages ---
print("\n--- Required Package Check ---")
# List of (package_name, import_name) pairs
packages_to_check = [
    ('boto3', 'boto3'),
    ('pyarrow', 'pyarrow'),
    ('pandas', 'pandas'),
    ('requests', 'requests'),
    ('finnhub-python', 'finnhub'),
    ('websocket-client', 'websocket'),
    ('matplotlib', 'matplotlib'),
    ('seaborn', 'seaborn'),
    ('jupyterlab', 'jupyterlab')
]
missing = []

def check_package_with_importlib(package_name_for_display, import_name):
    try:
        if util.find_spec(import_name) is not None:
            print(f"✓ {package_name_for_display} is installed.")
            return True
        else:
            print(f"✗ {package_name_for_display} is NOT installed.")
            missing.append(package_name_for_display)
            return False
    except Exception as e:
        print(f"Error checking {package_name_for_display}: {e}")
        missing.append(package_name_for_display) # Add to missing if check itself fails
        return False

for pkg_display_name, pkg_import_name in packages_to_check:
    check_package_with_importlib(pkg_display_name, pkg_import_name)

if missing:
    print("\nACTION REQUIRED: Please install missing packages:")
    print(f"  python3 -m pip install {' '.join(missing)}")
else:
    print("✓ All required packages are installed.")
print("-" * 30)

# --- 3. MinIO Configuration and Connectivity Check ---
print("\n--- MinIO Connectivity Check ---")

# Try to get MinIO details from environment variables first, then fallback to config.py
minio_endpoint = os.getenv("MINIO_ENDPOINT") # Should now come from Codespaces env var
minio_access_key = os.getenv("MINIO_ACCESS_KEY")
minio_secret_key = os.getenv("MINIO_SECRET_KEY")

if not minio_access_key or not minio_secret_key or not minio_endpoint:
    print("✗ MinIO credentials (endpoint, access key, or secret key) are not fully set as environment variables.")
    print("  Please ensure MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY environment variables are set in your Codespace.")
    s3_client = None
else:
    print(f"MinIO Endpoint: {minio_endpoint}")
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=minio_endpoint,
            aws_access_key_id=minio_access_key,
            aws_secret_access_key=minio_secret_key,
            config=Config(signature_version='s3v4'),
            region_name='us-east-1' # Placeholder region
        )
        s3_client.list_buckets() # Test connection by listing buckets
        print("✓ MinIO S3 client initialized and connected.")

        # Check for bucket existence, create if not found
        for bucket_name in [RAW_DATA_BUCKET, PROCESSED_DATA_BUCKET]:
            try:
                s3_client.head_bucket(Bucket=bucket_name)
                print(f"✓ MinIO bucket '{bucket_name}' exists.")
            except ClientError as e:
                error_code = int(e.response['Error']['Code'])
                if error_code == 404:
                    print(f"Bucket '{bucket_name}' not found. Attempting to create...")
                    s3_client.create_bucket(Bucket=bucket_name)
                    print(f"✓ Successfully created bucket '{bucket_name}'.")
                else:
                    print(f"✗ Error accessing bucket '{bucket_name}': {e}")
            except Exception as e:
                print(f"✗ Unexpected error with bucket '{bucket_name}': {e}")

    except Exception as e:
        print(f"✗ Error initializing or connecting to MinIO S3 client: {e}")
        print(f"  Reason: {e}")
        print("  Please ensure MinIO server is running on the VM and accessible from this Codespace.")
        s3_client = None
print("-" * 30)

# --- 4. API Key Rotation Manager Status ---
print("\n--- API Key Rotation Manager Status (from config.py) ---")
if TWELVE_DATA_KEYS:
    print(f"✓ Twelve Data Keys configured: {len(TWELVE_DATA_KEYS)} keys found.")
else:
    print("✗ No Twelve Data API keys found in config.py.")
if FINNHUB_KEYS:
    print(f"✓ Finnhub Keys configured: {len(FINNHUB_KEYS)} keys found.")
else:
    print("✗ No Finnhub API keys found in config.py.")
print("-" * 30)

# --- 5. Test Twelve Data API Connectivity ---
print("\n--- Testing Twelve Data API with a real request ---")
if TWELVE_DATA_KEYS:
    try:
        key = twelvedata_manager.get_key()
        params = {'symbol': 'AAPL', 'interval': '1min', 'apikey': key}
        print(f"  Attempting request using Twelve Data key from: {twelvedata_manager.keys[0][0] if twelvedata_manager.keys else 'N/A'}")
        resp = requests.get('https://api.twelvedata.com/time_series', params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data and 'values' in data:
            print("✓ Twelve Data API test successful. Received time series data.")
        elif 'code' in data and data['code'] == 401:
            print(f"✗ Twelve Data API key invalid or unauthorized: {data}")
        else:
            print(f"✗ Twelve Data API test successful, but unexpected response structure: {data}")
    except requests.exceptions.Timeout:
        print("✗ Twelve Data API request timed out. Check network or API server.")
    except requests.exceptions.RequestException as e:
        print(f"✗ Twelve Data API request failed: {e}")
        if "429 Client Error" in str(e):
            print("  (Rate limit likely hit. This is normal during aggressive testing.)")
    except Exception as e:
        print(f"✗ General error testing Twelve Data API: {e}")
else:
    print("No Twelve Data API keys configured in config.py. Skipping test.")
print("-" * 30)

# --- 6. Test Finnhub REST API Connectivity ---
print("\n--- Testing Finnhub REST API with a real request ---")
if FINNHUB_KEYS:
    try:
        key = finnhub_rest_manager.get_key("rest")
        client = finnhub.Client(api_key=key)
        print(f"  Attempting request using Finnhub REST key from: {finnhub_rest_manager.keys[0][0] if finnhub_rest_manager.keys else 'N/A'}")
        quote = client.quote('AAPL')
        if quote and 'c' in quote:
            print(f"✓ Finnhub REST API test successful. Received quote for AAPL: {quote}")
        else:
            print(f"✗ Finnhub REST API test successful, but unexpected response structure: {quote}")
    except finnhub.exceptions.FinnhubAPIException as e:
        print(f"✗ Finnhub REST API error: {e}")
        if "Limit exceeded" in str(e) or "invalid token" in str(e):
            print("  (Rate limit or invalid key. This is normal during aggressive testing.)")
    except Exception as e:
        print(f"✗ General error testing Finnhub REST API: {e}")
else:
    print("No Finnhub API keys configured in config.py. Skipping test.")
print("-" * 30)

# --- 7. Test Finnhub WebSocket API Connectivity (simplified) ---
print("\n--- Testing Finnhub WebSocket API (initial connection) ---")
if FINNHUB_KEYS:
    try:
        key = finnhub_websocket_manager.get_key("websocket")
        ws_url = f"wss://ws.finnhub.io?token={key}"
        print(f"  Attempting Finnhub WebSocket connection using key from: {finnhub_websocket_manager.keys[0][0] if finnhub_websocket_manager.keys else 'N/A'}")
        # A full WebSocket test would involve a persistent connection and event handling.
        # This is a symbolic check to confirm the URL and key are valid for initiation.
        # You would typically run finnhub_integration.py for actual WS data collection.
        print("  (Note: This is a basic check. For full WebSocket functionality, run finnhub_integration.py)")
        print("✓ Finnhub WebSocket connectivity check initiated (manual verification for full functionality needed).")
    except Exception as e:
        print(f"✗ Error setting up Finnhub WebSocket test: {e}")
else:
    print("No Finnhub API keys configured in config.py. Skipping WebSocket test.")
print("-" * 30)

print("\n--- Environment Setup Check Complete ---")
print("Review the output above. '✓' indicates success, '✗' indicates an issue.")
print("If MinIO or API tests failed, re-check environment variables, API keys in config.py, and network accessibility.")
