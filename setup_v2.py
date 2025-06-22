import boto3
import sys
from apis.twelve_data import TwelveDataAPI
from config import MINIO_CONFIG, BUCKET_NAME, TWELVE_DATA_API_KEY

def init_minio():
    print("\nChecking MinIO setup...")
    try:
        client = boto3.client(
            's3',
            endpoint_url=f"http://{MINIO_CONFIG['endpoint']}",
            aws_access_key_id=MINIO_CONFIG['access_key'],
            aws_secret_access_key=MINIO_CONFIG['secret_key']
        )
        
        # Check if bucket exists
        try:
            client.head_bucket(Bucket=BUCKET_NAME)
            print(f"✓ Found existing bucket: {BUCKET_NAME}")
        except:
            client.create_bucket(Bucket=BUCKET_NAME)
            print(f"✓ Created new bucket: {BUCKET_NAME}")
        return True
        
    except Exception as e:
        print(f"✗ MinIO setup failed: {str(e)}")
        return False

def check_twelve_data():
    print("\nChecking Twelve Data API...")
    try:
        api = TwelveDataAPI()
        resp = api.test_connection()
        
        if isinstance(resp, dict) and resp.get('code') == 401:
            print(f"✗ API key validation failed: {resp.get('message', 'Unknown error')}")
            return False
            
        print("✓ Twelve Data API connection successful")
        return True
        
    except Exception as e:
        print(f"✗ Twelve Data API check failed: {str(e)}")
        return False

def run_setup():
    print("🔧 Starting Algotrading Bot Setup")
    
    # Run checks
    minio_ok = init_minio()
    twelve_data_ok = check_twelve_data()
    
    # Final status
    if minio_ok and twelve_data_ok:
        print("\n✨ Setup completed successfully!")
        sys.exit(0)
    else:
        print("\n⚠️ Setup failed - Please check the errors above")
        sys.exit(1)

if __name__ == "__main__":
    run_setup()
