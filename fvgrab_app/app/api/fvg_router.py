from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from typing import List, Dict, Any, Optional
import pandas as pd
import asyncio
from collections import deque # For kline buffer
import logging # For WebSocket logging

# Assuming services and core_logic are structured as per previous steps
from app.services import bybit_service
from app.core_logic import fvg_detector

# Configure basic logging for this router/module
logger = logging.getLogger(__name__)
# Ensure basicConfig is called, perhaps in main.py or once globally
# For now, if not configured by `bybit_service` or main, this might not output
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


router = APIRouter()

# The existing /test route
@router.get("/test", tags=["General"])
async def test_route():
    return {"message": "FVG API router is working!"}

# Existing historical FVG endpoint
@router.get("/fvgs/historical", response_model=List[Dict[str, Any]], tags=["FVG Analysis"])
async def get_historical_fvgs(
    symbol: str = Query(..., description="Trading symbol, e.g., BTCUSDT", example="BTCUSDT"),
    interval: str = Query(..., description="Kline interval (Bybit format), e.g., '60' for 1h, 'D' for 1 day", example="60"),
    limit: int = Query(200, description="Number of klines to fetch (max 1000 for Bybit)", ge=1, le=1000),
    category: str = Query("linear", description="Bybit category: 'linear', 'spot', 'inverse'", example="linear"),
    threshold_percent: Optional[float] = Query(0.0, description="Minimum body percentage for the FVG's middle candle, as a percentage (e.g., 0.5 for 0.5%). Set to 0 to disable.", ge=0.0)
):
    """
    Fetches historical kline data for a given symbol and interval from Bybit,
    then detects Fair Value Gaps (FVGs) based on the retrieved data.
    """
    logger.info(f"API Call /fvgs/historical: symbol={symbol}, interval={interval}, limit={limit}, category={category}, threshold={threshold_percent}")

    ohlcv_df = await bybit_service.get_historical_klines_bybit(
        symbol=symbol,
        interval=interval,
        limit=limit,
        category=category
    )

    if ohlcv_df is None:
        logger.warning(f"Failed to fetch kline data from Bybit for {symbol} (category: {category}, interval: {interval}).")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch kline data from Bybit for {symbol}. The Bybit service might be temporarily unavailable or parameters might be invalid."
        )

    if ohlcv_df.empty:
        logger.info(f"No kline data returned from Bybit for {symbol} (category: {category}, interval: {interval}). Returning empty list of FVGs.")
        return []

    try:
        current_threshold = threshold_percent if threshold_percent is not None else 0.0
        fvgs = fvg_detector.detect_fvgs(ohlcv_df, threshold_percent=current_threshold)
        logger.info(f"Detected {len(fvgs)} FVGs for {symbol} (category: {category}, interval: {interval}).")
        return fvgs
    except ValueError as e:
        logger.error(f"ValueError in FVG detection for {symbol}: {e}. DF head: {ohlcv_df.head()}")
        raise HTTPException(status_code=400, detail=f"Invalid data for FVG detection: {str(e)}")
    except Exception as e:
        logger.exception(f"Unexpected error during FVG detection for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred during FVG detection.")


