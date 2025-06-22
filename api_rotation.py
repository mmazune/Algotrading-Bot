import time
from collections import deque, defaultdict
import threading
from config import TWELVE_DATA_KEYS, FINNHUB_KEYS

class KeyManager:
    def __init__(self, service):
        self.service = service
        self.keys = deque(
            [(owner, key) for owner, key in 
             (TWELVE_DATA_KEYS if service == "twelvedata" else FINNHUB_KEYS).items()]
        )
        self.counters = defaultdict(int)
        self.reset_times = defaultdict(float)
        self.lock = threading.Lock()  # Thread safety for concurrent access
        
        # Service-specific limits
        self.limits = {
            "twelvedata": {"calls": 8, "period": 60},  # 8 calls/minute
            "finnhub": {
                "rest": {"calls": 60, "period": 60},  # 60 calls/minute
                "websocket": {"calls": 50, "period": 86400}  # 50 calls/day
            }
        }
    
    def get_key(self, endpoint="rest"):
        with self.lock:  # Ensure thread safety
            current_owner, current_key = self.keys[0]
            
            # Determine limit type
            limit_type = endpoint if self.service == "finnhub" else "calls"
            period = (
                self.limits[self.service][endpoint]["period"]
                if self.service == "finnhub"
                else self.limits[self.service]["period"]
            )
            
            # Reset counter if period expired
            if time.time() - self.reset_times[current_owner] > period:
                self.counters[current_owner] = 0
                self.reset_times[current_owner] = time.time()
            
            # Check if limit reached
            max_calls = (
                self.limits[self.service][endpoint]["calls"]
                if self.service == "finnhub"
                else self.limits[self.service]["calls"]
            )
            
            if self.counters[current_owner] >= max_calls:
                # Rotate to next key
                self.keys.rotate(-1)
                current_owner, current_key = self.keys[0]
                self.counters[current_owner] = 0
                self.reset_times[current_owner] = time.time()
                print(f"[ROTATION] Switched to {self.service} key from {current_owner}")
            
            # Increment counter
            self.counters[current_owner] += 1
            
            print(f"Using {self.service} key from {current_owner} "
                  f"({self.counters[current_owner]}/{max_calls} calls this period)")
            return current_key
    
    def get_usage_stats(self):
        """Return current usage statistics for all keys"""
        stats = {}
        for owner, _ in self.keys:
            stats[owner] = {
                "calls": self.counters[owner],
                "last_reset": self.reset_times[owner]
            }
        return stats

# Initialize managers as singletons
twelvedata_manager = KeyManager("twelvedata")
finnhub_rest_manager = KeyManager("finnhub")
finnhub_websocket_manager = KeyManager("finnhub")
