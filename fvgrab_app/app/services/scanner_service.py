"""
Service module for scanning multiple symbols for Fair Value Gaps (FVGs).

This service iterates over a list of trading symbols, fetches historical
kline data for each using the bybit_service, and then applies FVG detection
logic from fvg_detector to find FVGs. It supports concurrent scanning of symbols.

Key Functions:
- `scan_symbols_for_fvgs`: Main function to orchestrate the scan over multiple symbols for a given interval.
- `_fetch_and_detect_for_pair`: Helper function to process a single symbol.

Potential Future Enhancements (TODOs):
- More sophisticated filtering for "current" or "actionable" FVGs within `_fetch_and_detect_for_pair`.
- Option to use a predefined list of symbols (e.g., from a configuration file or database) if none are provided by the user.
- API-level pagination for scan results if a very large number of FVGs could be returned (though the scanner itself returns all it finds for the given kline_limit).
- More configurable concurrency for `asyncio.gather` (e.g., passing `max_concurrent_tasks` from API).
"""
import asyncio
import logging
import pandas as pd
from typing import Dict, List, Any, Optional
import sys
import os

# --- Path setup for direct script execution ---
if __name__ == "__main__" or not __package__:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_folder_root = os.path.dirname(script_dir) મોટાભાગના કિસ્સાઓમાં, જો તમે આ સ્ક્રિપ્ટ સીધી રીતે ચલાવી રહ્યા હોવ તો, તમારે પ્રોજેક્ટ રુટ ઉમેરવાની જરૂર પડશે.
    project_root_for_app_pkg = os.path.dirname(app_folder_root)
    if project_root_for_app_pkg not in sys.path:
        sys.path.insert(0, project_root_for_app_pkg)
        # print(f"DEBUG: Added {project_root_for_app_pkg} to sys.path for scanner_service.py direct run.")
# --- End Path Setup ---

from app.core_logic.fvg_detector import detect_fvgs
from app.services.bybit_service import get_historical_klines_bybit

logger = logging.getLogger(__name__)
if not logger.handlers:
    if __name__ == '__main__':
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
        # logger.propagate = False # Optional: prevent double logging if root also configured by basicConfig
    else:
        # If imported, assume calling module or main.py configures logging.
        # Add a NullHandler to prevent "No handler found" warnings if no config elsewhere.
        logger.addHandler(logging.NullHandler())


