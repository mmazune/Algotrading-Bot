import boto3
from apis.twelve_data import TwelveDataAPI
from config import MINIO_CONFIG, BUCKET_NAME

def init():
    print("🔧 Setting up Algotrading Bot...")
    success = True
    
    # Setup MinIO
    try:
        minio_client = boto3.client(
            's3',
            endpoint_url=f"http://{MINIO_CONFIG['endpoint']}",
            aws_access_key_id=MINIO_CONFIG['access_key'],
            aws_secret_access_key=MINIO_CONFIG['secret_key']
        )
        minio_client.head_bucket(Bucket=BUCKET_NAME)
        print(f"✓ Bucket '{BUCKET_NAME}' exists")
    except:
        try:
            minio_client.create_bucket(Bucket=BUCKET_NAME)
            print(f"✓ Created bucket '{BUCKET_NAME}'")
        except Exception as e:
            print(f"✗ MinIO setup failed: {str(e)}")
            success = False
    
    # Verify Twelve Data API
    try:
        api = TwelveDataAPI()
        response = api.test_connection()
        if 'code' in response and response['code'] == 401:
            print(f"✗ Twelve Data API key invalid")
            success = False
        else:
            print("✓ Twelve Data API key verified")
    except Exception as e:
        print(f"✗ Twelve Data API verification failed: {str(e)}")
        success = False
    
    # Print final status
    if success:
        print("\n✨ Setup completed successfully!")
    else:
        print("\n⚠️ Setup completed with errors. Please fix the issues above.")

if __name__ == "__main__":
    init()
