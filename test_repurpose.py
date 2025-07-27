#!/usr/bin/env python3
"""
Test script to copy just AAPL data as a proof of concept
"""

import boto3
import os
from botocore.client import Config

# MinIO Configuration (same as in main_data_collector.py)
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", 'http://159.223.139.171:9000')
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", 'minioadmin')
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", 'minioadmin')
RAW_DATA_BUCKET = 'market-data'

# Initialize MinIO client
s3_client = boto3.client(
    's3',
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    config=Config(signature_version='s3v4'),
    region_name='us-east-1'
)

print("Copying AAPL historical data as test...")

try:
    # List first 10 Twelve Data historical files for AAPL
    response = s3_client.list_objects_v2(
        Bucket=RAW_DATA_BUCKET,
        Prefix='twelvedata_historical/AAPL/',
        MaxKeys=10
    )
    
    if 'Contents' not in response:
        print("No Twelve Data historical files found for AAPL")
        exit(1)
    
    files_copied = 0
    for obj in response['Contents']:
        source_key = obj['Key']
        
        # Skip if not a parquet file
        if not source_key.endswith('.parquet'):
            continue
        
        # Extract date from filename (e.g., raw_2020-07-27.parquet)
        filename = source_key.split('/')[-1]
        if not filename.startswith('raw_'):
            continue
        
        date_str = filename.replace('raw_', '').replace('.parquet', '')
        
        # Create corresponding Finnhub historical path
        try:
            year, month, day = date_str.split('-')
            finnhub_key = f'finnhub_historical/AAPL/{year}/{month}/{day}/candles_{date_str.replace("-", "")}.parquet'
            
            # Copy the object
            copy_source = {'Bucket': RAW_DATA_BUCKET, 'Key': source_key}
            s3_client.copy_object(
                CopySource=copy_source,
                Bucket=RAW_DATA_BUCKET,
                Key=finnhub_key
            )
            files_copied += 1
            print(f"Copied {source_key} -> {finnhub_key}")
        
        except Exception as date_error:
            print(f"Error processing date {date_str}: {date_error}")
            continue
    
    print(f"Successfully copied {files_copied} test files for AAPL")
    
except Exception as e:
    print(f"Error: {e}")
