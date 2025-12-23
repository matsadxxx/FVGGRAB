import sys
import os
import json # For json.JSONDecodeError

# Adjust path for imports:
# __file__ is /app/fvgrab_app/tools/test_backtest_api_nofetch.py
# script_dir is /app/fvgrab_app/tools
# project_root (parent of script_dir) is /app/fvgrab_app
# This makes 'app' (as in 'from app.main...') importable from /app/fvgrab_app/app
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print("DEBUG: Attempting to import app.core_logic.backtester directly...")
try:
    from app.core_logic import backtester
    print("DEBUG: Successfully imported app.core_logic.backtester")
    from app.core_logic import fvg_detector # Also check this one
    print("DEBUG: Successfully imported app.core_logic.fvg_detector")
    from app.services import bybit_service # And this one
    print("DEBUG: Successfully imported app.services.bybit_service")
except ImportError as ie:
    print(f"ERROR: Direct import failed: {ie}")
    print(f"Current sys.path: {sys.path}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Other error during direct import: {e}")
    sys.exit(1)

from fastapi.testclient import TestClient
# Try to import the app instance; if app.main has issues, this might fail early.
try:
    from app.main import app
except ModuleNotFoundError as e:
    print(f"ERROR: Could not import 'app' from 'app.main'. Ensure PYTHONPATH is correct or app structure is valid.")
    print(f"Current sys.path: {sys.path}")
    print(f"Original error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: An unexpected error occurred during import of app.main: {e}")
    sys.exit(1)


def run_api_test():
    """
    Tests the /api/v1/backtest/run endpoint, expecting a failure due to
    Bybit data fetching issues (as observed in previous tests).
    """
    # Configure basic logging to see output from the app if it's not already configured globally
    # import logging
    # logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    client = TestClient(app)

    print("Attempting to call POST /api/v1/backtest/run endpoint...")

    # Define a valid payload according to BacktestParams Pydantic model
    payload = {
        "symbol": "BTCUSDT",
        "interval": "60", # 1-hour
        "category": "linear",
        "data_limit": 100, # Using a small limit for this test
        "static_threshold_percent": 0.0, # Renamed in API from fvg_static_threshold_percent
        "use_adaptive_threshold": False,
        "use_volume_confirmation": False,
        "volume_lookback_period": 20,
        "volume_factor": 1.5,
        "min_fvg_price_height": 0.0,
        "initial_balance": 10000.0,
        "commission_percent": 0.00075, # e.g., 0.075%
        "risk_per_trade_percent": 1.0,  # e.g., 1%
        "risk_free_rate_annual": 0.0    # e.g., 0%
    }
    # Note: Field aliases like 'fvg_static_threshold_percent' are for query params.
    # For Pydantic request body, use the actual field names if no alias is defined for body fields.
    # The Pydantic model in fvg_router.py for BacktestParams uses the direct field names.
    # The API endpoint definition for /fvgs/historical used aliases for its query params.
    # The /backtest/run endpoint uses a Pydantic model `BacktestParams` with direct field names.

    response = None
    try:
        response = client.post("/api/v1/backtest/run", json=payload)
    except Exception as e:
        print(f"ERROR: TestClient POST request failed: {type(e).__name__} - {str(e)}")
        print("This might indicate an issue with the FastAPI application setup or TestClient itself.")
        sys.exit(1)


    print(f"\n--- API Call Report for /api/v1/backtest/run ---")
    print(f"Status Code: {response.status_code}")

    response_json = None
    try:
        response_json = response.json()
        print(f"Response JSON: {json.dumps(response_json, indent=4)}") # Pretty print JSON
    except json.JSONDecodeError:
        print(f"Response Content (not JSON): {response.text}")
    except Exception as e:
        print(f"Error decoding or printing JSON response: {e}")

    # Verification based on expected behavior (Bybit API call fails)
    if response.status_code == 503:
        print("\nTest Result: PASSED (Received 503 Service Unavailable).")
        print("This is the expected outcome if bybit_service.get_historical_klines_bybit returns None due to Bybit API issues.")
    elif response.status_code == 404 and response_json and "Not enough kline data" in response_json.get("detail", ""):
        print("\nTest Result: PASSED (Received 404 Not Found with 'Not enough kline data' message).")
        print("This is expected if bybit_service.get_historical_klines_bybit returns an empty DataFrame (or too few rows) and the endpoint logic then raises 404.")
    else:
        print(f"\nTest Result: FAILED (Expected 503 or specific 404, but received {response.status_code}).")
        if response_json:
             print("Please check the 'Response JSON' above for details from the API.")
        else:
            print("Response content was not valid JSON, check 'Response Content' above.")
    print("--- End of Report ---")

if __name__ == "__main__":
    print(f"Current sys.path for test_backtest_api_nofetch.py: {sys.path}\n")
    run_api_test()
