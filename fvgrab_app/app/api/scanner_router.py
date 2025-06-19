"""
API router for FVG (Fair Value Gap) Symbol Scanner endpoints.

This module defines FastAPI routes for:
- Running scans across multiple symbols and intervals to find current FVGs.
  It leverages the `scanner_service` for concurrent data fetching and FVG detection.
"""
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging

from app.services import scanner_service
# TODO: Add import for logger if specific API level logging is needed beyond FastAPI's default.

logger = logging.getLogger(__name__) # Standard Python logger
# Ensure logging is configured in main.py or at application startup.

router = APIRouter()

class ScannerParams(BaseModel):
    """
    Pydantic model defining the parameters for an FVG scan request.
    This model is used as the request body for the `/scanner/run-scan` endpoint.
    It includes lists of symbols and intervals to scan, market category,
    data fetching limits, and detailed FVG detection parameters.
    """
    symbols: List[str] = Field(
        ...,
        min_length=1,
        description="List of trading symbols to scan, e.g., ['BTCUSDT', 'ETHUSDT']",
        example=["BTCUSDT", "ETHUSDT"]
    )
    intervals: List[str] = Field(
        ...,
        min_length=1,
        description="List of kline intervals (Bybit format), e.g., ['60', 'D'] for 1-hour and daily.",
        example=["60", "240", "D"]
    )
    category: str = Field(
        "linear",
        description="Bybit market category: 'linear' (USDT perps), 'spot', 'inverse'.",
        example="linear"
    )
    kline_limit_per_scan: int = Field(
        30,  # Default to a smaller number for scanner, focusing on recent FVGs
        ge=10,
        le=200, # Max reasonable for "current" FVG scan per pair; Bybit API max is 1000 for general fetch
        description="Number of recent klines to fetch per symbol/interval combination for FVG detection."
    )

    # FVG Detection Parameters (mirroring those in fvg_detector.detect_fvgs)
    static_threshold_percent: float = Field(
        0.0, ge=0.0,
        description="Static threshold for FVG middle candle body % (0.0 to disable)."
    )
    use_adaptive_threshold: bool = Field(
        False,
        description="Use adaptive threshold for FVG detection (based on cumulative avg body size)."
    )
    adaptive_threshold_period_UNUSED: int = Field( # TODO: Remove or implement if adaptive logic changes
        0,
        description="Placeholder for future adaptive FVG threshold period (currently unused by detector)."
    )
    use_volume_confirmation: bool = Field(
        False,
        description="Filter FVGs based on volume confirmation of the middle candle."
    )
    volume_lookback_period: int = Field(
        20, ge=1,
        description="Lookback period for calculating average volume for confirmation."
    )
    volume_factor: float = Field(
        1.5, ge=0.1, # Factor must be positive
        description="Volume factor for confirmation (middle candle_vol > avg_vol * factor)."
    )
    min_fvg_price_height: float = Field(
        0.0, ge=0.0,
        description="Minimum absolute price height for a valid FVG (in quote currency units, 0.0 to disable)."
    )
    # TODO: Consider adding max_concurrent_symbol_tasks to ScannerParams if user control is desired.