async def _fetch_and_detect_for_pair(
    symbol: str,
    interval: str,
    category: str,
    kline_limit: int,
    fvg_params: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Fetches kline data and detects FVGs for a single symbol-interval pair.

    This is a helper function for `scan_symbols_for_fvgs`. It encapsulates the logic
    for fetching data for one symbol and then running the FVG detection on that data.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT").
        interval: Kline interval (e.g., "60" for 1-hour).
        category: Market category (e.g., "linear").
        kline_limit: Number of klines to fetch.
        fvg_params: Parameters for FVG detection, passed directly to `detect_fvgs`.
            Expected keys include: 'static_threshold_percent', 'use_adaptive_threshold', etc.

    Returns:
        A dictionary containing the symbol and a list of detected FVGs.
        If data fetching fails, returns `None`.
        If FVG detection encounters an error, returns a dict with an 'error' key.
        Structure for success: `{"symbol": symbol, "fvgs": List[Dict]}`
        Structure for detection error: `{"symbol": symbol, "fvgs": [], "error": str}`
    """
    logger.info(f"Scanner: Starting process for {symbol} ({category}, {interval}). Fetching {kline_limit} klines.")

    ohlcv_df = await get_historical_klines_bybit(
        symbol=symbol,
        interval=interval,
        limit=kline_limit,
        category=category
    )

    if ohlcv_df is None:
        logger.error(f"Scanner: Failed to fetch kline data from Bybit for {symbol} (interval: {interval}).")
        return None

    if ohlcv_df.empty or len(ohlcv_df) < 3:
        logger.info(f"Scanner: Not enough kline data for {symbol} ({len(ohlcv_df)} candles, interval: {interval}) for FVG detection.")
        return {"symbol": symbol, "fvgs": []}

    try:
        logger.debug(f"Scanner: Detecting FVGs for {symbol} (interval: {interval}) with params: {fvg_params}")
        # Pass all FVG detection parameters to the core detector function
        detected_fvgs_list = detect_fvgs(
            ohlcv_df,
            static_threshold_percent=fvg_params.get("static_threshold_percent", 0.0),
            use_adaptive_threshold=fvg_params.get("use_adaptive_threshold", False),
            adaptive_threshold_period_UNUSED=fvg_params.get("adaptive_threshold_period_UNUSED", 0),
            use_volume_confirmation=fvg_params.get("use_volume_confirmation", False),
            volume_lookback_period=fvg_params.get("volume_lookback_period", 20),
            volume_factor=fvg_params.get("volume_factor", 1.5),
            min_fvg_price_height=fvg_params.get("min_fvg_price_height", 0.0)
        )

        # TODO: Implement more sophisticated "current FVG" filtering logic if needed.
        #       For example, filter FVGs based on how recently they formed (e.g., within last N candles).
        #       Currently, all FVGs found in the `kline_limit` period are returned.

        if detected_fvgs_list:
            logger.info(f"Scanner: Detected {len(detected_fvgs_list)} FVGs for {symbol} (interval: {interval}).")
            return {"symbol": symbol, "fvgs": detected_fvgs_list}
        else:
            logger.info(f"Scanner: No FVGs detected for {symbol} (interval: {interval}) with given parameters.")
            return {"symbol": symbol, "fvgs": []}

    except ValueError as ve:
        logger.error(f"Scanner: ValueError during FVG detection for {symbol} (interval: {interval}): {ve}")
        return {"symbol": symbol, "fvgs": [], "error": str(ve)}
    except Exception as e:
        logger.exception(f"Scanner: Unexpected error during FVG detection for {symbol} (interval: {interval}): {e}")
        return {"symbol": symbol, "fvgs": [], "error": f"Unexpected error: {type(e).__name__}"}


async def scan_symbols_for_fvgs(
    symbols: List[str],
    interval: str, # Note: This processes one interval at a time. API layer iterates multiple intervals.
    category: str = "linear",
    kline_limit: int = 200,
    fvg_detection_params: Optional[Dict[str, Any]] = None,
    max_concurrent_tasks: int = 5
) -> List[Dict[str, Any]]:
    """
    Scans a list of symbols for Fair Value Gaps (FVGs) for a *single specified interval*,
    processing symbols concurrently.

    Args:
        symbols: A list of trading symbols to scan (e.g., ["BTCUSDT", "ETHUSDT"]).
        interval: The kline interval string for this scan (e.g., "60", "D").
        category: Market category (e.g., "linear", "spot"). Defaults to "linear".
        kline_limit: Number of klines to fetch for each symbol. Defaults to 200.
        fvg_detection_params: Dictionary of parameters for `detect_fvgs`.
                              Defaults to internal `detect_fvgs` defaults if None.
        max_concurrent_tasks: Max symbols to process concurrently. Defaults to 5.
                              TODO: Make this configurable at a higher level if necessary.

    Returns:
        A list of dictionaries. Each dictionary corresponds to a symbol and contains:
        - "symbol" (str): The symbol name.
        - "fvgs" (List[Dict]): A list of detected FVG objects for that symbol.
                               Empty if no FVGs found or if an error occurred during detection for that symbol.
        - "error" (str, optional): An error message if detection failed for that symbol.
        Symbols for which data fetching failed entirely (returned None from helper) are excluded.
    """
    if not symbols:
        logger.warning("Scanner: No symbols provided for scanning.")
        return []

    current_fvg_params = fvg_detection_params if fvg_detection_params is not None else {}
    # TODO: Consider having a default list of symbols if `symbols` is empty,
    #       e.g., from a configuration file or a predefined market cap list.

    logger.info(f"Scanner: Starting FVG scan for {len(symbols)} symbols. Interval: {interval}, Category: {category}, Kline Limit: {kline_limit}.")
    logger.info(f"Scanner: Using FVG detection parameters: {current_fvg_params}")

    results_accumulator = []
    semaphore = asyncio.Semaphore(max_concurrent_tasks)

    async def constrained_fetch_and_detect(symbol_item: str) -> Optional[Dict[str, Any]]:
        async with semaphore:
            return await _fetch_and_detect_for_pair(
                symbol_item, interval, category, kline_limit, current_fvg_params
            )

    tasks = [constrained_fetch_and_detect(sym) for sym in symbols]
    scan_task_outputs = await asyncio.gather(*tasks, return_exceptions=True)

    for output in scan_task_outputs:
        if isinstance(output, Exception):
            logger.error(f"Scanner: A symbol processing task resulted in an unhandled exception: {output}", exc_info=output)
        elif output is not None: # Filter out Nones (total fetch failures)
            results_accumulator.append(output)

    logger.info(f"Scanner: FVG scan for interval '{interval}' completed. Attempted {len(symbols)} symbols.")
    logger.info(f"Scanner: Received results for {len(results_accumulator)} symbols (some may include per-symbol errors).")
    successful_detections = len([r for r in results_accumulator if not r.get("error") and r.get("fvgs")])
    logger.info(f"Scanner: Successfully found FVGs for {successful_detections} symbols on interval '{interval}'.")
    # TODO: Implement pagination or result limiting here if `results_accumulator` can be excessively large.
    #       However, this function processes a single interval; API layer might handle cross-interval pagination.
    return results_accumulator


# --- Example Usage (for direct script testing if needed) ---
async def main_scanner_test():
    """Example test function for the scanner service."""
    test_symbols_linear = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "NONEXISTENTSYMBOL"]

    fvg_params_example = {
        "static_threshold_percent": 0.0,
        "use_adaptive_threshold": True,
        "use_volume_confirmation": True,
        "volume_lookback_period": 10,
        "volume_factor": 1.2,
        "min_fvg_price_height": 0.01
    }

    logger.info("--- Scanner Service: Testing with Linear Symbols (Interval: 15 min) ---")
    # This test will run for a single interval. The API endpoint handles multiple intervals.
    results_linear_15m = await scan_symbols_for_fvgs(
        symbols=test_symbols_linear,
        interval="15",
        category="linear",
        kline_limit=50,
        fvg_detection_params=fvg_params_example,
        max_concurrent_tasks=2
    )

    if results_linear_15m:
        logger.info(f"Scan Results (Linear, 15min, {len(results_linear_15m)} symbols processed):")
        for item in results_linear_15m:
            if "error" in item:
                logger.error(f"  Symbol: {item['symbol']}, Error: {item['error']}")
            else:
                logger.info(f"  Symbol: {item['symbol']}, FVGs Found: {len(item['fvgs'])}")
                if item['fvgs']:
                    logger.info(f"    First FVG details (example): {item['fvgs'][0]}")
    else:
        logger.warning("Scanner test (Linear, 15min) produced no results list.")

    # Example for another interval
    logger.info("--- Scanner Service: Testing with Linear Symbols (Interval: 60 min) ---")
    results_linear_60m = await scan_symbols_for_fvgs(
        symbols=["BTCUSDT", "ETHUSDT"], # Shorter list for second test
        interval="60",
        category="linear",
        kline_limit=30,
        fvg_detection_params={"static_threshold_percent": 0.1}, # Simpler params
        max_concurrent_tasks=2
    )
    if results_linear_60m:
        logger.info(f"Scan Results (Linear, 60min, {len(results_linear_60m)} symbols processed):")
        for item in results_linear_60m:
            # ... (similar logging as above)
            logger.info(f"  Symbol: {item['symbol']}, Result: {item}")


if __name__ == "__main__":
    if not logger.handlers: # Check if handlers are already attached
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            force=True
        )
    logger.info("Executing scanner_service.py directly for testing...")

    asyncio.run(main_scanner_test())
    logger.info("Scanner_service.py direct execution test finished.")
