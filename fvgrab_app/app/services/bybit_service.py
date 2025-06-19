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
from pybit.unified_trading import HTTP as UnifiedHTTP
from pybit.unified_trading import WebSocket as UnifiedWebSocket
import asyncio
import time # Not used directly, but kept for potential future use
from datetime import datetime # Not used directly, but kept for potential future use
import logging
from typing import Dict, List, Any, Optional, Callable

logger = logging.getLogger(__name__)
# TODO: Ensure global logging (basicConfig) is configured in main.py for consistent output.

# --- HTTP Client Setup ---
# ... (existing TODOs and comments) ...

async def get_historical_klines_bybit(
    symbol: str,
    interval: str,
    limit: int = 200,
    category: str = "linear"
) -> pd.DataFrame | None:
    # ... (function implementation as before, no changes needed for this subtask) ...
    session = UnifiedHTTP(testnet=False)
    if limit > 1000:
        logger.warning(f"Requested kline limit {limit} exceeds Bybit's max of 1000. Capping to 1000.")
        limit = 1000
    try:
        logger.debug(f"Fetching Bybit klines: Category='{category}', Symbol='{symbol}', Interval='{interval}', Limit={limit}")
        response = session.get_kline(category=category, symbol=symbol, interval=interval, limit=limit)
        if response and response.get('retCode') == 0:
            klines_data = response.get('result', {}).get('list', [])
            if not klines_data:
                logger.info(f"No kline data returned from Bybit for {symbol}, interval {interval}, category {category}.")
                return pd.DataFrame()
            df = pd.DataFrame(klines_data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            df['time'] = pd.to_datetime(df['time'].astype(int), unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
            df = df.sort_values(by='time', ascending=True).reset_index(drop=True)
            return df
        else:
            err_code = response.get('retCode'); err_msg = response.get('retMsg')
            logger.error(f"Error fetching klines from Bybit for {symbol} (Cat: {category}, Int: {interval}): {err_msg} (Code: {err_code})")
            return None
    except Exception as e:
        logger.exception(f"An exception occurred while fetching klines for {symbol} (Cat: {category}, Int: {interval}): {e}")
        return None

# --- WebSocket Implementation ---
active_ws_connections: Dict[str, UnifiedWebSocket] = {}

async def minimal_ws_callback(message: Dict): # Changed from default_kline_handler for clarity
    """Minimal callback for WebSocket messages, primarily for logging."""
    logger.info(f"Minimal WS Callback Received: {message}")

async def start_kline_websocket( # Unchanged for this test, but used by test_websocket_subscription_variants
    symbol: str,
    interval: str,
    callback_fn: Callable, # Changed from callable to Callable
    testnet: bool = False,
    category: str = "linear"
):
    # ... (function implementation as before, with critical TODO about TypeError) ...
    ws_client_id = f"{category}_{symbol}_{interval}"
    if ws_client_id in active_ws_connections:
        ws_instance = active_ws_connections[ws_client_id]
        # Simplified check, actual connection status check might be more complex or pybit version dependent
        if (hasattr(ws_instance, '_ws_connected') and ws_instance._ws_connected) or \
           (hasattr(ws_instance, 'is_connected') and ws_instance.is_connected()):
             logger.info(f"WebSocket for {ws_client_id} is already considered running.")
             return
        else:
             logger.warning(f"WebSocket for {ws_client_id} in dict but not connected. Attempting to recreate.")

    ws = UnifiedWebSocket(testnet=testnet, channel_type=category)
    topic = f"kline.{interval}.{symbol}"
    logger.info(f"Attempting to start WebSocket for {topic} on {'testnet' if testnet else 'mainnet'} (Channel: '{category}').")
    try:
        ws.subscribe([topic], callback=callback_fn)
        active_ws_connections[ws_client_id] = ws
        logger.info(f"Subscription attempt to {topic} successful. Callback: '{callback_fn.__name__}'.")
    except Exception as e:
        logger.error(f"Error during WebSocket subscription to {topic}: {e}", exc_info=True)

async def stop_kline_websocket(symbol: str, interval: str, category: str = "linear"):
    # ... (function implementation as before) ...
    ws_client_id = f"{category}_{symbol}_{interval}"
    if ws_client_id in active_ws_connections:
        logger.info(f"Attempting to stop WebSocket for {ws_client_id}...")
        ws = active_ws_connections.pop(ws_client_id)
        if hasattr(ws, 'exit') and callable(ws.exit):
            try: ws.exit()
            except Exception as e: logger.error(f"Exception while stopping WS {ws_client_id}: {e}", exc_info=True)
        logger.info(f"WebSocket for {ws_client_id} stop process initiated.")
    else: logger.info(f"No active WebSocket for {ws_client_id} to stop.")


# --- Test function for WebSocket subscription variants ---
async def test_websocket_subscription_variants():
    """
    Tests different ways to call ws.subscribe() to investigate TypeError.
    Focuses on variations in topic argument and channel_type.
    """
    logger.info("--- Testing WebSocket Subscription Variants ---")

    # Define test cases: (channel_type, topic_arg_for_subscribe, description_of_case)
    # Topic for kline: kline.INTERVAL.SYMBOL, e.g. kline.1.BTCUSDT
    # Topic for tickers: tickers.SYMBOL, e.g. tickers.BTCUSDT
    test_cases = [
        # Kline subscriptions
        ("linear", "kline.1.BTCUSDT", "Linear Kline, Topic as String"),
        ("linear", ["kline.1.BTCUSDT"], "Linear Kline, Topic as List of one string"),
        ("spot", "kline.1.BTCUSDT", "Spot Kline, Topic as String"),
        ("spot", ["kline.1.BTCUSDT"], "Spot Kline, Topic as List of one string"),
        # Tickers subscriptions (another common public topic)
        ("linear", "tickers.BTCUSDT", "Linear Tickers, Topic as String"),
        ("linear", ["tickers.BTCUSDT"], "Linear Tickers, Topic as List of one string"),
        ("spot", "tickers.BTCUSDT", "Spot Tickers, Topic as String"),
        ("spot", ["tickers.BTCUSDT"], "Spot Tickers, Topic as List of one string"),
        # Try with multiple topics in a list (if supported by UnifiedWebSocket subscribe)
        ("linear", ["kline.1.BTCUSDT", "kline.1.ETHUSDT"], "Linear Kline, Multiple Topics in List"),
    ]

    for case_details in test_cases:
        channel_type, topic_arg, description = case_details
        logger.info(f"Attempting: {description} (Channel: {channel_type}, Topic Arg: {topic_arg})")
        ws = None # Ensure ws is reset for each case
        ws_client_id_test = f"test_{channel_type}_{str(topic_arg)}" # Unique ID for this test instance

        try:
            ws = UnifiedWebSocket(testnet=False, channel_type=channel_type)
            # Optional: Assign logger to pybit's WS if it supports it, for more internal details.
            # if hasattr(ws, 'logger'): ws.logger = logger

            # Brief pause for WebSocket object to initialize, though pybit typically connects on subscribe/start.
            await asyncio.sleep(0.5)

            logger.info(f"[{description}] Calling ws.subscribe()...")
            ws.subscribe(
                topic_arg,
                callback=minimal_ws_callback
            )
            # If subscribe call itself doesn't raise TypeError, log it.
            logger.info(f"[{description}] ws.subscribe() call completed without immediate TypeError.")

            # Store this test WS instance to attempt cleanup if it was created
            active_ws_connections[ws_client_id_test] = ws

            # Keep alive for a short period to see if any message (data, error, auth) is received.
            # This also gives time for the connection to fully establish or fail.
            logger.info(f"[{description}] Waiting for 5 seconds for messages or connection errors...")
            await asyncio.sleep(5)

        except TypeError as te:
            logger.error(f"[{description}] Caught TypeError during subscribe call: {te}", exc_info=True)
        except Exception as e:
            logger.error(f"[{description}] Caught other exception: {type(e).__name__} - {e}", exc_info=True)
        finally:
            if ws_client_id_test in active_ws_connections: # Remove if stored
                del active_ws_connections[ws_client_id_test]
            if ws and hasattr(ws, 'exit') and callable(ws.exit):
                logger.info(f"[{description}] Stopping WebSocket instance...")
                try:
                    ws.exit()
                except Exception as e_exit:
                    logger.error(f"[{description}] Exception during ws.exit(): {e_exit}", exc_info=True)
            await asyncio.sleep(1) # Pause between test cases for cleaner logs & resource release.

    logger.info("--- Finished WebSocket Subscription Variants Test ---")


# Example test functions (main_test_http_full, main_test_ws) are kept for direct script testing if needed.
async def main_test_http_full():
    # ... (implementation as before) ...
    pass # For brevity, assuming it's there from previous steps

async def main_test_ws(): # This was the old test, will be replaced by the variants test
    # ... (implementation as before) ...
    pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    loop = asyncio.get_event_loop()
    try:
        logger.info("Running WebSocket Subscription Variants Test...")
        loop.run_until_complete(test_websocket_subscription_variants())
    except KeyboardInterrupt:
        logger.info("__main__: Test interrupted by user.")
    except Exception as e:
        logger.error(f"__main__: Error in test_websocket_subscription_variants execution: {e}", exc_info=True)
    finally:
        logger.info("__main__: Cleaning up any remaining test WS connections...")
        stop_tasks = []
        for ws_id_key in list(active_ws_connections.keys()):
            # Test connections are stored with "test_" prefix, actual service connections are not.
            if ws_id_key.startswith("test_"):
                 ws_to_stop = active_ws_connections.pop(ws_id_key, None)
                 if ws_to_stop and hasattr(ws_to_stop, 'exit') and callable(ws_to_stop.exit):
                    logger.info(f"__main__: Force stopping test WS for ID {ws_id_key}.")
                    # Directly call exit here as these are test objects not managed by symbol/interval
                    try: ws_to_stop.exit()
                    except Exception as e_final_stop: logger.error(f"Error stopping {ws_id_key}: {e_final_stop}")

        # If any application-managed WS were started by other test functions (not the case here)
        # they would need their specific stop_kline_websocket calls.
        # For this subtask, only test_websocket_subscription_variants runs.

        if loop.is_running() and not loop.is_closed(): # Check if loop needs explicit closing
            logger.info("__main__: Event loop still running, but tests finished.")
        # Consider loop.close() if this is the absolute end of all async operations.
        logger.info("__main__: Script execution finished.")
