import pandas as pd
from typing import List, Dict, Any

def detect_fvgs(ohlcv_df: pd.DataFrame, threshold_percent: float = 0.0) -> List[Dict[str, Any]]:
    fvgs = []
    if not isinstance(ohlcv_df, pd.DataFrame) or len(ohlcv_df) < 3:
        return fvgs

    required_columns = {'time', 'open', 'high', 'low', 'close'}
    if not required_columns.issubset(ohlcv_df.columns):
        print(f"DataFrame must contain columns: {required_columns}") # TODO: Replace with logging or exception
        return fvgs

    for i in range(2, len(ohlcv_df)):
        current_candle = ohlcv_df.iloc[i]
        previous_candle = ohlcv_df.iloc[i-1]
        prior_candle = ohlcv_df.iloc[i-2]

        # Check for NaN values in critical columns for the 3-candle pattern
        critical_values = [
            current_candle['low'], current_candle['high'],
            previous_candle['open'], previous_candle['close'], previous_candle['time'],
            prior_candle['high'], prior_candle['low'], prior_candle['time']
        ]
        if any(pd.isna(value) for value in critical_values):
            continue # Skip this iteration if any critical data is missing

        # Bullish FVG
        current_low_0 = current_candle['low']
        prior_high_2 = prior_candle['high']
        previous_close_1 = previous_candle['close']
        previous_open_1 = previous_candle['open']
        prior_low_2 = prior_candle['low']

        bar_delta_percent = 0
        if previous_open_1 != 0 and not pd.isna(previous_open_1) and not pd.isna(previous_close_1):
            bar_delta_percent = ((previous_close_1 - previous_open_1) / previous_open_1) * 100

        is_bullish_fvg_condition = current_low_0 > prior_high_2 and previous_close_1 > prior_high_2
        if threshold_percent > 0:
            is_bullish_fvg_condition = is_bullish_fvg_condition and bar_delta_percent > threshold_percent

        if is_bullish_fvg_condition:
            fvg_bottom = prior_high_2
            fvg_top = current_low_0
            entry_price = (fvg_top + fvg_bottom) / 2
            sl_price = prior_low_2

            tp_price = entry_price
            if entry_price != sl_price : # Check to prevent zero division or no risk defined
                tp_distance = abs(entry_price - sl_price)
                tp_price = entry_price + 2 * tp_distance

            fvgs.append({
                'type': 'bullish',
                'time': previous_candle['time'],
                'fvg_bottom': fvg_bottom,
                'fvg_top': fvg_top,
                'entry_price': entry_price,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'trigger_candle_time': current_candle['time']
            })

        # Bearish FVG
        current_high_0 = current_candle['high']
        prior_low_2_bearish = prior_candle['low']
        prior_high_2_bearish = prior_candle['high']

        # bar_delta_percent is the same as for bullish, but used negatively in condition
        is_bearish_fvg_condition = current_high_0 < prior_low_2_bearish and previous_close_1 < prior_low_2_bearish
        if threshold_percent > 0:
            # For bearish, the body change should be negative and its absolute value > threshold
            is_bearish_fvg_condition = is_bearish_fvg_condition and (bar_delta_percent < 0 and abs(bar_delta_percent) > threshold_percent)


        if is_bearish_fvg_condition:
            fvg_bottom = current_high_0
            fvg_top = prior_low_2_bearish
            entry_price = (fvg_top + fvg_bottom) / 2
            sl_price = prior_high_2_bearish

            tp_price = entry_price
            if entry_price != sl_price:
                tp_distance = abs(sl_price - entry_price)
                tp_price = entry_price - 2 * tp_distance

            fvgs.append({
                'type': 'bearish',
                'time': previous_candle['time'],
                'fvg_bottom': fvg_bottom,
                'fvg_top': fvg_top,
                'entry_price': entry_price,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'trigger_candle_time': current_candle['time']
            })

    return fvgs
