import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from api_rotation import twelvedata_manager
import requests

class TwelveDataAPI:
    BASE_URL = "https://api.twelvedata.com"
    
    def get_time_series(self, symbol, interval='1day'):
        endpoint = f"{self.BASE_URL}/time_series"
        api_key = twelvedata_manager.get_key()
        params = {
            'symbol': symbol,
            'interval': interval,
            'apikey': api_key
        }
        
        print(f"Requesting Twelve Data with params: {params}")  # Debug log
        response = requests.get(endpoint, params=params)
        return response.json()
    
    def test_connection(self):
        return self.get_time_series('AAPL', '1min')

if __name__ == "__main__":
    api = TwelveDataAPI()
    print(api.test_connection())
