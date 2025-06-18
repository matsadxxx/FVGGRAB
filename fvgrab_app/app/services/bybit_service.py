"""
Service module for interacting with the Bybit API.

This module handles fetching historical kline data via Bybit's REST API (v5)
and setting up WebSocket connections for live kline data streams.
It uses the 'pybit' library for API communication.

Key functionalities:
- Fetch historical OHLCV data.
- Establish and manage WebSocket subscriptions for real-time kline updates.

Note:
- WebSocket functionality is currently impaired due to issues with `pybit.subscribe()`.
- REST API calls may be restricted in certain sandboxed environments.
"""
import pandas as pd
from pybit.unified_trading import HTTP as UnifiedHTTP  # Renamed for clarity
from pybit.unified_trading import WebSocket as UnifiedWebSocket
import asyncio
import time
from datetime import datetime
import logging

logger = logging.getLogger(__name__) # Logger for this module
# TODO: Ensure global logging (basicConfig) is configured in main.py for consistent output.

# --- HTTP Client Setup ---
# TODO: Consider managing HTTP session more globally (e.g., using a singleton or dependency injection)
#       for better performance, connection pooling, and rate limit adherence.
# TODO: Add API key/secret management for any private endpoints if those become necessary in the future.
#       (Currently only public data endpoints are used).

