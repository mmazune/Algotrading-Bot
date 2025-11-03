#!/bin/bash
# Quick Webhook Test - Run after updating DISCORD_WEBHOOK_URL

echo "════════════════════════════════════════════════════════════════"
echo "Testing New Webhook URL"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Update fallback file
python - <<'PY'
import os, pathlib
webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
if webhook:
    pathlib.Path("reports").mkdir(exist_ok=True)
    pathlib.Path("reports/.discord_webhook").write_text(webhook)
    print(f"✅ Webhook stored in fallback file")
    print(f"   Length: {len(webhook)} chars")
    print(f"   Ends with: ...{webhook[-15:]}")
else:
    print("❌ No webhook found in environment")
    exit(1)
PY

echo ""
echo "Testing webhook delivery..."
echo ""

# Single test message
PYTHONPATH=. python - <<'PY'
import os, json, urllib.request, urllib.error

webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
payload = {"content": "🎉 **NEW WEBHOOK WORKING!** AXFL alerts are now operational."}
data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(webhook, data=data, headers={"Content-Type": "application/json"}, method="POST")

try:
    with urllib.request.urlopen(req, timeout=10) as r:
        print(f"✅ SUCCESS! HTTP {r.getcode()}")
        print("")
        print("Message delivered to Discord!")
        print("Check your channel - you should see the message.")
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", "ignore")
    print(f"❌ Error: HTTP {e.code} - {body}")
except Exception as ex:
    print(f"❌ Exception: {ex}")
PY

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "If successful, we can now run the full test suite!"
echo "════════════════════════════════════════════════════════════════"
