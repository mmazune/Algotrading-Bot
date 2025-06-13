import sys
import subprocess
import pkg_resources

def check_package(package_name):
    try:
        dist = pkg_resources.get_distribution(package_name)
        print(f"{package_name} version {dist.version} is installed at {dist.location}")
        return True
    except pkg_resources.DistributionNotFound:
        print(f"{package_name} is NOT installed")
        return False

print(f"Python executable path: {sys.executable}")
print(f"Python version: {sys.version}")
print("\nChecking required packages:")

packages = ['finnhub-python', 'boto3', 'pyarrow']
missing = []

for pkg in packages:
    if not check_package(pkg):
        missing.append(pkg)

if missing:
    print("\nAttempting to install missing packages...")
    for pkg in missing:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
            print(f"Successfully installed {pkg}")
        except subprocess.CalledProcessError:
            print(f"Failed to install {pkg}")