async def get_historical_klines_bybit(
    symbol: str,
    interval: str,
    limit: int = 200,
    category: str = "linear"
) -> pd.DataFrame | None:
    """
    Fetches historical kline (OHLCV) data from the Bybit v5 API.

    Args:
        symbol (str): Trading symbol, e.g., "BTCUSDT".
        interval (str): Kline interval. Bybit examples: '1', '5', '60', 'D', 'W'.
        limit (int, optional): Number of klines to fetch. Max is 1000 for Bybit's
                               `get_kline` endpoint. Defaults to 200.
        category (str, optional): Category of trading ('linear', 'spot', 'inverse').
                                  Defaults to "linear".

    Returns:
        Optional[pd.DataFrame]: A pandas DataFrame with columns ['time', 'open', 'high',
                                 'low', 'close', 'volume'], sorted by time ascending.
                                 Returns None if an API error occurs.
                                 Returns an empty DataFrame if the API call is successful
                                 but no data is returned (e.g., new symbol).

    Note:
        This function uses Bybit's v5 `get_kline` endpoint.
        During previous tests in some sandboxed environments, direct API calls failed,
        possibly due to network restrictions or SSL issues. Requires testing in an
        open environment for confirmation.
    """
    # TODO: Implement more sophisticated error handling for API calls, including retries with exponential backoff.
    # TODO: Add more comprehensive rate limit handling if making frequent calls.

    # Using UnifiedHTTP from pybit for v5 API
    session = UnifiedHTTP(testnet=False)

    if limit > 1000:
        logger.warning(f"Requested kline limit {limit} exceeds Bybit's max of 1000. Capping to 1000.")
        limit = 1000

    try:
        logger.debug(f"Fetching Bybit klines: Category='{category}', Symbol='{symbol}', Interval='{interval}', Limit={limit}")
        response = session.get_kline(
            category=category,
            symbol=symbol,
            interval=interval,
            limit=limit
        )

        if response and response.get('retCode') == 0:
            klines_data = response.get('result', {}).get('list', [])
            if not klines_data:
                logger.info(f"No kline data returned from Bybit for {symbol}, interval {interval}, category {category}.")
                return pd.DataFrame() # Return empty DataFrame for no data scenario

            # Kline data format from Bybit: [timestamp, open, high, low, close, volume, turnover]
            df = pd.DataFrame(klines_data, columns=[
                'time', 'open', 'high', 'low', 'close', 'volume', 'turnover'
            ])

            # Data processing and type conversion
            df['time'] = pd.to_datetime(df['time'].astype(int), unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            # Select and order final columns
            df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
            # Bybit v5 API get_kline returns data in descending order (newest first).
            # Sort to ascending order (oldest first) for typical analysis usage.
            df = df.sort_values(by='time', ascending=True).reset_index(drop=True)
            return df
        else:
            err_code = response.get('retCode')
            err_msg = response.get('retMsg')
            logger.error(f"Error fetching klines from Bybit for {symbol} (Cat: {category}, Int: {interval}): {err_msg} (Code: {err_code})")
            return None

    except Exception as e:
        logger.exception(f"An exception occurred while fetching klines for {symbol} (Cat: {category}, Int: {interval}): {e}")
        return None

# --- WebSocket Implementation ---

# TODO: Consider a more robust global/shared WebSocket connection manager if the service needs to scale
#       or if connections need to be managed across different parts of the application.
active_ws_connections: Dict[str, UnifiedWebSocket] = {}

def default_kline_handler(message: Dict):
    """
    Default handler for processing incoming kline data from Bybit WebSocket.

    This function is called by the `pybit` WebSocket client when a new message
    is received on a subscribed kline topic. It logs the received kline data.

    Args:
        message (Dict): The raw message dictionary from `pybit` WebSocket.
                        Expected structure for kline data:
                        {'topic': 'kline.1.BTCUSDT', 'type': 'snapshot'/'delta',
                         'ts': timestamp,
                         'data': [{'start': ..., 'open': ..., 'high': ..., 'low': ...,
                                   'close': ..., 'volume': ..., 'turnover': ...,
                                   'confirm': True/False, 'timestamp': ...}]}

    Note on Current `pybit` Issue:
        - TODO: CRITICAL - The `pybit` library (v5.11.0) showed a `TypeError`
          during `ws.subscribe()` in tests ('bool' object is not iterable in
          `pybit/_websocket_stream.py`). This issue prevents actual subscription
          and data reception. It needs investigation (potential pybit bug, version
          conflict, or specific environment problem) and a workaround or library
          update for WebSocket features to function correctly.
    """
    topic = message.get('topic', 'UnknownTopic')
    data_list = message.get('data', [])

    if not data_list:
        logger.info(f"WS Message on {topic} (no data field or empty data list): {message}")
        return

    # Assuming kline data is usually the first item in the 'data' list for kline streams
    kline = data_list[0]
    symbol = topic.split('.')[-1] if '.' in topic else "UnknownSymbol"

    logger.info(f"WS Kline Received: Symbol={symbol}, "
                f"Time={pd.to_datetime(kline.get('start'), unit='ms')}, "
                f"Open={kline.get('open')}, High={kline.get('high')}, "
                f"Low={kline.get('low')}, Close={kline.get('close')}, "
                f"Volume={kline.get('volume')}, Confirm={kline.get('confirm')}")

async def start_kline_websocket(
    symbol: str,
    interval: str,
    callback_fn: callable,
    testnet: bool = False,
    category: str = "linear"
):
    """
    Starts a Bybit WebSocket connection for a specific kline stream.

    Manages the WebSocket instance and subscribes to the specified kline topic.
    The provided `callback_fn` is invoked upon message receipt.

    Args:
        symbol (str): Trading symbol (e.g., "BTCUSDT").
        interval (str): Kline interval (e.g., "1" for 1 minute, "D" for daily).
        callback_fn (callable): Asynchronous function to process received messages.
        testnet (bool, optional): True to use Bybit testnet, False for mainnet. Defaults to False.
        category (str, optional): Market category ('linear', 'spot', 'inverse'). Defaults to "linear".

    Note on Current `pybit` Issue:
        - TODO: CRITICAL - See note in `default_kline_handler` regarding the `pybit`
          `TypeError` during `subscribe`. This function's ability to subscribe is affected.
    """
    # TODO: Implement more robust error handling for WebSocket operations (e.g., connection drops, auto-reconnect).
    # TODO: Add a mechanism to monitor WebSocket connection health and attempt restarts if necessary.

    ws_client_id = f"{category}_{symbol}_{interval}" # Unique ID for managing this specific WebSocket stream

    # Check if a connection for this specific stream already exists and is active
    if ws_client_id in active_ws_connections:
        # Accessing pybit's internal _is_connected flag if available, or assume connected if in dict.
        # A more robust check might involve a custom health status.
        ws_instance = active_ws_connections[ws_client_id]
        if hasattr(ws_instance, 'is_connected') and ws_instance.is_connected(): # pybit 0.2.x style
             logger.info(f"WebSocket for {ws_client_id} is already running and connected.")
             return
        elif hasattr(ws_instance, '_ws_connected') and ws_instance._ws_connected: # pybit 5.x style
             logger.info(f"WebSocket for {ws_client_id} is already running and connected (pybit 5.x).")
             return
        else:
             logger.warning(f"WebSocket for {ws_client_id} found in active connections but not connected. Attempting to restart.")


    # Initialize Bybit UnifiedWebSocket client
    # channel_type corresponds to the market category ('linear', 'spot', 'inverse', 'option')
    ws = UnifiedWebSocket(testnet=testnet, channel_type=category)

    # Define the subscription topic for klines, e.g., "kline.1.BTCUSDT"
    topic = f"kline.{interval}.{symbol}"

    logger.info(f"Attempting to start WebSocket for {topic} on {'testnet' if testnet else 'mainnet'} (Channel: '{category}').")

    try:
        # Subscribe to the topic.
        # NOTE: This specific call `ws.subscribe([topic], callback=callback_fn)`
        # previously resulted in a TypeError within pybit (v5.11.0).
        # If this issue persists, WebSocket functionality will be impaired.
        ws.subscribe(
            [topic],  # Topics should be passed as a list, even for a single topic
            callback=callback_fn
        )
        active_ws_connections[ws_client_id] = ws # Store the active WebSocket instance
        logger.info(f"Subscription attempt to {topic} successful. Callback: '{callback_fn.__name__}'. Waiting for messages.")
    except Exception as e:
        logger.error(f"Error during WebSocket subscription to {topic}: {e}", exc_info=True)
        # TODO: Propagate this error or implement a retry mechanism so the calling code
        #       (e.g., API endpoint) is aware that the subscription failed.

async def stop_kline_websocket(symbol: str, interval: str, category: str = "linear"):
    """
    Stops and closes a specific Bybit kline WebSocket connection.

    Args:
        symbol (str): Trading symbol.
        interval (str): Kline interval.
        category (str, optional): Market category. Defaults to "linear".

    Note on Current `pybit` Issue:
        - TODO: CRITICAL - See note in `default_kline_handler`. If subscription failed,
          this stop call might be for a non-fully-initialized or problematic WebSocket instance.
    """
    # TODO: Ensure this function handles cases where the WebSocket might not have been fully started
    #       or is in an error state, providing more graceful shutdown and resource cleanup.
    ws_client_id = f"{category}_{symbol}_{interval}"
    if ws_client_id in active_ws_connections:
        logger.info(f"Attempting to stop WebSocket for {ws_client_id}...")
        ws = active_ws_connections.pop(ws_client_id) # Remove from active list first

        # Check if the WebSocket object has an 'exit' method and call it
        if hasattr(ws, 'exit') and callable(ws.exit):
            try:
                ws.exit() # This should close the WebSocket connection
                logger.info(f"WebSocket for {ws_client_id} stop command issued successfully.")
            except Exception as e:
                logger.error(f"Exception while stopping WebSocket for {ws_client_id}: {e}", exc_info=True)
        else:
            # This case might occur if 'ws' is not a fully initialized WebSocket object
            # or if the pybit version has a different way to close.
            logger.warning(f"WebSocket for {ws_client_id} does not have a direct 'exit' method or was not fully initialized. Relying on GC or program exit for cleanup.")
    else:
        logger.info(f"No active WebSocket found for {ws_client_id} to stop (it might have failed to start, already been stopped, or never existed).")

# Example test functions (main_test_http_full, main_test_ws) are kept for direct script testing if needed.
# These are not typically part of the service's public interface when used by the FastAPI app.
async def main_test_http_full():
    # ... (implementation as before)
    print("Fetching BTCUSDT 1-hour data (linear)...")
    df_btc = await get_historical_klines_bybit(symbol="BTCUSDT", interval="60", limit=5)
    if df_btc is not None:
        if not df_btc.empty: print("BTCUSDT 1-hour data:\n", df_btc.head())
        else: print("No data returned for BTCUSDT (linear).")
    else: print("Failed to fetch BTCUSDT (linear) data.")
    # ... (rest of function)


async def main_test_ws():
    logger.info("Starting main_test_ws: Attempting to start BTCUSDT 1-minute Kline WebSocket (linear)...")
    await start_kline_websocket(symbol="BTCUSDT", interval="1", callback_fn=default_kline_handler, category="linear", testnet=False)

    logger.info("main_test_ws: Simulating run time for 10 seconds to observe WebSocket messages (if pybit subscribe works and network allows)...")
    try:
        await asyncio.sleep(10) # Keep alive to allow WebSocket to receive messages
        logger.info("main_test_ws: Finished waiting period.")
    except KeyboardInterrupt:
        logger.info("main_test_ws: Keyboard interrupt received.")
    finally:
        logger.info("main_test_ws: Attempting to stop BTCUSDT WebSocket (linear)...")
        await stop_kline_websocket(symbol="BTCUSDT", interval="1", category="linear")
        logger.info("main_test_ws: WebSocket test finished.")

if __name__ == "__main__":
    # Configure logging for direct script execution tests
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    # --- Test Historical Data Fetching ---
    # logger.info("Running HTTP test (main_test_http_full)...")
    # asyncio.run(main_test_http_full())

    # --- Test WebSocket Subscription ---
    # The event loop needs to be managed for asyncio if not using asyncio.run() directly for the main task.
    loop = asyncio.get_event_loop()
    try:
        logger.info("Running WebSocket test (main_test_ws) via event loop...")
        loop.run_until_complete(main_test_ws())
    except KeyboardInterrupt:
        logger.info("__main__: Keyboard interrupt received during main_test_ws via event loop.")
    except Exception as e: # Catch-all for other exceptions from main_test_ws
        logger.error(f"__main__: Error in main_test_ws execution: {e}", exc_info=True)
    finally:
        logger.info("__main__: Cleaning up any remaining WS connections...")
        # This cleanup runs after main_test_ws completes or is interrupted.
        stop_tasks = []
        for ws_id_key in list(active_ws_connections.keys()): # Use list() for safe iteration if dict changes
            # Assuming ws_id_key format is "category_symbol_interval"
            parts = ws_id_key.split('_')
            if len(parts) == 3:
                cat, sym, intrvl = parts[0], parts[1], parts[2]
                logger.info(f"__main__: Preparing to stop WS for {sym} ({cat}, {intrvl}) from main cleanup.")
                stop_tasks.append(stop_kline_websocket(symbol=sym, interval=intrvl, category=cat))
            else:
                logger.warning(f"__main__: Could not parse ws_id_key '{ws_id_key}' for cleanup.")

        if stop_tasks:
            logger.info(f"__main__: Executing {len(stop_tasks)} stop tasks for WS cleanup...")
            # Run cleanup tasks within the existing loop if it's still running, or handle appropriately.
            # If loop is already closed/stopped, this might need adjustment or might not run.
            # For simplicity, assuming loop can still run these.
            if not loop.is_closed():
                 loop.run_until_complete(asyncio.gather(*stop_tasks, return_exceptions=True))
                 logger.info("__main__: Finished executing stop tasks for WS cleanup.")
            else:
                 logger.warning("__main__: Event loop was closed before WS cleanup tasks could be run.")
        else:
            logger.info("__main__: No active WS connections found needing cleanup.")

        logger.info("__main__: Script execution finished.")
        # loop.close() # Closing the loop, if appropriate for the script's lifecycle.
                      # Usually done if this is the main entry point and loop won't be used again.
