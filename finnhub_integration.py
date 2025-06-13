try:
    import sys
    from importlib import util

    # Verify required packages
    required_packages = {
        'finnhub-python': 'finnhub',
        'boto3': 'boto3',
        'botocore': 'botocore.client'
    }

    for package_name, import_name in required_packages.items():
        if util.find_spec(import_name.split('.')[0]) is None:
            print(f"ERROR: {package_name} is not installed. Please run: pip install {package_name}")
            sys.exit(1)

    # If verification passes, import the packages
    import finnhub
    import websocket
    import json
    from datetime import datetime
    import time
    import threading
    import os
    import boto3
    from botocore.client import Config
    import io

except ImportError as e:
    print(f"Error importing required packages: {e}")
    print("\nPlease install required packages using:")
    print("pip install finnhub-python boto3")
    sys.exit(1)

# --- Your API Keys ---
# IMPORTANT: Replace with your actual Finnhub API Key
FINNHUB_API_KEY = "d13gq5pr01qs7glhghj0d13gq5pr01qs7glhghjg" # <<< REPLACE THIS PART ONLY

# --- MinIO Connection Details (ensure these match your MinIO setup) ---
# IMPORTANT: Replace with your actual MinIO Access Key and Secret Key if different from 'minioadmin'
MINIO_ENDPOINT = 'http://localhost:9000'
MINIO_ACCESS_KEY = 'minioadmin' # <<< REPLACE THIS PART ONLY
MINIO_SECRET_KEY = 'minioadmin' # <<< REPLACE THIS PART ONLY

# Initialize MinIO S3 client
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
    print(f"Error initializing MinIO S3 client: {e}. Ensure MinIO Docker container is running and accessible.")
    s3_client = None

# --- Helper Function to Save Data to MinIO ---
def save_to_minio(bucket_name, object_name, data_bytes, content_type='application/json'):
    if not s3_client:
        print(f"MinIO client not available for '{object_name}', skipping save.")
        return

    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=data_bytes,
            ContentType=content_type
        )
        print(f"Successfully saved {object_name} to MinIO bucket '{bucket_name}'.")
    except boto3.exceptions.ClientError as e:
        print(f"MinIO Client Error for {object_name}: {e}")
        if e.response['Error']['Code'] == 'NoSuchBucket':
            print(f"ACTION REQUIRED: Bucket '{bucket_name}' does not exist. Please create it in the MinIO console (http://localhost:9001).")
        else:
            print(f"An unexpected S3 client error occurred: {e}")
    except Exception as e:
        print(f"General error saving {object_name} to MinIO: {e}")

# --- Finnhub Real-time (WebSocket) Example ---
# IMPORTANT: Finnhub's free tier WebSocket is *very* limited (50 messages per day sent *by you*).
# This example will likely hit that limit quickly from the initial subscription.
def run_finnhub_websocket():
    print("\n--- Initiating Finnhub WebSocket Stream (Real-time Trades) ---")
    ws_url = f"wss://ws.finnhub.io?token={FINNHUB_API_KEY}"
    ws_app = None

    def on_message(ws_app, message):
        try:
            msg = json.loads(message)
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            
            if msg.get('type') == 'trade' and msg.get('data'):
                for trade in msg['data']:
                    symbol = trade.get('s', 'UNKNOWN_SYMBOL').upper()
                    price = trade.get('p', 'N/A')
                    volume = trade.get('v', 'N/A')
                    print(f"Trade: {symbol} - Price: {price}, Volume: {volume}")
                    
                    object_name = f"finnhub_websocket/{symbol}/{datetime.now().strftime('%Y%m%d')}/trade_{timestamp_str}.json"
                    save_to_minio("raw-tick-data", object_name, json.dumps(trade).encode('utf-8'))
            elif msg.get('type') == 'ping':
                print("❤️ WebSocket heartbeat received")
            else:
                print(f"Other message received: {msg}")
        except Exception as e:
            print(f"Message processing error: {e}")

    def on_error(ws_app, error):
        print(f"⚠️ WebSocket Error: {error}")
        if "limit" in str(error).lower():
            print("NOTE: You may have hit the free tier limit (50 messages/day)")

    def on_close(ws_app, close_status_code, close_msg):
        print(f"🔴 WebSocket Closed - Status: {close_status_code}, Message: {close_msg}")

    def on_open(ws_app):
        print("🟢 WebSocket Connected!")
        subscribe_msg = {'type': 'subscribe', 'symbol': 'AAPL'}
        ws_app.send(json.dumps(subscribe_msg))
        print(f"📡 Subscribed to: {subscribe_msg}")

    try:
        ws_app = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        
        # Run in a separate thread with timeout
        ws_thread = threading.Thread(target=ws_app.run_forever, kwargs={
            'ping_interval': 15,
            'ping_timeout': 10
        })
        ws_thread.daemon = True
        ws_thread.start()
        
        # Keep main thread alive for demo period
        time.sleep(20)
        
        # Cleanup
        if ws_app:
            ws_app.close()
            print("WebSocket connection closed cleanly")
            
    except Exception as e:
        print(f"WebSocket setup error: {e}")
        if ws_app:
            ws_app.close()

# --- Finnhub Fundamental Data (REST API) Example ---
# This demonstrates how to make a single API call to get fundamental data.
def get_finnhub_fundamental():
    print("\n--- Fetching Finnhub Fundamental Data (REST API) ---")
    finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)

    # Get company basic financials for Apple (AAPL).
    # This is a REST API call and consumes your daily REST API limits.
    try:
        financials = finnhub_client.company_basic_financials("AAPL", "all")
        print("\nFetched Finnhub Basic Financials for AAPL (Keys only, data can be large):")
        # Print only the top-level keys as the full data can be very verbose.
        if financials and 'metric' in financials:
            print(financials['metric'].keys())
        else:
            print("No basic financials found for AAPL or unexpected format from Finnhub.")

        # Prepare data for MinIO. Store as JSON.
        if financials:
            json_bytes = json.dumps(financials).encode('utf-8')
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            object_name = f"finnhub_fundamentals/AAPL_financials_{timestamp_str}.json"

            # Save to the 'raw-tick-data' bucket in MinIO.
            save_to_minio("raw-tick-data", object_name, json_bytes, 'application/json')
        else:
            print("No fundamental data to save to MinIO.")

    except Exception as e:
        print(f"Error fetching fundamental data from Finnhub: {e}")
        if "Limit exceeded" in str(e) or "invalid token" in str(e):
            print("ACTION REQUIRED: Check your Finnhub API key and daily REST API limits. You might have hit them.")
        else:
            print(f"An unexpected error occurred: {e}")

# --- Main Execution Block ---
# This is where the script starts running.
if __name__ == "__main__":
    print("🚀 Starting Finnhub integration...")
    
    run_finnhub_websocket()
    
    print("\n📊 Running Fundamental Data example...")
    get_finnhub_fundamental()
    
    print("\n✨ Finnhub integration script finished.")