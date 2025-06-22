# Dependency check for required packages
required_packages = [
    'boto3',
    'pyarrow',
    'pandas',
    'requests',
    'finnhub',
]
missing = []
for pkg in required_packages:
    try:
        __import__(pkg)
    except ImportError:
        missing.append(pkg)
if missing:
    print(f"ERROR: The following required packages are missing: {', '.join(missing)}")
    print("Please install them with:")
    print(f"    pip install {' '.join(missing)}")
    import sys
    sys.exit(1)

# MinIO Configuration
MINIO_CONFIG = {
    'endpoint': 'localhost:9000',
    'access_key': 'minioadmin',  # Default MinIO access key
    'secret_key': 'minioadmin',  # Default MinIO secret key
    'secure': False
}

# API Key Rotation Configuration
TWELVE_DATA_KEYS = {
    "Elijah": "509e81ce956741b48b5db02c7d4baeba",
    "Mark": "d7ca6bcdd1d247289088dd40a1cad1ac",
    "Pamella": "1f21fc9b320743f793737f7822cd5910",
    "Nicky": "5cd89fc3c99d4e86bbf3db3fc633d14c",
    "Leticia": "8cb1d203fde04aa18592197405b14280",
    "Katrina": "5ebf17461c3946afb292f55a6f1b5c0b",
    "Mine": "9977c171aff74be9948775735805e5c0"
}

FINNHUB_KEYS = {
    "Leticia": "d18kaj9r01qg5218jce0d18kaj9r01qg5218jceg",
    "Nicky": "d18kn6pr01qg5218lii0d18kn6pr01qg5218liig",
    "Mark": "d18kilpr01qg5218kpjgd18kilpr01qg5218kpk0",
    "Pamella": "d18kci9r01qg5218jnvgd18kci9r01qg5218jo00",
    "Elijah": "d18kcehr01qg5218jn5gd18kcehr01qg5218jn60",
    "Katrina": "d16rlcpr01qkv5jctje0d16rlcpr01qkv5jctjeg",
    "Mine": "d13gq5pr01qs7glhghj0d13gq5pr01qs7glhghjg"
}

# Bucket names
BUCKET_NAME = 'market-data'  # Main bucket for raw data
RAW_DATA_BUCKET = 'market-data'  # Alias for raw data bucket
PROCESSED_DATA_BUCKET = 'processed-financial-data'  # Bucket for transformed data

# Fallback keys for direct usage
MINE_TWELVE_DATA_KEY = TWELVE_DATA_KEYS["Mine"]
MINE_FINNHUB_KEY = FINNHUB_KEYS["Mine"]
