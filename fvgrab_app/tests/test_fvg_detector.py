import pandas as pd
import unittest
import numpy as np
from app.core_logic.fvg_detector import detect_fvgs

class TestFVGDetector(unittest.TestCase):

    def _get_default_kws(self):
        """Returns default keyword arguments for detect_fvgs for new filters."""
        return {
            "use_volume_confirmation": False,
            "volume_lookback_period": 20,
            "volume_factor": 1.5,
            "min_fvg_price_height": 0.0
        }

    def test_bullish_fvg_static_threshold_default(self):
        bullish_data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [19.0, 22.0, 25.5], 'high':  [20.0, 25.0, 28.0],
            'low':   [18.0, 21.0, 26.0], 'close': [19.5, 25.0, 27.0],
            'volume': [100, 120, 110] # Added volume
        }
        df = pd.DataFrame(bullish_data)
        fvgs = detect_fvgs(df, static_threshold_percent=0.0, use_adaptive_threshold=False, **self._get_default_kws())
        self.assertEqual(len(fvgs), 1)
        # ... (rest of assertions remain same)
        fvg = fvgs[0]
        self.assertEqual(fvg['type'], 'bullish')
        self.assertEqual(fvg['fvg_bottom'], 20.0)
        self.assertEqual(fvg['fvg_top'], 26.0)
        self.assertAlmostEqual(fvg['entry_price'], 23.0)
        self.assertEqual(fvg['sl_price'], 18.0)
        self.assertAlmostEqual(fvg['tp_price'], 33.0)


    def test_bearish_fvg_static_threshold_default(self):
        bearish_data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [31.0, 28.0, 24.5], 'high':  [32.0, 29.0, 24.0],
            'low':   [30.0, 25.0, 22.0], 'close': [30.5, 25.0, 23.0],
            'volume': [100, 120, 110] # Added volume
        }
        df = pd.DataFrame(bearish_data)
        fvgs = detect_fvgs(df, static_threshold_percent=0.0, use_adaptive_threshold=False, **self._get_default_kws())
        self.assertEqual(len(fvgs), 1)
        # ... (rest of assertions remain same)
        fvg = fvgs[0]
        self.assertEqual(fvg['type'], 'bearish')
        self.assertEqual(fvg['fvg_top'], 30.0)
        self.assertEqual(fvg['fvg_bottom'], 24.0)
        self.assertAlmostEqual(fvg['entry_price'], 27.0)
        self.assertEqual(fvg['sl_price'], 32.0)
        self.assertAlmostEqual(fvg['tp_price'], 17.0)


    def test_no_fvg_static_threshold(self):
        no_fvg_data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [10.0, 11.0, 10.0], 'high':  [10.5, 11.5, 10.8],
            'low':   [9.5,  10.5, 9.8],  'close': [10.0, 11.0, 10.2],
            'volume': [100,100,100]
        }
        df = pd.DataFrame(no_fvg_data)
        fvgs = detect_fvgs(df, static_threshold_percent=0.0, use_adaptive_threshold=False, **self._get_default_kws())
        self.assertEqual(len(fvgs), 0)

    def test_bullish_fvg_with_static_threshold(self):
        data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [19.0, 22.0, 25.5], 'high':  [20.0, 22.6, 28.0],
            'low':   [18.0, 21.9, 26.0], 'close': [19.5, 22.5, 27.0],
            'volume': [100,100,100]
        }
        df = pd.DataFrame(data)
        fvgs_fail = detect_fvgs(df, static_threshold_percent=5.0, use_adaptive_threshold=False, **self._get_default_kws())
        self.assertEqual(len(fvgs_fail), 0)
        fvgs_pass = detect_fvgs(df, static_threshold_percent=1.0, use_adaptive_threshold=False, **self._get_default_kws())
        self.assertEqual(len(fvgs_pass), 1)
        if fvgs_pass: self.assertEqual(fvgs_pass[0]['type'], 'bullish')

    def test_bearish_fvg_with_static_threshold(self):
        data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [31.0, 28.0, 24.5], 'high':  [32.0, 28.1, 24.0],
            'low':   [30.0, 27.4, 22.0], 'close': [30.5, 27.5, 23.0],
            'volume': [100,100,100]
        }
        df = pd.DataFrame(data)
        fvgs_fail = detect_fvgs(df, static_threshold_percent=3.0, use_adaptive_threshold=False, **self._get_default_kws())
        self.assertEqual(len(fvgs_fail), 0)
        fvgs_pass = detect_fvgs(df, static_threshold_percent=1.0, use_adaptive_threshold=False, **self._get_default_kws())
        self.assertEqual(len(fvgs_pass), 1)
        if fvgs_pass: self.assertEqual(fvgs_pass[0]['type'], 'bearish')

    def test_edge_cases_input_data(self):
        default_kwargs = self._get_default_kws()
        cols_with_vol = ['time', 'open', 'high', 'low', 'close', 'volume']
        fvgs_empty = detect_fvgs(pd.DataFrame(columns=cols_with_vol), **default_kwargs)
        self.assertEqual(len(fvgs_empty), 0)

        short_df_data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05']),
            'open': [19.0, 22.0], 'high': [20.0, 25.0], 'low': [18.0, 21.0],
            'close': [19.5, 25.0], 'volume': [100,100]
        }
        fvgs_short = detect_fvgs(pd.DataFrame(short_df_data), **default_kwargs)
        self.assertEqual(len(fvgs_short), 0)

        nan_df_data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open': [19.0, None, 25.5], 'high': [20.0, 25.0, 28.0],
            'low': [18.0, 21.0, 26.0], 'close': [19.5, 25.0, 27.0], 'volume': [100,100,100]
        }
        fvgs_nan = detect_fvgs(pd.DataFrame(nan_df_data), **default_kwargs)
        self.assertEqual(len(fvgs_nan), 0)

    def test_zero_open_price_robustness(self):
        data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10', '2023-01-01 00:15']),
            'open':  [10, 0, 12, 13], 'high':  [11, 5, 13, 14],
            'low':   [9,  0, 11, 5],  'close': [10, 2, 12, 13],
            'volume': [10,0,10,10] # Added volume, C1 (idx 1) has 0 volume
        }
        df = pd.DataFrame(data)
        fvgs_static = detect_fvgs(df, static_threshold_percent=0.0, use_adaptive_threshold=False, **self._get_default_kws())
        self.assertEqual(len(fvgs_static), 0, "Static threshold should not find FVG with this data")
        fvgs_adaptive = detect_fvgs(df, use_adaptive_threshold=True, **self._get_default_kws())
        self.assertEqual(len(fvgs_adaptive), 0, "Adaptive threshold should not find FVG with this data")

    def test_adaptive_threshold_allows_fvg(self):
        data_large_body_adaptive = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10', '2023-01-01 00:15', '2023-01-01 00:20']),
            'open':  [100, 100, 100, 100, 112], 'high':  [100.1, 100.1, 100.1, 110, 115],
            'low':   [99.9, 99.9, 99.9, 90,  110], 'close': [100, 100, 100, 109, 114],
            'volume': [10,10,10,100,10] # C3 (idx 3, prev_candle) has high volume
        }
        df_lb = pd.DataFrame(data_large_body_adaptive)
        fvgs_adaptive_pass = detect_fvgs(df_lb, use_adaptive_threshold=True, **self._get_default_kws())
        self.assertEqual(len(fvgs_adaptive_pass), 1, "Adaptive (4.5%) should allow FVG (body 9%)")
        fvgs_static_filter_lb = detect_fvgs(df_lb, static_threshold_percent=10.0, use_adaptive_threshold=False, **self._get_default_kws())
        self.assertEqual(len(fvgs_static_filter_lb), 0, "Static 10% should filter FVG (body 9%)")

    # --- New tests for Volume and FVG Size Filters ---
    def test_volume_confirmation_filters_fvg(self):
        """FVG forms by price/threshold, but middle candle volume is too low."""
        data = { # Bullish FVG data from test_bullish_fvg_static_threshold_default
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [19.0, 22.0, 25.5], 'high':  [20.0, 25.0, 28.0],
            'low':   [18.0, 21.0, 26.0], 'close': [19.5, 25.0, 27.0],
            'volume': [100, 10, 110] # Middle candle (idx 1) volume is 10
        }
        df = pd.DataFrame(data)
        # Avg volume for middle candle (idx 1): (100+10)/2 = 55, if lookback=2. If lookback=1, avg=100.
        # Let's use lookback = 1 for simplicity here, so avg_vol for middle candle is prior candle's vol (100).
        # Factor 1.5: 100 * 1.5 = 150. Middle candle vol (10) < 150. So FVG should be filtered.
        fvgs = detect_fvgs(df, use_volume_confirmation=True, volume_lookback_period=1, volume_factor=1.5)
        self.assertEqual(len(fvgs), 0, "FVG should be filtered by low volume on middle candle")

    def test_volume_confirmation_passes_fvg(self):
        """FVG forms and middle candle volume is sufficient."""
        data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [19.0, 22.0, 25.5], 'high':  [20.0, 25.0, 28.0],
            'low':   [18.0, 21.0, 26.0], 'close': [19.5, 25.0, 27.0],
            'volume': [100, 160, 110] # Middle candle (idx 1) volume is 160
        }
        df = pd.DataFrame(data)
        # Avg_vol for middle candle (lookback=1) is 100. Factor 1.5: 100 * 1.5 = 150.
        # Middle candle vol (160) > 150. FVG should pass.
        fvgs = detect_fvgs(df, use_volume_confirmation=True, volume_lookback_period=1, volume_factor=1.5)
        self.assertEqual(len(fvgs), 1, "FVG should pass with sufficient volume")

    def test_volume_filter_at_start_of_data(self):
        """Test volume filter with min_periods=1 at the start of data."""
        # Only 3 candles, so rolling avg for middle candle (idx 1) will only use first candle if lookback > 1.
        # With lookback=20, min_periods=1: avg_vol[0]=vol[0], avg_vol[1]=(vol[0]+vol[1])/2
        data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [19.0, 22.0, 25.5], 'high':  [20.0, 25.0, 28.0],
            'low':   [18.0, 21.0, 26.0], 'close': [19.5, 25.0, 27.0],
            'volume': [10, 100, 110] # C0=10, C1(middle)=100
        }
        df = pd.DataFrame(data)
        # avg_volume_series.iloc[i-1] is for previous_candle (idx 1).
        # avg_volume_series[0] = 10
        # avg_volume_series[1] = (10+100)/2 = 55
        # Threshold = 55 * 1.5 = 82.5. Middle candle volume is 100. 100 > 82.5. Pass.
        fvgs = detect_fvgs(df, use_volume_confirmation=True, volume_lookback_period=20, volume_factor=1.5)
        self.assertEqual(len(fvgs), 1, "FVG should pass volume filter at start of data")

        # Case: Volume is too low at start
        data_low_vol_start = {
             'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [19.0, 22.0, 25.5], 'high':  [20.0, 25.0, 28.0],
            'low':   [18.0, 21.0, 26.0], 'close': [19.5, 25.0, 27.0],
            'volume': [100, 10, 110] # C0=100, C1(middle)=10
        }
        df_lvs = pd.DataFrame(data_low_vol_start)
        # avg_volume_series[0] = 100
        # avg_volume_series[1] = (100+10)/2 = 55
        # Threshold = 55 * 1.5 = 82.5. Middle candle volume is 10. 10 < 82.5. Filtered.
        fvgs_lvs = detect_fvgs(df_lvs, use_volume_confirmation=True, volume_lookback_period=20, volume_factor=1.5)
        self.assertEqual(len(fvgs_lvs), 0, "FVG should be filtered by volume at start of data")


    def test_min_fvg_size_filters_fvg(self):
        """FVG forms by price, but its height is too small."""
        # FVG from test_bullish_fvg: height = fvg_top (26) - fvg_bottom (20) = 6.0
        data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [19.0, 22.0, 25.5], 'high':  [20.0, 25.0, 28.0],
            'low':   [18.0, 21.0, 26.0], 'close': [19.5, 25.0, 27.0],
            'volume': [100,120,100]
        }
        df = pd.DataFrame(data)
        kwargs = self._get_default_kws()
        kwargs['min_fvg_price_height'] = 7.0
        fvgs = detect_fvgs(df, **kwargs) # Min height 7, FVG is 6
        self.assertEqual(len(fvgs), 0, "FVG should be filtered by min_fvg_price_height")

    def test_min_fvg_size_passes_fvg(self):
        """FVG forms and its height meets the minimum."""
        data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [19.0, 22.0, 25.5], 'high':  [20.0, 25.0, 28.0],
            'low':   [18.0, 21.0, 26.0], 'close': [19.5, 25.0, 27.0],
            'volume': [100,120,100]
        }
        df = pd.DataFrame(data)
        kwargs = self._get_default_kws()
        kwargs['min_fvg_price_height'] = 5.0
        fvgs = detect_fvgs(df, **kwargs) # Min height 5, FVG is 6
        self.assertEqual(len(fvgs), 1, "FVG should pass with sufficient height")

    def test_combined_filters_fvg_passes_all(self):
        """FVG forms and passes body threshold, volume, and size filters."""
        # Bullish FVG: prior_H=20, prev_C=25, curr_L=26. FVG height = 6.
        # Prev candle (idx 1): O=22, C=25. Body_delta = (3/22)*100 = 13.6%.
        # Volume: C0=80, C1(middle)=150, C2=100.
        # Avg Vol for C1 (lookback=1, factor=1.5): prev_avg=80, threshold=120. C1_vol(150)>120. Pass.
        data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [19.0, 22.0, 25.5], 'high':  [20.0, 25.0, 28.0],
            'low':   [18.0, 21.0, 26.0], 'close': [19.5, 25.0, 27.0],
            'volume': [80, 150, 100]
        }
        df = pd.DataFrame(data)
        fvgs = detect_fvgs(df,
                           static_threshold_percent=10.0, # 13.6% > 10%. Pass.
                           use_volume_confirmation=True, volume_lookback_period=1, volume_factor=1.5, # Pass.
                           min_fvg_price_height=5.0) # Height 6 > 5. Pass.
        self.assertEqual(len(fvgs), 1, "FVG should pass all combined filters")


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
