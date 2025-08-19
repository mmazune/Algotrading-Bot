# GitHub Secrets Setup Guide

## What are GitHub Secrets?
GitHub Secrets allow you to securely store sensitive information like API keys, passwords, and tokens that your workflows need to access. These secrets are encrypted and only available to GitHub Actions during workflow execution.

## How to Add GitHub Secrets

### Step 1: Access Repository Settings
1. Go to your GitHub repository: https://github.com/mmazune/Algotrading-Bot
2. Click on the **Settings** tab (you need admin/write access to the repository)
3. In the left sidebar, expand **Secrets and variables**
4. Click on **Actions**

### Step 2: Add New Repository Secrets
Click on **New repository secret** and add each of the following secrets:

#### Required API Keys:

**Option 1: Single API Keys (Basic Setup)**

1. **FINNHUB_API_KEY**
   - Name: `FINNHUB_API_KEY`
   - Value: Your Finnhub API key (get it from https://finnhub.io/)
   - This is used for fetching stock data from Finnhub

2. **TWELVEDATA_API_KEY**
   - Name: `TWELVEDATA_API_KEY`
   - Value: Your TwelveData API key (get it from https://twelvedata.com/)
   - This is used for fetching stock data from TwelveData

**Option 2: Multiple API Keys (Recommended for Production)**

For better rate limit management with automatic key rotation:

**Finnhub Keys (Add as many as you have):**
- `FINNHUB_API_KEY_1` - Your primary Finnhub key
- `FINNHUB_API_KEY_2` - Your secondary Finnhub key  
- `FINNHUB_API_KEY_3` - Your tertiary Finnhub key
- ... (continue with _4, _5, etc. as needed)

**TwelveData Keys (Add as many as you have):**
- `TWELVEDATA_API_KEY_1` - Your primary TwelveData key
- `TWELVEDATA_API_KEY_2` - Your secondary TwelveData key
- `TWELVEDATA_API_KEY_3` - Your tertiary TwelveData key
- ... (continue with _4, _5, etc. as needed)

**Note**: The system will automatically detect and use all available keys for rotation!

#### Optional MinIO Storage Keys (if using MinIO):

3. **MINIO_ACCESS_KEY**
   - Name: `MINIO_ACCESS_KEY`
   - Value: Your MinIO access key
   - Default: `minioadmin` (if using the default setup)

4. **MINIO_SECRET_KEY**
   - Name: `MINIO_SECRET_KEY`
   - Value: Your MinIO secret key
   - Default: `minioadmin` (if using the default setup)

5. **MINIO_ENDPOINT**
   - Name: `MINIO_ENDPOINT`
   - Value: Your MinIO endpoint URL
   - Example: `http://159.223.139.171:9000`

### Step 3: Verify Secrets
After adding all secrets, you should see them listed in the repository secrets section. The values will be hidden for security.

## Getting API Keys

### Finnhub API Key:
1. Go to https://finnhub.io/
2. Sign up for a free account
3. Navigate to your dashboard
4. Copy your API key
5. Free tier allows 60 calls/minute

### TwelveData API Key:
1. Go to https://twelvedata.com/
2. Sign up for a free account
3. Go to your dashboard
4. Copy your API key
5. Free tier allows 800 requests/day

## Testing Your Setup

### Manual Workflow Trigger:
1. Go to the **Actions** tab in your repository
2. Click on **Automated Financial Data Pipeline**
3. Click **Run workflow**
4. Enter a stock symbol (e.g., AAPL, MSFT, GOOGL)
5. Select a data interval
6. Click **Run workflow**

### Check Workflow Results:
1. Click on the running/completed workflow
2. Expand each step to see the logs
3. Look for successful data fetching and CSV creation
4. Check if `transformed_financial_data.csv` appears in your repository

## Security Best Practices

1. **Never commit API keys to your repository**
2. **Use GitHub Secrets for all sensitive data**
3. **Regularly rotate your API keys**
4. **Monitor your API usage to prevent unexpected charges**
5. **Use different API keys for development and production**

## Troubleshooting

### Common Issues:

1. **"API key not provided"**: Make sure the secret name exactly matches what's in the workflow
2. **"Rate limit exceeded"**: You've exceeded your API quota, wait or upgrade your plan
3. **"No data returned"**: Check if the stock symbol exists and markets are open
4. **"Permission denied"**: Ensure you have write access to the repository

### Viewing Logs:
- Go to Actions tab → Click on workflow run → Expand individual steps
- Look for error messages in the "Run data collection and transformation script" step

## Next Steps

After setting up secrets:
1. The workflow will run automatically daily at midnight UTC
2. You can trigger manual runs anytime from the Actions tab
3. Data will be saved as `transformed_financial_data.csv` in your repository
4. Monitor the Actions tab for successful/failed runs

## Support

If you encounter issues:
1. Check the workflow logs in the Actions tab
2. Verify your API keys are valid and have sufficient quota
3. Ensure the stock symbol exists and is correctly formatted
4. Check that all secrets are properly named and set
