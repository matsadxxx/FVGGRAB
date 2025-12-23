"""
API router for FVG (Fair Value Gap) related endpoints.

This module defines FastAPI routes for:
- Fetching historical FVG data.
- Streaming live FVG data via WebSockets.
- Running backtests of FVG strategies.

It uses services for Bybit API interaction and core logic for FVG detection and backtesting.
Includes a ConnectionManager for handling WebSocket clients.
"""
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import pandas as pd
import asyncio
from collections import deque
import logging

from app.services import bybit_service
from app.core_logic import fvg_detector, backtester # Added backtester

logger = logging.getLogger(__name__)
# Ensure logging is configured in main.py or at application startup.

router = APIRouter()

# --- General Test Endpoint ---
@router.get("/test", tags=["General"])
async def test_route():
    """A simple test endpoint to confirm the API router is working."""
    return {"message": "FVG API router is working!"}

# --- Historical FVG Endpoint ---
@router.get("/fvgs/historical", response_model=List[Dict[str, Any]], tags=["FVG Analysis"])
async def get_historical_fvgs(
    symbol: str = Query(..., description="Trading symbol, e.g., BTCUSDT", example="BTCUSDT"),
    interval: str = Query(..., description="Kline interval (Bybit format), e.g., '60' for 1h, 'D' for 1 day", example="60"),
    limit: int = Query(200, description="Number of klines to fetch (max 1000 for Bybit)", ge=1, le=1000),
    category: str = Query("linear", description="Bybit category: 'linear', 'spot', 'inverse'", example="linear"),
    # FVG Detection Parameters
    static_threshold_percent: Optional[float] = Query(0.0, alias="fvg_static_threshold_percent", description="Static threshold for FVG middle candle body %", ge=0.0),
    use_adaptive_threshold: Optional[bool] = Query(False, alias="fvg_use_adaptive_threshold", description="Use adaptive threshold for FVG detection"),
    use_volume_confirmation: Optional[bool] = Query(False, alias="fvg_use_volume_confirmation", description="Use volume confirmation for FVG"),
    volume_lookback_period: Optional[int] = Query(20, alias="fvg_volume_lookback_period", ge=5, description="Lookback period for volume average"),
    volume_factor: Optional[float] = Query(1.5, alias="fvg_volume_factor", ge=1.0, description="Factor for volume confirmation"),
    min_fvg_price_height: Optional[float] = Query(0.0, alias="fvg_min_price_height", ge=0.0, description="Minimum price height for a valid FVG")
):
    """
    Fetches historical kline data for a symbol and detects Fair Value Gaps (FVGs)
    using specified detection parameters.
    """
    logger.info(f"API Call /fvgs/historical: symbol={symbol}, interval={interval}, limit={limit}, category={category}")

    ohlcv_df = await bybit_service.get_historical_klines_bybit(
        symbol=symbol, interval=interval, limit=limit, category=category
    )

    if ohlcv_df is None:
        logger.warning(f"Failed to fetch kline data from Bybit for {symbol}.")
        raise HTTPException(status_code=503, detail=f"Failed to fetch kline data from Bybit for {symbol}.")
    if ohlcv_df.empty:
        logger.info(f"No kline data for {symbol}. Returning empty list of FVGs.")
        return []

    try:
        # Ensure defaults are handled if Optional query params are not provided
        fvgs = fvg_detector.detect_fvgs(
            ohlcv_df,
            static_threshold_percent=static_threshold_percent if static_threshold_percent is not None else 0.0,
            use_adaptive_threshold=use_adaptive_threshold if use_adaptive_threshold is not None else False,
            use_volume_confirmation=use_volume_confirmation if use_volume_confirmation is not None else False,
            volume_lookback_period=volume_lookback_period if volume_lookback_period is not None else 20,
            volume_factor=volume_factor if volume_factor is not None else 1.5,
            min_fvg_price_height=min_fvg_price_height if min_fvg_price_height is not None else 0.0
        )
        logger.info(f"Detected {len(fvgs)} FVGs for {symbol}.")
        return fvgs
    except ValueError as e:
        logger.error(f"ValueError in FVG detection for {symbol}: {e}.")
        raise HTTPException(status_code=400, detail=f"Invalid data for FVG detection: {str(e)}")
    except Exception as e:
        logger.exception(f"Unexpected error during FVG detection for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during FVG detection.")

