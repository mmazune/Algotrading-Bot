#!/bin/bash

echo "==================================="
echo "Replay Parity Pack - Demo Test"
echo "==================================="
echo ""

echo "Step 1: Running heuristic scan..."
echo "-----------------------------------"
SCAN_OUTPUT=$(python -m axfl.cli scan --symbols EURUSD --strategies lsg --days 30 --source auto --venue OANDA --method heuristic --pad_before 60 --pad_after 60 2>&1)

echo "$SCAN_OUTPUT" | grep -A 5 "=== AXFL Signal Scanner ==="

# Extract SCANS JSON
SCANS_JSON=$(echo "$SCAN_OUTPUT" | sed -n '/###BEGIN-AXFL-SCANS###/,/###END-AXFL-SCANS###/p' | sed '1d;$d')

if [ -z "$SCANS_JSON" ]; then
    echo "ERROR: No SCANS JSON found"
    exit 1
fi

echo ""
echo "Step 2: Scan completed successfully"
echo "-----------------------------------"
echo "SCANS JSON (first 200 chars):"
echo "$SCANS_JSON" | cut -c1-200
echo "..."

# Count targets
TARGET_COUNT=$(echo "$SCANS_JSON" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('targets', [])))")
echo "Found $TARGET_COUNT targets"

if [ "$TARGET_COUNT" -eq 0 ]; then
    echo "WARNING: No targets found in scan, skipping replay"
    exit 0
fi

echo ""
echo "Step 3: Running replay-slice..."
echo "-----------------------------------"
REPLAY_OUTPUT=$(python -m axfl.cli replay-slice --scans "$SCANS_JSON" --use_scan_params false --warmup_days 3 --assert_min_trades 0 --extend 0 2>&1)

echo "$REPLAY_OUTPUT" | grep -A 10 "=== AXFL Targeted Replay ==="

echo ""
echo "Step 4: Checking outputs..."
echo "-----------------------------------"

# Check for LIVE-PORT block
if echo "$REPLAY_OUTPUT" | grep -q "BEGIN-AXFL-LIVE-PORT"; then
    echo "✅ LIVE-PORT block emitted"
else
    echo "❌ LIVE-PORT block missing"
fi

# Check for DIAG block (should NOT be present with assert_min_trades=0)
if echo "$REPLAY_OUTPUT" | grep -q "BEGIN-AXFL-DIAG"; then
    echo "⚠️  DIAG block present (unexpected)"
else
    echo "✅ No DIAG block (expected)"
fi

# Check targets_used
if echo "$REPLAY_OUTPUT" | grep -q "targets_used"; then
    echo "✅ targets_used tracking present"
else
    echo "❌ targets_used tracking missing"
fi

# Check assertion message
if echo "$REPLAY_OUTPUT" | grep -q "Assertion passed"; then
    echo "✅ Assertion check executed"
else
    echo "❌ Assertion check missing"
fi

echo ""
echo "==================================="
echo "Test Complete!"
echo "==================================="
