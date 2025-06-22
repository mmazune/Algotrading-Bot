import os
import sys
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
from io import BytesIO
from config import RAW_DATA_BUCKET, PROCESSED_DATA_BUCKET
from api_rotation import twelvedata_manager, finnhub_rest_manager

# --- 1. Load MinIO Details from Environment Variables ---
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", 'http://localhost:9000')
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")

# Define bucket names (using config.py values now)
RAW_BUCKET_NAME = 'raw-financial-data'  # Hardcoded to match main_data_collector.py
PROCESSED_BUCKET_NAME = PROCESSED_DATA_BUCKET # From config.py

# Basic validation for essential MinIO keys
if not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
    print("Error: MINIO_ACCESS_KEY or MINIO_SECRET_KEY environment variables not set. Please set them.")
    sys.exit(1)

# Initialize MinIO S3 client
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
    # Verify MinIO connection and create buckets if needed
    try:
        s3_client.list_buckets()
        print(f"MinIO S3 client initialized and connected to endpoint: {MINIO_ENDPOINT}")
        
        for bucket_name in [RAW_BUCKET_NAME, PROCESSED_BUCKET_NAME]:
            try:
                s3_client.head_bucket(Bucket=bucket_name)
                print(f"Bucket '{bucket_name}' already exists.")
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    print(f"Bucket '{bucket_name}' does not exist. Creating now...")
                    s3_client.create_bucket(Bucket=bucket_name)
                    print(f"Bucket '{bucket_name}' created successfully.")
                else:
                    raise
    except Exception as e:
        print(f"Warning: MinIO S3 client initialized but failed to list/verify buckets. Check connection or credentials. Error: {e}")
        s3_client = None

except Exception as e:
    print(f"Error initializing MinIO S3 client: {e}. Ensure MinIO Docker container is running and accessible.")
    s3_client = None

# --- Helper Function to Save Data to MinIO ---
def save_dataframe_to_minio_parquet(df, bucket_name, object_name):
    if not s3_client:
        print(f"MinIO client not available, skipping save of {object_name}.")
        return

    try:
        df_to_save = df.reset_index() if isinstance(df.index, pd.DatetimeIndex) else df

        parquet_buffer = BytesIO()
        table = pa.Table.from_pandas(df_to_save)
        pq.write_table(table, parquet_buffer)
        parquet_bytes = parquet_buffer.getvalue()

        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=parquet_bytes,
            ContentType='application/octet-stream'
        )
        print(f"Successfully saved processed data to s3://{bucket_name}/{object_name}")
    except ClientError as e:
        print(f"MinIO Client Error for {object_name}: {e}")
        if e.response['Error']['Code'] == 'NoSuchBucket':
            print(f"ACTION REQUIRED: Bucket '{bucket_name}' does not exist. Please create it in the MinIO console ({MINIO_ENDPOINT.replace('9000', '9001')}).")
        else:
            print(f"An unexpected S3 client error occurred: {e}")
    except Exception as e:
        print(f"General error saving {object_name} to MinIO: {e}")

# --- Helper Function to List Objects in MinIO ---
def list_objects(minio_client, bucket, prefix):
    """Helper function to list objects in MinIO bucket with given prefix"""
    try:
        objects = minio_client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix
        )
        return list(objects.get('Contents', []))
    except Exception as e:
        print(f"Error listing objects in s3://{bucket}/{prefix}: {str(e)}")
        return []

# --- Helper Function to Read Symbols from File ---
def get_symbols(filename="symbols.txt"):
    try:
        with open(filename, 'r') as f:
            symbols = [line.strip().upper() for line in f if line.strip()]
        print(f"Loaded {len(symbols)} symbols from {filename}")
        return symbols
    except FileNotFoundError:
        print(f"Error: {filename} not found. Please create it with stock symbols.")
        return []

