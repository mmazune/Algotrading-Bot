import os
import sys
import json
import time
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import boto3
from botocore.client import Config
from datetime import datetime
from io import BytesIO
import requests # For Twelve Data direct API calls if client library isn't used
import finnhub # For Finnhub API calls
from finnhub_integration import FINNHUB_API_KEY # Import the API key from finnhub_integration.py

# --- 1. Load API Keys and MinIO Details from Environment Variables ---
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", 'http://localhost:9000') # Default to localhost
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")

# Basic validation for essential keys
if not TWELVEDATA_API_KEY:
    print("Error: TWELVEDATA_API_KEY environment variable not set. Please set it.")
    sys.exit(1)
if not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
    print("Error: MINIO_ACCESS_KEY or MINIO_SECRET_KEY environment variables not set. Please set them.")
    sys.exit(1)

print("All API Keys and MinIO credentials loaded successfully.")

# Initialize Finnhub client
finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
twelvedata_base_url = "https://api.twelvedata.com"

# Initialize MinIO S3 client
try:
    s3_client = boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1' # Placeholder region
    )
    # Verify MinIO connection by listing buckets or creating one if needed
    try:
        s3_client.list_buckets()
        print(f"MinIO S3 client initialized and connected to endpoint: {MINIO_ENDPOINT}")
    except Exception as e:
        print(f"Warning: MinIO S3 client initialized but failed to list buckets. Check connection or credentials. Error: {e}")

except Exception as e:
    print(f"Error initializing MinIO S3 client: {e}. Ensure MinIO Docker container is running and accessible.")
    s3_client = None # Set to None if initialization fails

# --- Helper Function to Save Data to MinIO ---
def save_to_minio(bucket_name, object_name, data_bytes, content_type='application/octet-stream'):
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
            print(f"ACTION REQUIRED: Bucket '{bucket_name}' does not exist. Please create it in the MinIO console ({MINIO_ENDPOINT.replace('9000', '9001')}).")
        else:
            print(f"An unexpected S3 client error occurred: {e}")
    except Exception as e:
        print(f"General error saving {object_name} to MinIO: {e}")

# --- Function to Read Symbols from File ---
def get_symbols(filename="symbols.txt"):
    try:
        with open(filename, 'r') as f:
            symbols = [line.strip().upper() for line in f if line.strip()]
        print(f"Loaded {len(symbols)} symbols from {filename}")
        return symbols
    except FileNotFoundError:
        print(f"Error: {filename} not found. Please create it in the same directory as the script, with one symbol per line.")
        return []

# --- Main Data Ingestion Logic ---
def fetch_and_store_data():
    symbols_to_fetch = get_symbols()
    if not symbols_to_fetch:
        print("No symbols to fetch. Exiting.")
        return

    for symbol in symbols_to_fetch:
        print(f"\n--- Processing data for {symbol} ---")
        current_datetime = datetime.now()
        date_path = current_datetime.strftime("%Y/%m/%d") # For S3 partitioning

        # --- Fetch and Store Finnhub Quote ---
        try:
            print(f"Fetching Finnhub quote for {symbol}...")
            quote_data = finnhub_client.quote(symbol)
            if quote_data and quote_data.get('c') is not None: # Check if current price exists
                df_quote = pd.DataFrame([quote_data])
                df_quote['symbol'] = symbol
                df_quote['fetch_timestamp'] = current_datetime

                # Convert to Parquet Bytes
                parquet_buffer = BytesIO()
                table = pa.Table.from_pandas(df_quote)
                pq.write_table(table, parquet_buffer)
                parquet_bytes = parquet_buffer.getvalue()

                object_name = f"finnhub_quotes/{symbol}/{date_path}/{current_datetime.strftime('%H%M%S')}_quote.parquet"
                save_to_minio("raw-financial-data", object_name, parquet_bytes, 'application/octet-stream')
            else:
                print(f"No valid Finnhub quote data for {symbol}.")
        except Exception as e:
            print(f"Error fetching/storing Finnhub quote for {symbol}: {e}")
            if "Limit exceeded" in str(e) or "invalid token" in str(e):
                print("ACTION REQUIRED: Check your Finnhub API key and daily REST API limits. You might have them.")

        time.sleep(1) # Small delay to respect Finnhub rate limits

        # --- Fetch and Store Twelve Data Historical ---
        try:
            print(f"Fetching Twelve Data historical (1day) for {symbol}...")
            td_timeseries_url = (
                f"{twelvedata_base_url}/time_series?"
                f"symbol={symbol}&interval=1day&outputsize=30&apikey={TWELVEDATA_API_KEY}" # Fetch last 30 days
            )
            td_timeseries_response = requests.get(td_timeseries_url)
            td_timeseries_response.raise_for_status()
            td_timeseries_data = td_timeseries_response.json()

            if td_timeseries_data.get('status') == 'ok' and 'values' in td_timeseries_data and td_timeseries_data['values']:
                df_ts = pd.DataFrame(td_timeseries_data['values'])
                df_ts['symbol'] = symbol
                df_ts['fetch_timestamp'] = current_datetime
                df_ts['datetime'] = pd.to_datetime(df_ts['datetime']) # Convert 'datetime' column to datetime objects

                # Convert columns to numeric, coercing errors
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df_ts[col] = pd.to_numeric(df_ts[col], errors='coerce')


                # Convert to Parquet Bytes
                parquet_buffer = BytesIO()
                table = pa.Table.from_pandas(df_ts)
                pq.write_table(table, parquet_buffer)
                parquet_bytes = parquet_buffer.getvalue()

                object_name = f"twelvedata_historical/{symbol}/{date_path}/{current_datetime.strftime('%H%M%S')}_daily.parquet"
                save_to_minio("raw-financial-data", object_name, parquet_bytes, 'application/octet-stream')
            else:
                print(f"No valid Twelve Data historical data for {symbol}. Response: {td_timeseries_data}")

        except requests.exceptions.RequestException as e:
            print(f"Error fetching Twelve Data historical for {symbol}: {e}")
            if hasattr(e, 'response') and e.response.status_code == 429:
                print(f"Hit Twelve Data rate limit for {symbol}. Waiting for 60 seconds before next request.")
                time.sleep(60) # Wait longer if rate limited
        except Exception as e:
            print(f"An unexpected error occurred with Twelve Data processing/upload for {symbol}: {e}")

        time.sleep(2) # Longer delay between processing each symbol to avoid hitting limits across APIs

    print("\nData collection for all symbols complete.")

# --- Main Execution Block ---
if __name__ == "__main__":
    print("🚀 Starting centralized data collection...")
    # Ensure pyarrow is installed for Parquet saving
    try:
        import pyarrow.parquet
        print("PyArrow is installed, Parquet saving will work.")
    except ImportError:
        print("WARNING: PyArrow is NOT installed. Saving data to Parquet will FAIL. Please run 'pip install pyarrow'.")
        sys.exit(1) # Exit if pyarrow is missing, as it's critical for storage

    fetch_and_store_data()
    print("\n✨ Centralized data collection script finished.")