@router.post("/scanner/run-scan", response_model=List[Dict[str, Any]], tags=["Symbol Scanner"])
async def run_symbol_scan(params: ScannerParams = Body(...)):
    """
    Scans multiple symbols across multiple intervals for current Fair Value Gaps (FVGs).

    This endpoint accepts a list of symbols and intervals, along with various FVG
    detection parameters. For each interval specified, it concurrently scans all
    provided symbols.

    **Request Body (`ScannerParams`):**
    - `symbols`: List of symbol strings (e.g., `["BTCUSDT", "ETHUSDT"]`).
    - `intervals`: List of interval strings (e.g., `["60", "240", "D"]`).
    - `category`: Market category (default: "linear").
    - `kline_limit_per_scan`: Number of recent klines to fetch for each scan (default: 30).
    - FVG detection parameters (static_threshold_percent, use_adaptive_threshold, etc.).

    **Response:**
    - A list of dictionaries. Each dictionary represents the result for a symbol on a
      specific interval and includes:
        - `symbol` (str): The symbol scanned.
        - `interval_scanned` (str): The interval for this part of the scan.
        - `fvgs` (List[Dict]): A list of detected FVG objects. Empty if no FVGs found.
        - `error` (str, optional): An error message if FVG detection failed for this symbol/interval.
    - If data fetching from Bybit fails for all symbols/intervals (e.g., due to API restrictions),
      an empty list `[]` might be returned. If the service call itself fails unexpectedly for
      an interval, an item with `{"error_for_interval": ..., "detail": ...}` may be included.

    **Note on Environment Limitations:**
    - Due to current sandbox environment restrictions, Bybit API calls for live data fetching
      are blocked (resulting in 403 errors from Bybit). This endpoint will likely return
      results indicating these data fetching failures (e.g., empty FVG lists or error messages
      per symbol) rather than actual FVGs from live market data.
      The endpoint's structure and parameter handling are tested, but end-to-end FVG
      detection with live data is not possible in this restricted environment.
    """
    # TODO: Implement API-level pagination for the overall results if a scan across many
    #       symbols and intervals could produce an extremely large response.
    #       Currently, pagination is not implemented; all results are returned.

    logger.info(f"API Call /scanner/run-scan received with params: {params.model_dump_json(indent=2, exclude_none=True)}")

    all_results: List[Dict[str, Any]] = []

    # Prepare FVG detection parameters dictionary to pass to the scanner service.
    # This ensures only relevant FVG detection settings are passed.
    fvg_detection_params_for_service = {
        "static_threshold_percent": params.static_threshold_percent,
        "use_adaptive_threshold": params.use_adaptive_threshold,
        "adaptive_threshold_period_UNUSED": params.adaptive_threshold_period_UNUSED,
        "use_volume_confirmation": params.use_volume_confirmation,
        "volume_lookback_period": params.volume_lookback_period,
        "volume_factor": params.volume_factor,
        "min_fvg_price_height": params.min_fvg_price_height
    }

    # Iterate through each specified interval and scan all symbols for that interval.
    for interval_to_scan in params.intervals:
        logger.info(f"Scanner endpoint: Processing interval '{interval_to_scan}' for {len(params.symbols)} symbols.")
        try:
            interval_results = await scanner_service.scan_symbols_for_fvgs(
                symbols=params.symbols,
                interval=interval_to_scan,
                category=params.category,
                kline_limit=params.kline_limit_per_scan, # Corrected from data_limit_per_scan
                fvg_detection_params=fvg_detection_params_for_service
                # max_concurrent_tasks is handled by scanner_service's default or could be exposed.
            )

            # Augment results with the interval they belong to for clarity in the combined response.
            for symbol_result in interval_results:
                if isinstance(symbol_result, dict): # Ensure it's a dict before adding key
                    symbol_result["interval_scanned"] = interval_to_scan

            all_results.extend(interval_results)

        except Exception as e:
            logger.exception(f"Scanner endpoint: Unexpected critical error during scan for interval {interval_to_scan}: {e}")
            # This represents a failure in the overall scanning process for an interval,
            # not just an issue with a single symbol within that scan.
            all_results.append({
                "error_for_interval": interval_to_scan,
                "detail": f"A critical error occurred while processing scan for interval {interval_to_scan}: {type(e).__name__} - {str(e)}"
            })
            # Depending on desired behavior, might raise HTTPException here to terminate early,
            # or continue to process other intervals. Current: continue and report error for this interval.

    if not all_results:
        logger.warning("Scanner endpoint: No results or errors reported from scanner service across all symbols and intervals.")

    logger.info(f"Scanner endpoint: Scan completed. Returning {len(all_results)} total result items (each for a symbol/interval pair or an interval-level error).")
    return all_results