# --- Function to Read Parquet Data from MinIO for a Specific Prefix (now for multiple days) ---
def read_all_parquet_from_minio_prefix(bucket_name, base_prefix):
    if not s3_client:
        print("MinIO client not available, cannot read data.")
        return pd.DataFrame()

    all_dataframes = []
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        # List objects within the base_prefix to find all daily parquet files
        pages = paginator.paginate(Bucket=bucket_name, Prefix=base_prefix)

        for page in pages:
            if "Contents" in page:
                for obj in page['Contents']:
                    if obj['Key'].endswith('.parquet'):
                        try:
                            response = s3_client.get_object(Bucket=bucket_name, Key=obj['Key'])
                            parquet_data = response['Body'].read()
                            df = pd.read_parquet(BytesIO(parquet_data))
                            all_dataframes.append(df)
                        except Exception as e:
                            print(f"Error reading {obj['Key']} from MinIO: {e}")
        if all_dataframes:
            return pd.concat(all_dataframes, ignore_index=True)
        else:
            return pd.DataFrame()
    except ClientError as e:
        print(f"Error listing objects in s3://{bucket_name}/{base_prefix}: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"General error reading from MinIO: {e}")
        return pd.DataFrame()


# --- Transformation Function for Finnhub Quotes ---
def process_finnhub_quotes(symbol):
    print(f"  Processing Finnhub quotes for {symbol}...")
    try:
        # Instead of current date, process all raw data for this symbol
        base_prefix = f"finnhub_quotes/{symbol}/"
        raw_df = read_all_parquet_from_minio_prefix(RAW_BUCKET_NAME, base_prefix)

        if raw_df.empty:
            print(f"    No raw Finnhub quote data found for {symbol}. Skipping.")
            return None

        # Ensure 'timestamp' column is datetime and set as index
        if 'fetch_timestamp' in raw_df.columns: # Use fetch_timestamp as the primary time index for quotes
            raw_df['fetch_timestamp'] = pd.to_datetime(raw_df['fetch_timestamp'], utc=True, errors='coerce')
            raw_df['fetch_timestamp'] = raw_df['fetch_timestamp'].dt.tz_localize(None)
            raw_df.set_index('fetch_timestamp', inplace=True)
            raw_df.sort_index(inplace=True)
        else:
            print(f"Warning: 'fetch_timestamp' not found in raw Finnhub data for {symbol}.")
            return None # Cannot process without a proper timestamp

        df = raw_df.copy()
        
        numeric_cols = ['c', 'h', 'l', 'o', 'pc']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df.dropna(subset=['c'], inplace=True)

        if 'h' in df.columns and 'l' in df.columns:
            df['spread'] = df['h'] - df['l']
        
        # Select and rename columns for processed data consistency
        processed_df = df[['c', 'h', 'l', 'o', 'pc', 'spread', 'symbol']].copy() # Removed fetch_timestamp as it's the index
        processed_df.rename(columns={
            'c': 'close',
            'h': 'high',
            'l': 'low',
            'o': 'open',
            'pc': 'prev_close'
        }, inplace=True)
        
        # Determine the output path for processed data (saved as a single file per symbol)
        processed_object_name = f"finnhub_quotes/{symbol}/processed_quotes_all.parquet"
        
        save_dataframe_to_minio_parquet(processed_df, PROCESSED_BUCKET_NAME, processed_object_name)
        print(f"    Processed Finnhub quotes for {symbol} saved.")
        return processed_df
    except Exception as e:
        print(f"Error processing Finnhub quotes for {symbol}: {e}")
        return None

# --- Transformation Function for Twelve Data Historical ---
def process_twelvedata_historical(symbol):
    print(f"  Processing Twelve Data historical for {symbol}...")
    try:
        # Instead of current date, process all raw data for this symbol
        base_prefix = f"twelvedata_historical/{symbol}/"
        raw_df = read_all_parquet_from_minio_prefix(RAW_BUCKET_NAME, base_prefix)

        if raw_df.empty:
            print(f"    No raw Twelve Data historical data found for {symbol}. Skipping.")
            return None

        # Ensure 'datetime' column is datetime and set as index
        if 'datetime' in raw_df.columns:
            raw_df['datetime'] = pd.to_datetime(raw_df['datetime'], utc=True, errors='coerce')
            raw_df['datetime'] = raw_df['datetime'].dt.tz_localize(None) # Make it naive
            raw_df.set_index('datetime', inplace=True)
            raw_df.sort_index(inplace=True)
        else:
            print(f"Warning: 'datetime' not found in raw Twelve Data historical data for {symbol}.")
            return None # Cannot process without a proper datetime

        df = raw_df.copy()
        
        ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in ohlcv_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        df.dropna(subset=['close'], inplace=True)

        df['daily_return'] = df['close'].pct_change()
        
        # Select columns for processed data consistency
        processed_df = df[['open', 'high', 'low', 'close', 'volume', 'daily_return', 'symbol']].copy() # Removed fetch_timestamp as it's no longer the relevant index for this data type

        # Determine the output path for processed data (saved as a single file per symbol)
        processed_object_name = f"twelvedata_historical/{symbol}/processed_daily_data_all.parquet"

        save_dataframe_to_minio_parquet(processed_df, PROCESSED_BUCKET_NAME, processed_object_name)
        print(f"    Processed Twelve Data historical for {symbol} saved.")
        return processed_df
    except Exception as e:
        print(f"Error processing Twelve Data historical for {symbol}: {e}")
        return None

# --- Main Data Transformation Orchestration ---
def main():
    print("\nStarting data transformation and processing")

    if not s3_client:
        print("MinIO client not initialized. Cannot proceed with transformation. Exiting.")
        sys.exit(1)

    try:
        import pyarrow.parquet
        print("PyArrow is installed, Parquet operations will work.")
    except ImportError:
        print("WARNING: PyArrow is NOT installed. Parquet operations will FAIL. Please run 'pip install pyarrow'.")
        sys.exit(1)

    symbols = get_symbols()
    if not symbols:
        print("No symbols to process. Exiting.")
        return

    for symbol in symbols:
        # Process both data types for each symbol
        process_finnhub_quotes(symbol)
        process_twelvedata_historical(symbol)
    
    print("\nData transformation process completed")

# --- Entry Point ---
if __name__ == "__main__":
    main()