# --- WebSocket Connection Manager & FVG Streaming ---
class ConnectionManager:
    # ... (Implementation as before, no changes needed for this class here) ...
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    async def connect(self, websocket: WebSocket, stream_id: str):
        await websocket.accept()
        if stream_id not in self.active_connections: self.active_connections[stream_id] = []
        self.active_connections[stream_id].append(websocket)
        logger.info(f"Client connected to stream: {stream_id}. Total clients: {len(self.active_connections[stream_id])}")
    def disconnect(self, websocket: WebSocket, stream_id: str) -> bool:
        stream_was_emptied = False
        if stream_id in self.active_connections and websocket in self.active_connections[stream_id]:
            self.active_connections[stream_id].remove(websocket)
            logger.info(f"Client disconnected from stream: {stream_id}.")
            if not self.active_connections[stream_id]:
                del self.active_connections[stream_id]; logger.info(f"Stream {stream_id} removed."); stream_was_emptied = True
        if not self.active_connections.get(stream_id) and not stream_was_emptied: stream_was_emptied = True
        return stream_was_emptied
    async def broadcast_to_stream(self, stream_id: str, message: Any):
        if stream_id in self.active_connections:
            results = await asyncio.gather(*[conn.send_json(message) for conn in self.active_connections[stream_id]], return_exceptions=True)
            for res in results:
                if isinstance(res, Exception): logger.error(f"Error broadcasting in stream {stream_id}: {res}")
    def get_client_count_for_stream(self, stream_id: str) -> int:
        return len(self.active_connections.get(stream_id, []))

manager = ConnectionManager()
stream_kline_buffers: Dict[str, deque] = {}

def _kline_list_to_df(kline_list: List[Dict]) -> pd.DataFrame:
    # ... (Implementation as before, no changes needed here) ...
    if not kline_list: return pd.DataFrame()
    df = pd.DataFrame(kline_list)
    df = df.rename(columns={'start': 'time', 'volume': 'volume_orig'})
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    numeric_cols = ['open', 'high', 'low', 'close', 'volume_orig']
    for col in numeric_cols: df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.rename(columns={'volume_orig': 'volume'})
    required_detector_columns = ['time', 'open', 'high', 'low', 'close', 'volume']
    for col in required_detector_columns:
        if col not in df.columns: df[col] = 0.0; logger.warning(f"Column '{col}' missing, filled with 0.0.")
    return df[required_detector_columns].copy()

async def bybit_kline_processor_factory(stream_id: str, detection_params: Dict[str, Any]) -> callable:
    # ... (Modified to accept a dict of detection_params) ...
    if stream_id not in stream_kline_buffers:
        stream_kline_buffers[stream_id] = deque(maxlen=10)
        logger.info(f"Initialized kline buffer for stream_id: {stream_id}")

    async def process_kline_message(message: Dict):
        kline_data_list = message.get('data', [])
        for kline_item in kline_data_list:
            if kline_item.get('confirm', False):
                required_fields = ['start', 'open', 'high', 'low', 'close', 'volume']
                if not all(field in kline_item for field in required_fields): continue
                buffer = stream_kline_buffers.get(stream_id)
                if buffer is None: return
                buffer.append(kline_item)
                if len(buffer) >= 3:
                    ohlcv_df = _kline_list_to_df(list(buffer))
                    if not ohlcv_df.empty and len(ohlcv_df) >=3:
                        try:
                            # Pass all FVG detection params
                            fvgs = fvg_detector.detect_fvgs(ohlcv_df, **detection_params)
                            if fvgs:
                                latest_kline_time_in_df = ohlcv_df['time'].iloc[-1]
                                new_fvgs = [fvg for fvg in fvgs if pd.to_datetime(fvg['trigger_candle_time']) == latest_kline_time_in_df]
                                if new_fvgs:
                                    logger.info(f"New FVGs for {stream_id}: {new_fvgs}")
                                    await manager.broadcast_to_stream(stream_id, {"type": "fvg_update", "data": new_fvgs})
                        except Exception as e: logger.exception(f"Error in FVG detection for stream {stream_id}: {e}")
    return process_kline_message

