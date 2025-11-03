#!/bin/bash
# Discord Webhook Test - Wait and Retry
# This script waits for Cloudflare block to clear, then tests the webhook

echo "════════════════════════════════════════════════════════════════"
echo "Discord Webhook - Wait and Retry Test"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Cloudflare has temporarily blocked this IP due to rapid requests."
echo "Waiting 3 minutes for the block to clear..."
echo ""

for i in {1..18}; do
    echo -n "⏳ $(($i * 10)) seconds elapsed..."
    sleep 10
    echo " ✓"
done

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Block should be cleared - Testing webhook now..."
echo "════════════════════════════════════════════════════════════════"
echo ""

PYTHONPATH=. python - <<'PY'
import os, json, urllib.request, urllib.error

webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

payload = {"content": "✅ **WEBHOOK RETRY TEST** - Cloudflare block cleared!"}
data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(webhook, data=data, headers={"Content-Type": "application/json"}, method="POST")

try:
    with urllib.request.urlopen(req, timeout=10) as r:
        print(f"✅ SUCCESS! HTTP {r.getcode()}")
        print("Message delivered to Discord!")
        print("")
        print("You should now see the message in your Discord channel.")
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", "ignore")
    print(f"❌ Still blocked: HTTP {e.code} - {body}")
    print("")
    print("Cloudflare block hasn't cleared yet.")
    print("Please try one of these:")
    print("  1. Wait another 5-10 minutes and run this script again")
    print("  2. Delete and recreate the webhook in Discord")
except Exception as ex:
    print(f"❌ Error: {ex}")
PY

echo ""
echo "════════════════════════════════════════════════════════════════"
