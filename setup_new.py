import boto3
from apis.twelve_data import TwelveDataAPI
from config import MINIO_CONFIG, BUCKET_NAME

class Setup:
    def __init__(self):
        self.minio_success = False
        self.twelve_data_success = False

    def setup_minio(self):
        try:
            minio_client = boto3.client(
                's3',
                endpoint_url=f"http://{MINIO_CONFIG['endpoint']}",
                aws_access_key_id=MINIO_CONFIG['access_key'],
                aws_secret_access_key=MINIO_CONFIG['secret_key']
            )
            try:
                minio_client.head_bucket(Bucket=BUCKET_NAME)
                print(f"✓ Bucket '{BUCKET_NAME}' exists")
            except:
                minio_client.create_bucket(Bucket=BUCKET_NAME)
                print(f"✓ Created bucket '{BUCKET_NAME}'")
            self.minio_success = True
        except Exception as e:
            print(f"✗ MinIO setup failed: {str(e)}")
            self.minio_success = False

    def verify_twelve_data(self):
        try:
            api = TwelveDataAPI()
            response = api.test_connection()
            if 'code' in response and response['code'] == 401:
                print(f"✗ Twelve Data API key invalid: {response}")
                self.twelve_data_success = False
            else:
                print("✓ Twelve Data API key verified")
                self.twelve_data_success = True
        except Exception as e:
            print(f"✗ Twelve Data API verification failed: {str(e)}")
            self.twelve_data_success = False

    def run(self):
        print("🔧 Setting up Algotrading Bot...")
        self.setup_minio()
        self.verify_twelve_data()
        
        if self.minio_success and self.twelve_data_success:
            print("\n✨ Setup completed successfully!")
        else:
            print("\n⚠️ Setup completed with errors. Please fix the issues above.")

if __name__ == "__main__":
    setup = Setup()
    setup.run()