@router.websocket("/ws/fvg-stream/{category}/{symbol}/{interval}")
async def websocket_fvg_endpoint(
    websocket: WebSocket, category: str, symbol: str, interval: str,
    static_threshold_percent: Optional[float] = Query(0.0, alias="fvg_static_threshold_percent", ge=0.0),
    use_adaptive_threshold: Optional[bool] = Query(False, alias="fvg_use_adaptive_threshold"),
    use_volume_confirmation: Optional[bool] = Query(False, alias="fvg_use_volume_confirmation"),
    volume_lookback_period: Optional[int] = Query(20, alias="fvg_volume_lookback_period", ge=5),
    volume_factor: Optional[float] = Query(1.5, alias="fvg_volume_factor", ge=1.0),
    min_fvg_price_height: Optional[float] = Query(0.0, alias="fvg_min_price_height", ge=0.0)
):
    # Construct detection_params dict for the factory
    detection_params = {
        "static_threshold_percent": static_threshold_percent if static_threshold_percent is not None else 0.0,
        "use_adaptive_threshold": use_adaptive_threshold if use_adaptive_threshold is not None else False,
        "use_volume_confirmation": use_volume_confirmation if use_volume_confirmation is not None else False,
        "volume_lookback_period": volume_lookback_period if volume_lookback_period is not None else 20,
        "volume_factor": volume_factor if volume_factor is not None else 1.5,
        "min_fvg_price_height": min_fvg_price_height if min_fvg_price_height is not None else 0.0
    }
    # Stream ID should be unique for the combination of stream source and processing parameters
    param_values_str = "_".join(str(v) for v in detection_params.values()) # Simple way to make stream_id unique to params
    stream_id = f"{category}_{symbol}_{interval}_{param_values_str}"

    await manager.connect(websocket, stream_id)
    bybit_subscription_initiated = False
    if manager.get_client_count_for_stream(stream_id) == 1:
        logger.info(f"First client for stream {stream_id}. Starting Bybit WS.")
        try:
            processor = await bybit_kline_processor_factory(stream_id, detection_params)
            await bybit_service.start_kline_websocket(symbol, interval, processor, category=category)
            bybit_subscription_initiated = True
            logger.info(f"Bybit WS initiated for {stream_id}.")
            await websocket.send_json({"type": "status", "message": f"Connected to FVG stream {symbol}/{interval} with custom params. Waiting for data."})
        except Exception as e:
            logger.exception(f"Failed to start Bybit WS for {stream_id}: {e}")
            await websocket.close(code=1011, reason=f"Backend error for {stream_id}")
            manager.disconnect(websocket, stream_id); return
    else:
        logger.info(f"New client joined existing stream {stream_id}.")
        await websocket.send_json({"type": "status", "message": f"Joined existing FVG stream {symbol}/{interval}."})
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: logger.info(f"Client disconnected from {stream_id}.")
    except Exception as e: logger.exception(f"Exception for client on {stream_id}: {e}")
    finally:
        logger.info(f"Cleaning up client for {stream_id}.")
        emptied = manager.disconnect(websocket, stream_id)
        if emptied and bybit_subscription_initiated:
             logger.info(f"Last client for {stream_id} disconnected. Stopping Bybit WS.")
             if stream_id in stream_kline_buffers: del stream_kline_buffers[stream_id]
             await bybit_service.stop_kline_websocket(symbol, interval, category)
        logger.info(f"WS cleanup for {stream_id} finished.")

