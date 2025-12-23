"""
Core logic for detecting Fair Value Gaps (FVGs) in OHLCV data.

This module provides the primary function `detect_fvgs` which scans a pandas DataFrame
of market data to identify FVG patterns. These patterns are indicative of market
imbalances and are often used as entry points in trading strategies.
"""

import pandas as pd
from typing import List, Dict, Any
import numpy as np

# TODO: (Partially addressed by adaptive threshold) Consider more advanced adaptive thresholding, e.g., based on ATR.
# TODO: Explore options for multi-timeframe FVG confluence analysis.

def detect_fvgs(
    ohlcv_df: pd.DataFrame,
    static_threshold_percent: float = 0.0,
    use_adaptive_threshold: bool = False,
    adaptive_threshold_period_UNUSED: int = 0, # Placeholder
    use_volume_confirmation: bool = False,
    volume_lookback_period: int = 20,
    volume_factor: float = 1.5,
    min_fvg_price_height: float = 0.0
) -> List[Dict[str, Any]]:
    """
    Detects Fair Value Gaps (FVGs) from OHLCV data with optional filters.

    Args:
        ohlcv_df (pd.DataFrame): Input DataFrame with 'time', 'open', 'high', 'low', 'close', 'volume'.
                                 Assumed to be sorted chronologically.
        static_threshold_percent (float): Static body % threshold for the middle FVG candle
                                          (if `use_adaptive_threshold` is False).
        use_adaptive_threshold (bool): If True, uses an adaptive body % threshold.
        adaptive_threshold_period_UNUSED (int): Placeholder for future adaptive logic.
        use_volume_confirmation (bool): If True, filters FVGs based on the volume of the middle candle.
        volume_lookback_period (int): Lookback period for calculating average volume.
        volume_factor (float): Factor by which the middle candle's volume must exceed average volume.
        min_fvg_price_height (float): Minimum absolute price height of the FVG gap.

    Returns:
        List[Dict[str, Any]]: A list of detected FVG dictionaries.
    """
    fvgs = []
    if not isinstance(ohlcv_df, pd.DataFrame) or len(ohlcv_df) < 3:
        return fvgs

    required_cols = {'time', 'open', 'high', 'low', 'close', 'volume'} # Added 'volume'
    if not required_cols.issubset(ohlcv_df.columns): # Corrected back to ohlcv_df for this initial check
        # TODO: Replace print with proper logging
        print(f"FVG Detector: DataFrame must contain columns: {required_cols}")
        return fvgs

    df = ohlcv_df.copy()
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0.0) # Ensure volume is numeric

    # --- Pre-calculate series for efficiency ---
    open_prices = df['open'].fillna(0)
    close_prices = df['close']
    bar_delta_percent_series = pd.Series(
        np.where(open_prices == 0, 0.0, ((close_prices - open_prices) / open_prices) * 100),
        index=df.index
    ).fillna(0.0)

    adaptive_thresholds_series = None
    if use_adaptive_threshold:
        abs_bar_delta = bar_delta_percent_series.abs()
        cum_abs_bar_delta = abs_bar_delta.cumsum()
        num_candles_for_avg = pd.Series(range(1, len(df) + 1), index=df.index)
        adaptive_thresholds_series = (cum_abs_bar_delta / num_candles_for_avg) * 2.0
        adaptive_thresholds_series = adaptive_thresholds_series.fillna(0.0)

    avg_volume_series = None
    if use_volume_confirmation:
        # Calculate rolling average volume. min_periods=1 allows it to start calculating from the first candle.
        avg_volume_series = df['volume'].rolling(
            window=volume_lookback_period,
            min_periods=1 # Ensures we get a value even if fewer than `volume_lookback_period` bars exist
        ).mean().fillna(0.0) # Fill initial NaNs if any (though min_periods=1 should prevent full NaNs)

    # --- Main FVG Detection Loop ---
    for i in range(2, len(df)):
        current_candle = df.iloc[i]
        previous_candle = df.iloc[i-1] # This is the "middle candle" of the FVG pattern
        prior_candle = df.iloc[i-2]

        critical_values = [
            current_candle['low'], current_candle['high'], current_candle['time'],
            previous_candle['open'], previous_candle['close'], previous_candle['time'], previous_candle['volume'],
            prior_candle['high'], prior_candle['low'], prior_candle['time']
        ]
        if any(pd.isna(value) for value in critical_values):
            continue # Skip if essential data is missing for this 3-candle pattern

        bar_delta_of_previous_candle = bar_delta_percent_series.iloc[i-1]

        threshold_to_use = static_threshold_percent
        if use_adaptive_threshold and adaptive_thresholds_series is not None:
            threshold_to_use = adaptive_thresholds_series.iloc[i-1]

        # --- Bullish FVG ---
        is_bullish_fvg_price_action = current_candle['low'] > prior_candle['high'] and \
                                      previous_candle['close'] > prior_candle['high']

        passes_body_threshold_bullish = True # Assume passes if threshold is not positive
        if threshold_to_use > 0:
            passes_body_threshold_bullish = bar_delta_of_previous_candle > threshold_to_use

        if is_bullish_fvg_price_action and passes_body_threshold_bullish:
            fvg_bottom = prior_candle['high']
            fvg_top = current_candle['low']
            fvg_height = abs(fvg_top - fvg_bottom)

            # Apply Min FVG Size Filter
            if min_fvg_price_height > 0.0 and fvg_height < min_fvg_price_height:
                continue # FVG too small

            # Apply Volume Confirmation Filter
            if use_volume_confirmation and avg_volume_series is not None:
                middle_candle_volume = previous_candle['volume']
                # Average volume should be from the period *before* the middle candle.
                # So, if middle candle is at i-1, we look at avg volume ending at i-2.
                # The rolling mean at avg_volume_series.iloc[i-2] is the mean of window ending at i-2.
                if i-2 >= 0: # Ensure index i-2 is valid for avg_volume_series
                    avg_volume_base = avg_volume_series.iloc[i-2]
                    if pd.notna(avg_volume_base) and avg_volume_base > 0:
                        if middle_candle_volume < (avg_volume_base * volume_factor):
                            continue # Volume too low
                    # If avg_volume_base is NaN or 0, bypass this filter for this FVG.
                # else: (i-2 < 0) This case should not be hit as loop starts at i=2, so i-2 is min 0.
                # If avg_volume_series.iloc[0] is used (when i-2=0), it's the avg of the first element if min_periods=1.
                # This means for the first possible FVG (i=2), avg volume is based on prior_candle's volume only.

            # If all filters passed, record FVG
            entry_price = (fvg_top + fvg_bottom) / 2
            sl_price = prior_candle['low']
            tp_price = entry_price + 2 * abs(entry_price - sl_price) if entry_price != sl_price else entry_price
            fvgs.append({
                'type': 'bullish', 'time': previous_candle['time'],
                'fvg_bottom': fvg_bottom, 'fvg_top': fvg_top,
                'entry_price': entry_price, 'sl_price': sl_price, 'tp_price': tp_price,
                'trigger_candle_time': current_candle['time']
            })

        # --- Bearish FVG ---
        is_bearish_fvg_price_action = current_candle['high'] < prior_candle['low'] and \
                                      previous_candle['close'] < prior_candle['low']

        passes_body_threshold_bearish = True # Assume passes if threshold is not positive
        if threshold_to_use > 0:
            passes_body_threshold_bearish = bar_delta_of_previous_candle < 0 and \
                                            abs(bar_delta_of_previous_candle) > threshold_to_use

        if is_bearish_fvg_price_action and passes_body_threshold_bearish:
            fvg_bottom = current_candle['high']
            fvg_top = prior_candle['low']
            fvg_height = abs(fvg_top - fvg_bottom)

            # Apply Min FVG Size Filter
            if min_fvg_price_height > 0.0 and fvg_height < min_fvg_price_height:
                continue # FVG too small

            # Apply Volume Confirmation Filter
            if use_volume_confirmation and avg_volume_series is not None:
                middle_candle_volume = previous_candle['volume']
                if i-2 >= 0: # Ensure index i-2 is valid for avg_volume_series
                    avg_volume_base = avg_volume_series.iloc[i-2]
                    if pd.notna(avg_volume_base) and avg_volume_base > 0:
                        if middle_candle_volume < (avg_volume_base * volume_factor):
                            continue # Volume too low

            # If all filters passed, record FVG
            entry_price = (fvg_top + fvg_bottom) / 2
            sl_price = prior_candle['high']
            tp_price = entry_price - 2 * abs(sl_price - entry_price) if entry_price != sl_price else entry_price
            fvgs.append({
                'type': 'bearish', 'time': previous_candle['time'],
                'fvg_bottom': fvg_bottom, 'fvg_top': fvg_top,
                'entry_price': entry_price, 'sl_price': sl_price, 'tp_price': tp_price,
                'trigger_candle_time': current_candle['time']
            })

    return fvgs
