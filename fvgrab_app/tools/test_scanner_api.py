import sys
import os
import json

# Adjust path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi.testclient import TestClient
from app.main import app # app.main is where `app = FastAPI()` is expected

def run_scanner_api_test():
    client = TestClient(app)

    print("Attempting to call POST /api/v1/scanner/run-scan endpoint...")

    payload = {
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "intervals": ["15", "60"],
        "category": "linear",
        "kline_limit_per_scan": 30, # Min value for the endpoint
        "static_threshold_percent": 0.0,
        "use_adaptive_threshold": False,
        "adaptive_threshold_period_UNUSED": 0,
        "use_volume_confirmation": False,
        "volume_lookback_period": 20,
        "volume_factor": 1.5,
        "min_fvg_price_height": 0.0
    }

    response = None
    try:
        response = client.post("/api/v1/scanner/run-scan", json=payload)
    except Exception as e:
        print(f"ERROR: TestClient POST request to scanner failed: {type(e).__name__} - {str(e)}")
        sys.exit(1)

    print(f"\n--- API Call Report for /api/v1/scanner/run-scan ---")
    print(f"Status Code: {response.status_code}")

    response_json = None
    try:
        response_json = response.json()
        print(f"Response JSON: {json.dumps(response_json, indent=4)}")
    except json.JSONDecodeError:
        print(f"Response Content (not JSON): {response.text}")
    except Exception as e:
        print(f"Error decoding or printing JSON response: {e}")

    # Verification:
    # Expecting 200 OK with a list (likely of items indicating fetch failure or no FVGs)
    if response.status_code == 200:
        print("\nTest Result: PASSED (Received 200 OK).")
        if isinstance(response_json, list):
            print(f"Received {len(response_json)} items in the list (expected {len(payload['symbols']) * len(payload['intervals'])} items if all processed).")
            # Further checks could inspect the content of response_json items
            # to see if they correctly reflect errors from bybit_service.
            # For this test, 200 OK and a list response is the main check.
            for item in response_json:
                if item.get("error"):
                    print(f"  Symbol {item.get('symbol', 'N/A')} for interval {item.get('interval_scanned', 'N/A')} reported error: {item['error']}")
                elif "fvgs" in item:
                     print(f"  Symbol {item.get('symbol', 'N/A')} for interval {item.get('interval_scanned', 'N/A')} found {len(item['fvgs'])} FVGs.")

        else:
            print("Test Result: FAILED (Expected a JSON list in response).")
    else:
        print(f"\nTest Result: FAILED (Expected 200 OK, but received {response.status_code}).")
        if response_json:
             print("Please check the 'Response JSON' above for error details from the API.")
    print("--- End of Report ---")

if __name__ == "__main__":
    print(f"Current sys.path for test_scanner_api.py: {sys.path}\n")
    run_scanner_api_test()