# --- Backtesting Endpoint ---
class BacktestParams(BaseModel):
    symbol: str = Field(..., description="Trading symbol, e.g., BTCUSDT", example="BTCUSDT")
    interval: str = Field(..., description="Kline interval (Bybit format), e.g., '60', 'D'", example="60")
    category: str = Field("linear", description="Bybit category: 'linear', 'spot', 'inverse'")
    data_limit: int = Field(500, description="Number of klines to fetch for backtest period", ge=50, le=2000)

    # FVG Detection Params (mirrors detect_fvgs signature)
    static_threshold_percent: float = Field(0.0, ge=0.0, description="Static threshold for FVG middle candle body %")
    use_adaptive_threshold: bool = Field(False, description="Use adaptive threshold for FVG detection")
    # adaptive_threshold_period_UNUSED: int = Field(0, description="Currently unused placeholder for adaptive FVG threshold period") # Not exposed in API for now
    use_volume_confirmation: bool = Field(False, description="Use volume confirmation for FVG")
    volume_lookback_period: int = Field(20, ge=1, description="Lookback period for volume average") # min_periods=1 for rolling
    volume_factor: float = Field(1.5, ge=1.0, description="Factor for volume confirmation (current_vol > avg_vol * factor)")
    min_fvg_price_height: float = Field(0.0, ge=0.0, description="Minimum price height for a valid FVG (in quote currency units)")

    # Backtester Params
    initial_balance: float = Field(10000.0, gt=0, description="Initial balance for backtest")
    commission_percent: float = Field(0.00075, ge=0.0, description="Commission per trade side (e.g., 0.00075 for 0.075%)")
    risk_per_trade_percent: float = Field(1.0, gt=0.0, le=100.0, description="Percentage of current balance to risk per trade")
    risk_free_rate_annual: float = Field(0.0, ge=0.0, description="Annual risk-free rate (for Sharpe, currently simplified)")

@router.post("/backtest/run", response_model=Dict[str, Any], tags=["Backtesting"])
async def run_fvg_backtest(params: BacktestParams = Body(...)):
    """
    Runs a backtest for an FVG-based strategy with specified parameters.
    Fetches historical data, detects FVGs based on input criteria, simulates trades
    with risk management, and returns detailed trade lists and performance metrics.
    """
    logger.info(f"API Call /backtest/run: symbol={params.symbol}, interval={params.interval}, data_limit={params.data_limit}")

    ohlcv_df = await bybit_service.get_historical_klines_bybit(
        symbol=params.symbol,
        interval=params.interval,
        limit=params.data_limit, # bybit_service currently caps this at 1000 if > 1000
        category=params.category
    )

    if ohlcv_df is None:
        logger.error(f"Backtest failed for {params.symbol}: Failed to fetch kline data from Bybit.")
        raise HTTPException(status_code=503, detail=f"Failed to fetch kline data from Bybit for {params.symbol}. Service unavailable or invalid parameters for Bybit.")

    # Require a reasonable number of candles for a meaningful backtest, e.g., min 30-50.
    min_candles_for_backtest = 50
    if ohlcv_df.empty or len(ohlcv_df) < min_candles_for_backtest:
        logger.warning(f"Backtest aborted for {params.symbol}: Not enough kline data ({len(ohlcv_df)} candles). Minimum {min_candles_for_backtest} required.")
        raise HTTPException(status_code=404, detail=f"Not enough kline data returned for {params.symbol} to run backtest ({len(ohlcv_df)} candles). Minimum {min_candles_for_backtest} required.")

    try:
        logger.info(f"Running backtest for {params.symbol} with {len(ohlcv_df)} candles. Initial balance: {params.initial_balance:.2f}")
        # Call run_backtest, passing through all relevant parameters
        backtest_results = backtester.run_backtest(
            ohlcv_df=ohlcv_df,
            # FVG detection parameters
            static_threshold_percent=params.static_threshold_percent,
            use_adaptive_threshold=params.fvg_use_adaptive_threshold,
            # adaptive_threshold_period_UNUSED is not in BacktestParams, default in run_backtest used
            use_volume_confirmation=params.fvg_use_volume_confirmation,
            volume_lookback_period=params.fvg_volume_lookback_period,
            volume_factor=params.fvg_volume_factor,
            min_fvg_price_height=params.fvg_min_price_height,
            # Backtester specific parameters
            initial_balance=params.initial_balance,
            commission_percent=params.commission_percent,
            risk_per_trade_percent=params.risk_per_trade_percent,
            risk_free_rate_annual=params.risk_free_rate_annual
        )
        logger.info(f"Backtest completed for {params.symbol}. Trades: {len(backtest_results.get('trades', []))}")
        return backtest_results
    except ValueError as ve:
        logger.error(f"Backtesting input error for {params.symbol}: {str(ve)}")
        raise HTTPException(status_code=400, detail=f"Backtesting input error: {str(ve)}")
    except Exception as e:
        logger.exception(f"Unexpected error during backtest execution for {params.symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred during backtest: {type(e).__name__}.")
