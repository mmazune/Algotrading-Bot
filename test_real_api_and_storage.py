import time
from api_rotation import twelvedata_manager, finnhub_rest_manager, finnhub_websocket_manager
from config import BUCKET_NAME
import requests
import finnhub
import boto3
from botocore.client import Config

# Setup MinIO client
MINIO_ENDPOINT = 'http://localhost:9000'
MINIO_ACCESS_KEY = 'minioadmin'
MINIO_SECRET_KEY = 'minioadmin'
try:
    s3_client = boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )
    print("MinIO S3 client initialized for data storage.")
except Exception as e:
    print(f"Error initializing MinIO S3 client: {e}")
    s3_client = None

# Test Twelve Data API keys
print("\n--- Testing Twelve Data API keys with real requests ---")
for i in range(7):
    key = twelvedata_manager.get_key()
    params = {'symbol': 'AAPL', 'interval': '1day', 'apikey': key}
    try:
        resp = requests.get('https://api.twelvedata.com/time_series', params=params)
        print(f"Key {i+1}: HTTP {resp.status_code}, {resp.json().get('status','ok')}")
        # Save to MinIO
        if s3_client:
            s3_client.put_object(Bucket=BUCKET_NAME, Key=f'test/twelvedata_{i+1}.json', Body=resp.content)
    except Exception as e:
        print(f"Key {i+1}: Error: {e}")
    time.sleep(1)

# Test Finnhub REST API keys
print("\n--- Testing Finnhub REST API keys with real requests ---")
for i in range(7):
    key = finnhub_rest_manager.get_key("rest")
    try:
        client = finnhub.Client(api_key=key)
        quote = client.quote('AAPL')
        print(f"Key {i+1}: Finnhub quote: {quote}")
        # Save to MinIO
        if s3_client:
            s3_client.put_object(Bucket=BUCKET_NAME, Key=f'test/finnhub_{i+1}.json', Body=str(quote).encode())
    except Exception as e:
        print(f"Key {i+1}: Error: {e}")
    time.sleep(1)

# Test Finnhub WebSocket API keys (connect and subscribe, then close)
print("\n--- Testing Finnhub WebSocket API keys (connect/subscribe/close) ---")
try:
    import websocket
    import json
    for i in range(2):  # Only test 2 keys to avoid long waits
        key = finnhub_websocket_manager.get_key("websocket")
        ws_url = f"wss://ws.finnhub.io?token={key}"
        def on_message(ws, message):
            print(f"Key {i+1}: WebSocket message received.")
            ws.close()
        ws = websocket.WebSocketApp(ws_url, on_message=on_message)
        print(f"Key {i+1}: Connecting to {ws_url}")
        ws.run_forever(dispatcher=None, reconnect=0)
        time.sleep(1)
except Exception as e:
    print(f"WebSocket test error: {e}")

print("\nCheck your MinIO bucket for test data and review the above output for API key validity and data retrieval.")
