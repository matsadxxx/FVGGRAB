import pandas as pd
from pybit.unified_trading import HTTP # For v5 API
# from pybit.usdt_perpetual import HTTP as USDTHTTP # For older USDT perpetual
import asyncio
import time # For logging or if any sync operations are needed within async context
from datetime import datetime

# It's good practice to initialize the session once if possible,
# or pass it if multiple calls are made in short succession.
# For simplicity here, we'll create it per call.
# Consider API key/secret for private endpoints later, not needed for kline.

async def get_historical_klines_bybit(symbol: str, interval: str, limit: int = 200, category: str = "linear") -> pd.DataFrame | None:
    """
    Fetches historical kline data from Bybit v5 API.
    :param symbol: Trading symbol, e.g., BTCUSDT
    :param interval: Kline interval (e.g., '1', '5', '60', 'D')
    :param limit: Number of klines to fetch, max 1000 for Bybit v5 get_kline.
    :param category: Category of trading, e.g., 'linear', 'spot', 'inverse'.
    :return: Pandas DataFrame with OHLCV data or None if an error occurs, or empty DataFrame if no data.
    """
    session = HTTP(testnet=False) # Use testnet=True for Bybit testnet

    if limit > 1000:
        # print(f"Warning: Requested limit {limit} exceeds Bybit's max of 1000 per call. Capping to 1000.")
        limit = 1000

    try:
        # print(f"Fetching Bybit klines: Category='{category}', Symbol='{symbol}', Interval='{interval}', Limit={limit}")
        response = session.get_kline(
            category=category,
            symbol=symbol,
            interval=interval,
            limit=limit
        )

        if response and response.get('retCode') == 0:
            klines_data = response.get('result', {}).get('list', [])
            if not klines_data:
                # print(f"No kline data returned for {symbol} with interval {interval} in category {category}.")
                return pd.DataFrame() # Return empty DataFrame for no data

            # Kline data format from Bybit: [timestamp, open, high, low, close, volume, turnover]
            df = pd.DataFrame(klines_data, columns=[
                'time', 'open', 'high', 'low', 'close', 'volume', 'turnover'
            ])

            # Convert timestamp to datetime, ensure numeric types
            df['time'] = pd.to_datetime(df['time'].astype(int), unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                df[col] = pd.to_numeric(df[col], errors='coerce') # errors='coerce' will turn non-numeric to NaN

            df = df[['time', 'open', 'high', 'low', 'close', 'volume']] # Select desired columns

            # Bybit v5 API get_kline returns data in descending order (newest first)
            # Sort to ascending order (oldest first) for typical analysis usage
            df = df.sort_values(by='time', ascending=True).reset_index(drop=True)

            return df
        else:
            # print(f"Error fetching klines from Bybit for {symbol} (Category: {category}): {response.get('retMsg')} (Code: {response.get('retCode')})")
            return None

    except Exception as e:
        # print(f"An exception occurred while fetching klines for {symbol} (Category: {category}): {e}")
        return None

async def main_test_http(): # Renamed from main_test to avoid confusion
    print("Fetching BTCUSDT 1-hour data (linear)...")
    df_btc = await get_historical_klines_bybit(symbol="BTCUSDT", interval="60", limit=5)
    if df_btc is not None:
        if not df_btc.empty:
            print("BTCUSDT 1-hour data:")
            print(df_btc.head())
        else:
            print("No data returned for BTCUSDT (linear).")
    else:
        print("Failed to fetch BTCUSDT (linear) data due to an API error or exception.")

    print("\nFetching ETHUSDT 1-day data (spot)...")
    df_eth = await get_historical_klines_bybit(symbol="ETHUSDT", interval="D", limit=3, category="spot")
    if df_eth is not None:
        if not df_eth.empty:
            print("ETHUSDT 1-day (spot) data:")
            print(df_eth.head())
        else:
            print("No data returned for ETHUSDT (spot).")
    else:
        print("Failed to fetch ETHUSDT (spot) data due to an API error or exception.")

    print("\nFetching non_existent_symbol data (should fail or return empty)...")
    df_non_existent = await get_historical_klines_bybit(symbol="NONEXISTENTPAIR", interval="60", limit=5)
    if df_non_existent is not None:
        if not df_non_existent.empty:
            print("Non-existent pair data (unexpected):")
            print(df_non_existent.head())
        else:
            print("No data returned for non-existent pair (as expected if API handles gracefully).")
    else:
        print("Failed to fetch non-existent pair data (as expected for API error).")

# --- WebSocket Implementation ---
from pybit.unified_trading import WebSocket as UnifiedWebSocket
import logging

# Configure basic logging for the service
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Store active websockets to manage them
active_ws_connections = {}

def default_kline_handler(message):
    """Default handler for processing kline data from WebSocket."""
    data = message.get("data", [])
    topic = message.get('topic', '')
    symbol = topic.split('.')[-1] if topic else "UnknownSymbol" # basic symbol extraction

    if data:
        kline = data[0] # Kline data is usually in a list from Bybit WS
        logger.info(f"WS Kline Received: Symbol={symbol}, "
                    f"Time={pd.to_datetime(kline.get('start'), unit='ms')}, "
                    f"Open={kline.get('open')}, High={kline.get('high')}, Low={kline.get('low')}, Close={kline.get('close')}, "
                    f"Volume={kline.get('volume')}, Confirm={kline.get('confirm')}")
    else:
        logger.info(f"WS Message (no data field or empty data for {symbol}): {message}")


async def start_kline_websocket(symbol: str, interval: str, callback_fn: callable, testnet: bool = False, category: str = "linear"):
    """
    Starts a Bybit WebSocket connection for kline data.
    :param symbol: Trading symbol, e.g., BTCUSDT
    :param interval: Kline interval (e.g., '1', '5', '60', 'D').
    :param callback_fn: Function to call with received messages.
    :param testnet: Whether to use the Bybit testnet.
    :param category: Market category ('linear', 'spot', 'inverse').
    """
    ws_client_id = f"{category}_{symbol}_{interval}"
    if ws_client_id in active_ws_connections and active_ws_connections[ws_client_id].is_connected():
        logger.info(f"WebSocket for {ws_client_id} is already running.")
        return

    # For v5, channel_type is 'linear', 'spot', or 'inverse'
    ws = UnifiedWebSocket(testnet=testnet, channel_type=category)

    topic = f"kline.{interval}.{symbol}"

    logger.info(f"Attempting to start WebSocket for {topic} on {'testnet' if testnet else 'mainnet'} using channel_type '{category}'...")

    try:
        ws.subscribe(
            [topic],  # Pass the topic as a list
            callback=callback_fn
        )
        active_ws_connections[ws_client_id] = ws
        logger.info(f"Subscribed to topics {topic}. Callback handler is '{callback_fn.__name__}'. Waiting for messages (environment permitting).")
        # pybit's WebSocket client runs in background threads. No ws.run_forever() needed here.
    except Exception as e:
        logger.error(f"Error during WebSocket subscription to {topic}: {e}", exc_info=True)


async def stop_kline_websocket(symbol: str, interval: str, category: str = "linear"):
    """Stops a specific kline WebSocket connection."""
    ws_client_id = f"{category}_{symbol}_{interval}"
    if ws_client_id in active_ws_connections:
        logger.info(f"Attempting to stop WebSocket for {ws_client_id}...")
        ws = active_ws_connections.pop(ws_client_id)
        if hasattr(ws, 'exit') and callable(ws.exit):
            try:
                ws.exit()
                logger.info(f"WebSocket for {ws_client_id} stop command issued.")
            except Exception as e:
                logger.error(f"Exception while stopping WebSocket for {ws_client_id}: {e}", exc_info=True)
        else:
            logger.warning(f"WebSocket for {ws_client_id} does not have a direct exit method. Relaying on GC or program exit.")
    else:
        logger.info(f"No active WebSocket found for {ws_client_id} to stop.")

async def main_test_ws():
    logger.info("Attempting to start BTCUSDT 1-minute Kline WebSocket (linear)...")
    # Using linear as default category for BTCUSDT futures
    await start_kline_websocket(symbol="BTCUSDT", interval="1", callback_fn=default_kline_handler, category="linear", testnet=False)

    logger.info("Simulating run time for 10 seconds to observe WebSocket messages (if network allows)...")
    try:
        for i in range(10):
            # Check connection status if possible and meaningful
            # ws_id = f"linear_BTCUSDT_1"
            # if ws_id in active_ws_connections and active_ws_connections[ws_id].is_connected():
            #    logger.info(f"WS {ws_id} is connected. Iteration {i+1}/10.")
            # else:
            #    logger.info(f"WS {ws_id} is NOT connected or found. Iteration {i+1}/10.")
            await asyncio.sleep(1)
        logger.info("Finished waiting period for WebSocket messages.")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received during WS test.")
    finally:
        logger.info("Attempting to stop BTCUSDT WebSocket (linear)...")
        await stop_kline_websocket(symbol="BTCUSDT", interval="1", category="linear")
        logger.info("WebSocket test (linear) finished.")

if __name__ == "__main__":
    # To test historical data fetching:
    # asyncio.run(main_test_http())

    # To test WebSocket subscriptions:
    loop = asyncio.get_event_loop()
    try:
        logger.info("Starting WebSocket test scenario...")
        loop.run_until_complete(main_test_ws())
    except KeyboardInterrupt:
        logger.info("Main WebSocket test loop interrupted by user.")
    except Exception as e:
        logger.error(f"Error in main_test_ws execution: {e}", exc_info=True)
    finally:
        logger.info("Main block: Cleaning up any remaining WS connections...")
        # This cleanup is a bit tricky due to async nature and potential partial execution
        # A more robust solution would involve a central manager for WebSocket tasks

        # Gather all stop tasks
        stop_tasks = []
        for ws_id in list(active_ws_connections.keys()): # list() to avoid dict size change during iteration
            parts = ws_id.split('_')
            if len(parts) == 3: # category_symbol_interval
                category, symbol, interval_val = parts[0], parts[1], parts[2]
                logger.info(f"Preparing to stop WS for {symbol} ({category}, {interval_val}) from main cleanup.")
                # Add stop task to a list to run them concurrently
                stop_tasks.append(stop_kline_websocket(symbol=symbol, interval=interval_val, category=category))

        if stop_tasks:
            logger.info(f"Executing {len(stop_tasks)} stop tasks for WS cleanup...")
            loop.run_until_complete(asyncio.gather(*stop_tasks, return_exceptions=True)) # return_exceptions to see errors
            logger.info("Finished executing stop tasks for WS cleanup.")
        else:
            logger.info("No active WS connections found needing cleanup in main.")

        # loop.close() # Usually not needed if run_until_complete is the last call related to this loop
        logger.info("Main script execution finished.")
