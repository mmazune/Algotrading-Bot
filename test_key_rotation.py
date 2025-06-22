from api_rotation import twelvedata_manager, finnhub_rest_manager, finnhub_websocket_manager
import time

print("\n--- Testing Twelve Data Key Rotation (should rotate after 8 calls) ---")
for i in range(16):
    key = twelvedata_manager.get_key()
    print(f"Call {i+1}: Got Twelve Data key: {key}")
    time.sleep(0.5)  # Short sleep to simulate rapid calls

print("\n--- Testing Finnhub REST Key Rotation (should rotate after 60 calls) ---")
for i in range(65):
    key = finnhub_rest_manager.get_key("rest")
    if i < 5 or i > 58:  # Only print first 5 and last 5 for brevity
        print(f"Call {i+1}: Got Finnhub REST key: {key}")

print("\n--- Testing Finnhub WebSocket Key Rotation (should rotate after 50 calls) ---")
for i in range(55):
    key = finnhub_websocket_manager.get_key("websocket")
    if i < 5 or i > 48:  # Only print first 5 and last 5 for brevity
        print(f"Call {i+1}: Got Finnhub WebSocket key: {key}")

print("\nIf you see '[ROTATION]' logs and counters reset, the system is working!")
