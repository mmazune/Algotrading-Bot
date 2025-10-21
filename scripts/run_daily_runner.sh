#!/bin/bash
# AXFL Daily Runner - Production launcher script
# Runs automated London + NY trading sessions
set -e

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Change to repo root
cd "$REPO_ROOT"

echo "=== AXFL Daily Runner Starting ==="
echo "Working directory: $(pwd)"
echo "Time: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

# Load environment variables from /etc/axfl/axfl.env if present
if [ -f "/etc/axfl/axfl.env" ]; then
    echo "Loading environment from /etc/axfl/axfl.env"
    set -a  # automatically export all variables
    source /etc/axfl/axfl.env
    set +a
else
    echo "Warning: /etc/axfl/axfl.env not found, using existing environment"
fi

# Activate virtualenv if it exists
if [ -d ".venv" ]; then
    echo "Activating virtualenv: .venv"
    source .venv/bin/activate
else
    echo "No .venv found, using system Python"
fi

# Show Python version
echo "Python: $(python --version)"
echo "Python path: $(which python)"

# Verify OANDA credentials
if [ -z "$OANDA_API_KEY" ] || [ -z "$OANDA_ACCOUNT_ID" ]; then
    echo "ERROR: OANDA credentials not set in environment"
    echo "Please configure /etc/axfl/axfl.env with OANDA_API_KEY and OANDA_ACCOUNT_ID"
    exit 1
fi

echo "OANDA environment: ${OANDA_ENV:-practice}"
echo "Finnhub keys configured: $([ -n "$FINNHUB_API_KEYS" ] && echo 'yes' || echo 'no')"
echo "Discord webhook configured: $([ -n "$DISCORD_WEBHOOK_URL" ] && echo 'yes' || echo 'no')"
echo ""

# Run the daily runner
echo "Launching AXFL daily runner..."
exec python -m axfl.cli daily-runner \
    --cfg axfl/config/sessions.yaml \
    --profile portfolio
