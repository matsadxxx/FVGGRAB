import asyncio
import sys
import os
import pandas as pd # Ensure pandas is imported for type checking

# Adjust path to import from the 'app' package.
# __file__ is /app/fvgrab_app/tools/test_bybit_rest.py
# script_dir is /app/fvgrab_app/tools
# project_root (parent of script_dir) is /app/fvgrab_app
# This makes 'app' (as in 'from app.services...') importable from /app/fvgrab_app/app
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now the import should work if 'app' is a package directly under project_root
from app.services.bybit_service import get_historical_klines_bybit

async def main():
    print("Attempting to fetch historical klines for BTCUSDT (linear) from Bybit v5 API...")
    result_df = None
    error_message = None

    # Configure basic logging for bybit_service if it uses `logger.debug` etc.
    # This is optional for this test but can be helpful.
    # import logging
    # logging.basicConfig(level=logging.DEBUG) # To see debug logs from bybit_service

    try:
        result_df = await get_historical_klines_bybit(
            symbol="BTCUSDT",
            interval="60",  # 1-hour interval
            limit=10,       # Fetch 10 klines
            category="linear"
        )
    except Exception as e:
        error_message = f"Unhandled exception during API call: {type(e).__name__} - {str(e)}"
        print(error_message)
        # For more detail if needed:
        # import traceback
        # print(traceback.format_exc())

    print("\n--- API Call Report ---")
    if error_message:
        print("Outcome: Unhandled exception occurred during the API call.")
        print(f"Details: {error_message}")
    elif result_df is None:
        print("Outcome: Function returned None.")
        print("This indicates an error was handled within get_historical_klines_bybit(), such as an API error response (e.g., bad request, auth issue if keys were used, or server error from Bybit).")
        print("Check logs from bybit_service if it includes detailed error logging for API responses.")
    elif isinstance(result_df, pd.DataFrame) and result_df.empty:
        print("Outcome: Success, but an empty DataFrame was returned.")
        print("This could mean there's no data for the requested symbol/interval/category, or an issue where the API returns success with an empty list.")
    elif isinstance(result_df, pd.DataFrame) and not result_df.empty:
        print("Outcome: Success! Data received.")
        print(f"Number of rows received: {len(result_df)}")
        print("First 3 rows of data:")
        print(result_df.head(3))
        print("\nLast 3 rows of data:")
        print(result_df.tail(3))
    else:
        print(f"Outcome: Unknown result type received: {type(result_df)}")
        if result_df is not None:
            print(f"Value: {result_df}")
    print("--- End of Report ---")

if __name__ == "__main__":
    # Ensure loop is managed correctly if running in some environments
    # For simple scripts, asyncio.run() is usually fine.
    # If there are issues like "loop is already running" in other contexts (e.g. Jupyter),
    # consider nest_asyncio or other event loop management.
    asyncio.run(main())
