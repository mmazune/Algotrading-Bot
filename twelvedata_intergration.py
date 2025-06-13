import sys
from importlib import util

# Check if required packages are available
required_packages = {
    'twelvedata': 'twelvedata',
    'boto3': 'boto3',
    'pyarrow': 'pyarrow'
}

for package, import_name in required_packages.items():
    if util.find_spec(import_name) is None:
        print(f"ERROR: {package} is not installed. Please run: pip install {package}")
        sys.exit(1)

# If all packages are available, import them
import time
import json
import pandas as pd
from datetime import datetime
import os # IMPORTANT: os module is needed to access environment variables
import requests

# For MinIO integration
import boto3
from botocore.client import Config
import io

# Ensure twelvedata is properly imported
try:
    from twelvedata.client import TDClient
except ImportError:
    print("Error: TDClient could not be imported. Please reinstall the package:")
    print("pip uninstall twelvedata")
    print("pip install --no-cache-dir twelvedata")
    exit(1)

# --- Your API Keys & MinIO Details ---
# Retrieve API keys and MinIO credentials from environment variables
# This is a much more secure practice than hardcoding.
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", 'http://localhost:9000') # Default to localhost if not set
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")

# Basic validation for essential keys
if not TWELVEDATA_API_KEY:
    print("Error: TWELVEDATA_API_KEY environment variable not set.")
    sys.exit(1)
if not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
    print("Error: MINIO_ACCESS_KEY or MINIO_SECRET_KEY environment variables not set.")
    sys.exit(1)


# Initialize MinIO S3 client
try:
    s3_client = boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1' # A placeholder region, not used by MinIO but needed by boto3
    )
    print("MinIO S3 client initialized for data storage.")
except Exception as e:
    print(f"Error initializing MinIO S3 client: {e}. Ensure MinIO Docker container is running and accessible.")
    s3_client = None # Set to None if initialization fails, to prevent further errors

# --- Helper Function to Save Data to MinIO ---
# This function is used by both WebSocket and REST API parts to store data.
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

# --- Twelve Data Real-time (WebSocket) Example ---
# This demonstrates how to subscribe to a continuous stream of real-time data.
# This function MUST be 'async def' because the twelvedata WebSocket client is asynchronous.
def run_twelvedata_websocket():
    print("\n--- Initiating Twelve Data WebSocket Stream (Real-time) ---")
    print("WebSocket functionality is currently disabled pending fixes.")
    print("Historical data API is working correctly.")
    return

# --- Twelve Data Historical (REST API) Example ---
# This demonstrates how to make a single API call to get a batch of historical data.
def get_twelvedata_historical():
    print("\n--- Fetching Twelve Data Historical Data (REST API) ---")

    symbol = "AAPL"
    interval = "1min"
    outputsize = 50

    # --- DIAGNOSTIC STEP: Make a direct API call using 'requests' ---
    # This bypasses the twelvedata client library and shows the raw response.
    print(f"--- DIAGNOSTIC: Making direct API call for {symbol} ({interval}, {outputsize} bars) ---")
    direct_api_url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={TWELVEDATA_API_KEY}"

    try:
        response = requests.get(direct_api_url)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        raw_json_data = response.json()

        print(f"--- DIAGNOSTIC: RAW JSON Response from Twelve Data API ---")
        print(json.dumps(raw_json_data, indent=2)) # Print formatted JSON
        print("----------------------------------------------------------")

        # Now, try with the twelvedata client library as originally intended
        td = TDClient(apikey=TWELVEDATA_API_KEY)
        raw_response_obj = td.time_series(
            symbol=symbol,
            interval=interval,
            outputsize=outputsize
        )

        ts_dataframe = None

        # --- IMPORTANT: Check the response type for API errors FIRST (from the client library) ---
        if isinstance(raw_response_obj, dict) and raw_response_obj.get('status') == 'error':
            error_code = raw_response_obj.get('code')
            error_message = raw_response_obj.get('message')
            print(f"Twelve Data client library returned an error for historical data: Code={error_code}, Message={error_message}")
            if "invalid API key" in error_message or "Daily limit reached" in error_message or "quota" in error_message:
                print("ACTION REQUIRED: Your Twelve Data API key for REST API might be invalid or you've hit your daily/minute limits.")
            return # Exit the function, as no valid DataFrame can be created

        # Convert the raw JSON response to DataFrame directly
        if raw_json_data.get('status') == 'ok' and 'values' in raw_json_data:
            ts_dataframe = pd.DataFrame(raw_json_data['values'])
            ts_dataframe['datetime'] = pd.to_datetime(ts_dataframe['datetime'])
            ts_dataframe.set_index('datetime', inplace=True)

            # Convert columns to numeric
            for col in ['open', 'high', 'low', 'close', 'volume']:
                ts_dataframe[col] = pd.to_numeric(ts_dataframe[col])

            print(f"\nFetched Historical Data for AAPL (first 5 rows of {len(ts_dataframe)}):")
            print(ts_dataframe.head())

            # Prepare data for MinIO. Parquet is highly efficient for tabular dataframes.
            try:
                parquet_buffer = io.BytesIO()
                ts_dataframe.to_parquet(parquet_buffer, index=True)
                parquet_bytes = parquet_buffer.getvalue()

                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                start_date_str = ts_dataframe.index.min().strftime('%Y%m%d') if isinstance(ts_dataframe.index, pd.DatetimeIndex) and not ts_dataframe.empty else datetime.now().strftime('%Y%m%d')
                end_date_str = ts_dataframe.index.max().strftime('%Y%m%d') if isinstance(ts_dataframe.index, pd.DatetimeIndex) and not ts_dataframe.empty else datetime.now().strftime('%Y%m%d')

                object_name = f"twelvedata_historical/{start_date_str}_{end_date_str}/{symbol}_1min_{timestamp_str}.parquet"

                # IMPORTANT: Specify your MinIO bucket name here
                save_to_minio("historical-ohlcv", object_name, parquet_bytes, 'application/octet-stream')
            except ImportError:
                print("WARNING: 'pyarrow' library not found. Cannot save historical data to Parquet. Install with 'pip install pyarrow'.")
            except Exception as e:
                print(f"Error preparing or saving Parquet data to MinIO: {e}")

        else:
            print(f"Error in API response: {raw_json_data.get('message', 'Unknown error')}")

    except requests.exceptions.RequestException as e:
        print(f"Error making direct API request to Twelve Data: {e}")
        print("This could be a network issue, firewall, or Twelve Data server problem.")
    except json.JSONDecodeError:
        print(f"Error decoding JSON from direct API response. Raw response was: {response.text}")
    except Exception as e:
        print(f"An unexpected error occurred during historical data fetch: {e}")
        print(f"Please ensure your internet connection is stable and Twelve Data service is available.")

# --- Main Execution Block ---
if __name__ == "__main__":
    try:
        import pyarrow.parquet
        print("PyArrow is installed, Parquet saving will work.")
    except ImportError:
        print("WARNING: PyArrow is NOT installed. Saving historical data to Parquet will FAIL. Please run 'pip install pyarrow'.")

    print("Running Twelve Data WebSocket example...")
    run_twelvedata_websocket()

    print("\nRunning Twelve Data Historical API example...")
    get_twelvedata_historical()

    print("\nTwelve Data integration script finished.")
