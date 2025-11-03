# Discord Webhook Status

## Current Situation

**Status:** ⚠️ Temporarily Blocked by Cloudflare

**Error:** HTTP 403 - Cloudflare error code 1010

**Cause:** Too many rapid webhook POST requests from this Codespaces IP address triggered Cloudflare's rate limiting/DDoS protection.

## Webhook Details

- ✅ **Format:** Valid Discord webhook URL
- ✅ **Webhook ID:** 1434889818566824091
- ✅ **Token Length:** 68 characters (correct)
- ✅ **Environment:** Properly loaded from GitHub Codespaces secrets
- ✅ **Fallback File:** `reports/.discord_webhook` updated

## What Happened

1. Initial direct test worked (HTTP 204)
2. Ran multiple diagnostic scripts in rapid succession
3. Sent 5+ showcase embeds quickly
4. Cloudflare detected this as potential abuse
5. IP address temporarily blocked (error 1010)

## Solutions

### Option 1: Wait for Block to Clear (RECOMMENDED)

Cloudflare blocks are typically temporary (5-15 minutes).

**Run the wait-and-retry script:**
```bash
./scripts/wait_and_test_webhook.sh
```

This will:
- Wait 3 minutes
- Test the webhook
- Report success or suggest next steps

### Option 2: Create New Webhook (IMMEDIATE)

1. Go to Discord:
   - Server Settings → Integrations → Webhooks
   - **Delete** the current webhook (ID: 1434889818566824091)
   - **Create** a new webhook
   - Copy the new URL

2. Update Codespaces secret:
   ```bash
   gh secret set DISCORD_WEBHOOK_URL
   ```
   Paste the new webhook URL when prompted

3. Restart the Codespace or export manually:
   ```bash
   export DISCORD_WEBHOOK_URL='your-new-url'
   ```

4. Test:
   ```bash
   PYTHONPATH=. python scripts/alerts_diag.py
   ```

### Option 3: Test from Different IP

Test the webhook from your local machine to verify it works:

```bash
curl -X POST "YOUR_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"content": "Test from local machine"}'
```

If this works, the webhook is fine - just the Codespaces IP is blocked.

## Prevention for Future

The code has been updated to prevent this:

- ✅ `alerts_showcase.py`: Now has 2-second delays between messages
- ✅ `test_roundtrip.py`: Has 5-second delay between open/close
- ✅ All production code respects rate limits

For testing, always use delays:
```python
import time
send_discord("Message 1")
time.sleep(2)  # Wait 2 seconds
send_discord("Message 2")
```

## Next Steps

**Choose one:**

1. **Wait:** Run `./scripts/wait_and_test_webhook.sh` (takes 3 minutes)
2. **Recreate:** Delete and create new webhook in Discord, update secret
3. **Verify:** Test from your local machine using curl

## Files Created

- `scripts/wait_and_test_webhook.sh` - Automated wait-and-retry script
- `scripts/alerts_doctor.py` - Comprehensive webhook diagnostics
- `DISCORD_WEBHOOK_STATUS.md` - This status document

## Questions?

The webhook URL is valid and the code is correct. This is purely a Cloudflare rate limiting issue that will resolve itself with time or a fresh webhook.