# --- WebSocket Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, stream_id: str):
        await websocket.accept()
        if stream_id not in self.active_connections:
            self.active_connections[stream_id] = []
        self.active_connections[stream_id].append(websocket)
        logger.info(f"Client connected to stream: {stream_id}. Total clients for stream: {len(self.active_connections[stream_id])}")

    def disconnect(self, websocket: WebSocket, stream_id: str) -> bool:
        stream_was_emptied = False
        if stream_id in self.active_connections:
            if websocket in self.active_connections[stream_id]:
                self.active_connections[stream_id].remove(websocket)
                logger.info(f"Client disconnected from stream: {stream_id}.")
                if not self.active_connections[stream_id]:
                    del self.active_connections[stream_id]
                    logger.info(f"Stream {stream_id} removed as no clients are connected.")
                    stream_was_emptied = True
            # Check again if list became empty and was deleted by another disconnect call concurrently (less likely with FastAPI's per-request worker model but good for robustness)
            if not self.active_connections.get(stream_id) and not stream_was_emptied : # if it was deleted by this call, stream_was_emptied is true
                 stream_was_emptied = True # Indicates stream is now confirmed empty
        return stream_was_emptied

    async def broadcast_to_stream(self, stream_id: str, message: Any):
        if stream_id in self.active_connections:
            message_tasks = []
            for connection in self.active_connections[stream_id]:
                message_tasks.append(connection.send_json(message))
            if message_tasks:
                results = await asyncio.gather(*message_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        logger.error(f"Error broadcasting to client in stream {stream_id}: {res}")


    def has_clients_for_stream(self, stream_id: str) -> bool:
        return stream_id in self.active_connections and len(self.active_connections[stream_id]) > 0

    def get_client_count_for_stream(self, stream_id: str) -> int:
        if stream_id in self.active_connections:
            return len(self.active_connections[stream_id])
        return 0

manager = ConnectionManager()

# --- Kline Buffer and FVG Detection for WS ---
stream_kline_buffers: Dict[str, deque] = {}

def _kline_list_to_df(kline_list: List[Dict]) -> pd.DataFrame:
    if not kline_list:
        return pd.DataFrame()
    df = pd.DataFrame(kline_list)

    # Standardize column names and types for fvg_detector
    # Bybit WS kline data typically includes: {'start': ts, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v, 'turnover': t, 'confirm': bool, 'timestamp': ts_event}
    # fvg_detector expects: time, open, high, low, close, volume

    # Temporary rename 'volume' from Bybit if it clashes with a different meaning or type
    df = df.rename(columns={'start': 'time', 'volume': 'volume_orig'})
    df['time'] = pd.to_datetime(df['time'], unit='ms')

    numeric_cols = ['open', 'high', 'low', 'close', 'volume_orig'] # 'turnover' could also be numeric
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Final column selection and renaming 'volume_orig' to 'volume'
    df = df.rename(columns={'volume_orig': 'volume'})

    # Ensure all required columns are present, fill with NaN or 0 if appropriate, or raise error
    required_detector_columns = ['time', 'open', 'high', 'low', 'close', 'volume']
    for col in required_detector_columns:
        if col not in df.columns:
            df[col] = 0.0 # Or pd.NA, depending on how fvg_detector handles missing data
            logger.warning(f"Column '{col}' was missing from kline data, filled with 0.0.")

    return df[required_detector_columns].copy()


async def bybit_kline_processor_factory(stream_id: str, threshold_p: float):
    if stream_id not in stream_kline_buffers:
        stream_kline_buffers[stream_id] = deque(maxlen=10)
        logger.info(f"Initialized kline buffer for stream_id: {stream_id} with maxlen=10")

    async def process_kline_message(message: Dict):
        topic = message.get('topic', 'UnknownTopic')
        # logger.debug(f"WS Data for {topic} ({stream_id}): {message}")
        kline_data_list = message.get('data', [])

        processed_this_message = False
        for kline_item in kline_data_list:
            if kline_item.get('confirm', False):
                processed_this_message = True # Mark that we are processing a confirmed candle
                required_fields = ['start', 'open', 'high', 'low', 'close', 'volume']
                if not all(field in kline_item for field in required_fields):
                    logger.warning(f"Skipping kline item for {stream_id} due to missing fields: {kline_item}")
                    continue

                buffer = stream_kline_buffers[stream_id]
                buffer.append(kline_item)

                if len(buffer) >= 3:
                    klines_for_df = list(buffer)
                    ohlcv_df = _kline_list_to_df(klines_for_df)

                    if not ohlcv_df.empty and len(ohlcv_df) >=3:
                        try:
                            fvgs = fvg_detector.detect_fvgs(ohlcv_df, threshold_percent=threshold_p)
                            if fvgs:
                                latest_kline_time_in_df = ohlcv_df['time'].iloc[-1]
                                new_fvgs_to_send = [fvg for fvg in fvgs if pd.to_datetime(fvg['trigger_candle_time']) == latest_kline_time_in_df]

                                if new_fvgs_to_send:
                                    logger.info(f"New FVGs detected for {stream_id} (threshold {threshold_p}%): {new_fvgs_to_send}")
                                    await manager.broadcast_to_stream(stream_id, {"type": "fvg_update", "data": new_fvgs_to_send})
                        except Exception as e:
                            logger.exception(f"Error in FVG detection for stream {stream_id}: {e}")
        # if processed_this_message:
        #    logger.debug(f"Finished processing confirmed kline(s) for {stream_id}.")
    return process_kline_message


@router.websocket("/ws/fvg-stream/{category}/{symbol}/{interval}")
async def websocket_fvg_endpoint(
    websocket: WebSocket,
    category: str,
    symbol: str,
    interval: str,
    threshold_percent: Optional[float] = Query(0.0, description="FVG detection threshold (e.g., 0.5 for 0.5%)", ge=0.0)
):
    # Stream ID needs to be unique for each combination of parameters that affect the data or its processing
    current_threshold = threshold_percent if threshold_percent is not None else 0.0
    stream_id = f"{category}_{symbol}_{interval}_{current_threshold}"

    await manager.connect(websocket, stream_id)

    bybit_subscription_active_for_this_stream = False

    # Start Bybit WebSocket if this is the first client for this specific stream_id
    if manager.get_client_count_for_stream(stream_id) == 1:
        logger.info(f"First client for stream {stream_id}. Attempting to start Bybit WebSocket subscription.")
        try:
            processor = await bybit_kline_processor_factory(stream_id, current_threshold)
            await bybit_service.start_kline_websocket(
                symbol=symbol,
                interval=interval,
                callback_fn=processor,
                category=category
            )
            # Note: Due to known pybit issues in this env, start_kline_websocket might not actually succeed in subscribing.
            # We'll assume for this logic's structure that if it doesn't raise an immediate error, it "tried".
            bybit_subscription_active_for_this_stream = True
            logger.info(f"Bybit WebSocket subscription initiated for {stream_id}.")
            await websocket.send_json({"type": "status", "message": f"Connected to FVG stream for {symbol}/{interval} with threshold {current_threshold}%. Waiting for data."})
        except Exception as e:
            logger.exception(f"Failed to start Bybit WebSocket for {stream_id}: {e}")
            await websocket.send_json({"type": "error", "message": f"Could not connect to Bybit data stream for {symbol}/{interval}."})
            # No explicit disconnect from manager here; finally block will handle it. Client might close or server might.
    else:
        logger.info(f"New client joined existing stream {stream_id}. Not re-starting Bybit WS.")
        await websocket.send_json({"type": "status", "message": f"Joined existing FVG stream for {symbol}/{interval} with threshold {current_threshold}%."})

    try:
        while True:
            # Keep the connection alive. This will raise WebSocketDisconnect if client closes.
            # We are not expecting data from client in this simple broadcast-only setup.
            await websocket.receive_text()
            # If we needed to handle client messages:
            # data = await websocket.receive_json()
            # logger.info(f"Received from client on {stream_id}: {data}")
    except WebSocketDisconnect:
        logger.info(f"Client disconnected (WebSocketDisconnect) from {stream_id}.")
    except Exception as e:
        logger.exception(f"Exception for client on {stream_id}: {type(e).__name__} - {e}")
    finally:
        logger.info(f"Cleaning up client connection for stream {stream_id}.")
        stream_emptied = manager.disconnect(websocket, stream_id)
        if stream_emptied and bybit_subscription_active_for_this_stream:
             logger.info(f"Last client for stream {stream_id} disconnected. Stopping Bybit WebSocket subscription.")
             if stream_id in stream_kline_buffers:
                 del stream_kline_buffers[stream_id]
                 logger.info(f"Cleared kline buffer for stream {stream_id}.")
             await bybit_service.stop_kline_websocket(symbol, interval, category) # Category for stop should match start
        logger.info(f"WebSocket cleanup for client on {stream_id} finished.")
