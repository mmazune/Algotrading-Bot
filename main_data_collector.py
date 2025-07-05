import os
import sys
import json
import time
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from datetime import datetime
from io import BytesIO
# Using specific bucket names from config.py
from config import RAW_DATA_BUCKET, PROCESSED_DATA_BUCKET # Ensure these are defined in your config.py
import requests # For Twelve Data direct API calls
import finnhub # For Finnhub API calls

# Import the key managers for API rotation
from api_rotation import twelvedata_manager, finnhub_rest_manager

# --- 1. Load API Keys and MinIO Details from Environment Variables ---
# These variables should be set in your system's environment or in your run_pipeline.bat
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", 'http://localhost:9000')
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")

# Basic validation for essential keys
if not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
    print("Error: MINIO_ACCESS_KEY or MINIO_SECRET_KEY environment variables not set. Please set them.")
    sys.exit(1)

# Finnhub API key and Twelve Data API key are now managed by api_rotation,
# so direct environment variable check for them is not strictly necessary here,
# but the api_rotation module expects them to be available via its config.py.

print("All MinIO credentials loaded successfully.")

# Twelve Data base URL
twelvedata_base_url = "https://api.twelvedata.com"

# Initialize MinIO S3 client globally for reuse
s3_client = None
try:
    s3_client = boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1' # Placeholder region
    )
    # Verify MinIO connection and ensure buckets exist (improved check)
    try:
        s3_client.list_buckets()
        print(f"MinIO S3 client initialized and connected to endpoint: {MINIO_ENDPOINT}")
        
        # Check and create necessary buckets
        for bucket_name in [RAW_DATA_BUCKET, PROCESSED_DATA_BUCKET]: # Use the imported bucket names
            try:
                s3_client.head_bucket(Bucket=bucket_name)
                print(f"Bucket '{bucket_name}' already exists.")
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    print(f"Bucket '{bucket_name}' does not exist. Creating now...")
                    s3_client.create_bucket(Bucket=bucket_name)
                    print(f"Bucket '{bucket_name}' created successfully.")
                else:
                    raise # Re-raise other ClientErrors
    except Exception as e:
        print(f"Warning: MinIO S3 client initialized but failed to list/verify buckets. Check connection or credentials. Error: {e}")
        s3_client = None # Set to None if connection verification fails

except Exception as e:
    print(f"Error initializing MinIO S3 client: {e}. Ensure MinIO Docker container is running and accessible.")
    s3_client = None


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
    except ClientError as e:
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
    
    # Check PyArrow installation once
    try:
        import pyarrow.parquet
        print("PyArrow is installed, Parquet saving will work.")
    except ImportError:
        print("WARNING: PyArrow is NOT installed. Saving data to Parquet will FAIL. Please run 'pip install pyarrow'.")
        sys.exit(1)


    for symbol in symbols_to_fetch:
        print(f"\n--- Processing data for {symbol} ---")
        current_datetime = datetime.now()
        # Use ISO format for timestamp to avoid potential issues with `df.to_parquet`
        # and ensure uniqueness for each API call within the same day/minute.
        timestamp_for_filename = current_datetime.strftime('%H%M%S_%f')[:-3] # HHMMSS_milliseconds
        date_path_for_storage = current_datetime.strftime("%Y/%m/%d") # For S3 partitioning

        # --- Fetch and Store Finnhub Quote ---
        try:
            print(f"Fetching Finnhub quote for {symbol}...")
            # Use the finnhub_rest_manager to get an API key
            finnhub_client_with_key = finnhub.Client(api_key=finnhub_rest_manager.get_key("rest"))
            quote_data = finnhub_client_with_key.quote(symbol)
            
            if quote_data and quote_data.get('c') is not None: # Check if current price exists
                df_quote = pd.DataFrame([quote_data])
                df_quote['symbol'] = symbol
                df_quote['fetch_timestamp'] = current_datetime # Keep as datetime object for Pandas

                # Convert to Parquet Bytes
                parquet_buffer = BytesIO()
                table = pa.Table.from_pandas(df_quote)
                pq.write_table(table, parquet_buffer)
                parquet_bytes = parquet_buffer.getvalue()

                # Store in MinIO using RAW_DATA_BUCKET
                object_name = f"finnhub_quotes/{symbol}/{date_path_for_storage}/quote_{timestamp_for_filename}.parquet"
                save_to_minio(RAW_DATA_BUCKET, object_name, parquet_bytes, 'application/octet-stream')
            else:
                print(f"No valid Finnhub quote data for {symbol}.")
        except Exception as e:
            print(f"Error fetching/storing Finnhub quote for {symbol}: {e}")
            # Specific error handling for API limits/invalid tokens from finnhub_rest_manager or direct API
            if "Limit exceeded" in str(e) or "invalid token" in str(e) or "429" in str(e):
                print("ACTION REQUIRED: Check your Finnhub API key and daily REST API limits. You might have hit them.")
            
        time.sleep(1) # Small delay to respect Finnhub rate limits

        # --- Fetch and Store Twelve Data Historical ---
        try:
            print(f"Fetching Twelve Data historical (1day) for {symbol}...")
            td_timeseries_url = (
                f"{twelvedata_base_url}/time_series?"
                f"symbol={symbol}&interval=1day&outputsize=730&apikey={twelvedata_manager.get_key()}"
            )
            td_timeseries_response = requests.get(td_timeseries_url)
            td_timeseries_response.raise_for_status()
            td_timeseries_data = td_timeseries_response.json()

            if td_timeseries_data.get('status') == 'ok' and 'values' in td_timeseries_data and td_timeseries_data['values']:
                df_ts = pd.DataFrame(td_timeseries_data['values'])
                df_ts['symbol'] = symbol
                df_ts['fetch_timestamp'] = current_datetime
                df_ts['datetime'] = pd.to_datetime(df_ts['datetime'], errors='coerce')
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df_ts[col] = pd.to_numeric(df_ts[col], errors='coerce')

                # --- Save each day's row as a separate raw parquet file in market-data bucket ---
                for idx, row in df_ts.iterrows():
                    single_row_df = pd.DataFrame([row])
                    parquet_buffer = BytesIO()
                    table = pa.Table.from_pandas(single_row_df)
                    pq.write_table(table, parquet_buffer)
                    parquet_bytes = parquet_buffer.getvalue()
                    # Use the date from the row for the filename
                    row_date = row['datetime'] if pd.notnull(row['datetime']) else current_datetime
                    date_str = pd.to_datetime(row_date).strftime('%Y-%m-%d')
                    object_name = f"twelvedata_historical/{symbol}/raw_{date_str}.parquet"
                    save_to_minio(RAW_DATA_BUCKET, object_name, parquet_bytes, 'application/octet-stream')
                print(f"Saved {len(df_ts)} raw daily parquet files for {symbol} in {RAW_DATA_BUCKET} bucket.")
            else:
                print(f"No valid Twelve Data historical data for {symbol}. Response: {td_timeseries_data}")
        except requests.exceptions.RequestException as e:
            print(f"Error fetching Twelve Data historical for {symbol}: {e}")
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 429:
                print(f"Hit Twelve Data rate limit for {symbol}. Waiting for 60 seconds before next request.")
                time.sleep(60)
            else:
                print(f"Non-recoverable error fetching Twelve Data for {symbol}: {e}")
        except Exception as e:
            print(f"General error fetching or storing Twelve Data for {symbol}: {e}")
        time.sleep(1) # Small delay to respect API rate limits

    print("Data fetching and storage complete.")

# --- Entry Point for Script Execution ---
if __name__ == "__main__":
    fetch_and_store_data()