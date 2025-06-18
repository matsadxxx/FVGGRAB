import pandas as pd
import unittest
from app.core_logic.fvg_detector import detect_fvgs

class TestFVGDetector(unittest.TestCase):

    def test_bullish_fvg(self):
        bullish_data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [19.0, 22.0, 25.5],
            'high':  [20.0, 25.0, 28.0],
            'low':   [18.0, 21.0, 26.0],
            'close': [19.5, 25.0, 27.0]
        }
        df = pd.DataFrame(bullish_data)
        fvgs = detect_fvgs(df)
        self.assertEqual(len(fvgs), 1)
        fvg = fvgs[0]
        self.assertEqual(fvg['type'], 'bullish')
        self.assertEqual(fvg['fvg_bottom'], 20.0)
        self.assertEqual(fvg['fvg_top'], 26.0)
        self.assertAlmostEqual(fvg['entry_price'], 23.0)
        self.assertEqual(fvg['sl_price'], 18.0)
        self.assertAlmostEqual(fvg['tp_price'], 33.0) # Entry 23, SL 18. Risk = 5. TP = 23 + 2*5 = 33
        self.assertEqual(fvg['time'], pd.to_datetime('2023-01-01 00:05'))
        self.assertEqual(fvg['trigger_candle_time'], pd.to_datetime('2023-01-01 00:10'))

    def test_bearish_fvg(self):
        bearish_data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [31.0, 28.0, 24.5],
            'high':  [32.0, 29.0, 24.0], # prior_candle high is 32 (SL for bearish)
            'low':   [30.0, 25.0, 22.0], # prior_candle low is 30 (FVG top for bearish)
            'close': [30.5, 25.0, 23.0] # previous_candle close is 25
                                        # current_candle high is 24 (FVG bottom for bearish)
        }
        # Bearish FVG: current_candle['high'] (24) < prior_candle['low'] (30) AND previous_candle['close'] (25) < prior_candle['low'] (30)
        # FVG top = prior_candle['low'] = 30
        # FVG bottom = current_candle['high'] = 24
        # Entry = (30+24)/2 = 27
        # SL = prior_candle['high'] = 32
        # Risk = SL - Entry = 32 - 27 = 5
        # TP = Entry - 2*Risk = 27 - 2*5 = 17
        df = pd.DataFrame(bearish_data)
        fvgs = detect_fvgs(df)
        self.assertEqual(len(fvgs), 1)
        fvg = fvgs[0]
        self.assertEqual(fvg['type'], 'bearish')
        self.assertEqual(fvg['fvg_top'], 30.0)
        self.assertEqual(fvg['fvg_bottom'], 24.0)
        self.assertAlmostEqual(fvg['entry_price'], 27.0)
        self.assertEqual(fvg['sl_price'], 32.0)
        self.assertAlmostEqual(fvg['tp_price'], 17.0)
        self.assertEqual(fvg['time'], pd.to_datetime('2023-01-01 00:05'))
        self.assertEqual(fvg['trigger_candle_time'], pd.to_datetime('2023-01-01 00:10'))

    def test_no_fvg(self):
        no_fvg_data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [10.0, 11.0, 10.0],
            'high':  [10.5, 11.5, 10.8], # current_high_0 = 10.8, prior_low_2 = 9.5
            'low':   [9.5,  10.5, 9.8],  # current_low_0 = 9.8, prior_high_2 = 10.5
            'close': [10.0, 11.0, 10.2] # previous_close_1 = 11.0
        }
        # Bullish check: current_low_0 (9.8) > prior_high_2 (10.5) -> FALSE
        # Bearish check: current_high_0 (10.8) < prior_low_2 (9.5) -> FALSE
        df = pd.DataFrame(no_fvg_data)
        fvgs = detect_fvgs(df)
        self.assertEqual(len(fvgs), 0)

    def test_bullish_fvg_with_threshold(self):
        # previous_open_1 = 22, previous_close_1 = 22.5. Delta = ((22.5 - 22) / 22) * 100 = (0.5/22)*100 approx 2.27%
        bullish_data_small_body = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [19.0, 22.0, 25.5],
            'high':  [20.0, 22.6, 28.0],
            'low':   [18.0, 21.9, 26.0], # current_low_0 (26) > prior_high_2 (20)
            'close': [19.5, 22.5, 27.0] # previous_close_1 (22.5) > prior_high_2 (20)
        }
        df = pd.DataFrame(bullish_data_small_body)

        # bar_delta_percent = ((22.5 - 22.0) / 22.0) * 100 = (0.5 / 22.0) * 100 = 2.2727...
        # This FVG should form if threshold is 1% (2.27 > 1)
        # This FVG should NOT form if threshold is 5% (2.27 < 5)

        fvgs_with_high_thresh = detect_fvgs(df, threshold_percent=5.0)
        self.assertEqual(len(fvgs_with_high_thresh), 0, "FVG should not form with 5% threshold")

        fvgs_with_low_thresh = detect_fvgs(df, threshold_percent=1.0)
        self.assertEqual(len(fvgs_with_low_thresh), 1, "FVG should form with 1% threshold")
        if len(fvgs_with_low_thresh) > 0:
            self.assertEqual(fvgs_with_low_thresh[0]['type'], 'bullish')

    def test_bearish_fvg_with_threshold(self):
        # previous_open_1 = 28.0, previous_close_1 = 27.5. Delta = ((27.5 - 28.0) / 28.0) * 100 = (-0.5/28.0)*100 approx -1.78%
        # abs(bar_delta_percent) is approx 1.78%
        bearish_data_small_body = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [31.0, 28.0, 24.5],
            'high':  [32.0, 28.1, 24.0], # current_high_0 (24) < prior_low_2 (30)
            'low':   [30.0, 27.4, 22.0],
            'close': [30.5, 27.5, 23.0]  # previous_close_1 (27.5) < prior_low_2 (30)
        }
        df = pd.DataFrame(bearish_data_small_body)

        # abs_bar_delta_percent = abs(((27.5 - 28.0) / 28.0) * 100) = abs(-0.5 / 28.0 * 100) = 1.7857...
        # This FVG should form if threshold is 1% (1.78 > 1)
        # This FVG should NOT form if threshold is 3% (1.78 < 3)

        fvgs_with_high_thresh = detect_fvgs(df, threshold_percent=3.0)
        self.assertEqual(len(fvgs_with_high_thresh), 0, "FVG should not form with 3% threshold")

        fvgs_with_low_thresh = detect_fvgs(df, threshold_percent=1.0)
        self.assertEqual(len(fvgs_with_low_thresh), 1, "FVG should form with 1% threshold")
        if len(fvgs_with_low_thresh) > 0:
            self.assertEqual(fvgs_with_low_thresh[0]['type'], 'bearish')


    def test_edge_cases_input_data(self):
        # Test with empty DataFrame
        empty_df = pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close'])
        fvgs_empty = detect_fvgs(empty_df)
        self.assertEqual(len(fvgs_empty), 0)

        # Test with less than 3 rows
        short_df_data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05']),
            'open':  [19.0, 22.0], 'high':  [20.0, 25.0],
            'low':   [18.0, 21.0], 'close': [19.5, 25.0]
        }
        short_df = pd.DataFrame(short_df_data)
        fvgs_short = detect_fvgs(short_df)
        self.assertEqual(len(fvgs_short), 0)

        # Test with NaN values in critical price columns
        nan_data = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [19.0, None, 25.5], # NaN in previous_candle open
            'high':  [20.0, 25.0, 28.0],
            'low':   [18.0, 21.0, 26.0],
            'close': [19.5, 25.0, 27.0]
        }
        nan_df = pd.DataFrame(nan_data)
        fvgs_nan = detect_fvgs(nan_df)
        self.assertEqual(len(fvgs_nan), 0, "FVG should not form if critical data is NaN")

        nan_data_current = {
            'time': pd.to_datetime(['2023-01-01 00:00', '2023-01-01 00:05', '2023-01-01 00:10']),
            'open':  [19.0, 22.0, 25.5],
            'high':  [20.0, 25.0, None], # NaN in current_candle high
            'low':   [18.0, 21.0, 26.0],
            'close': [19.5, 25.0, 27.0]
        }
        nan_df_current = pd.DataFrame(nan_data_current)
        fvgs_nan_current = detect_fvgs(nan_df_current)
        self.assertEqual(len(fvgs_nan_current), 0, "FVG should not form if current candle data is NaN for check")


if __name__ == '__main__':
    # Relative import for app.core_logic works when tests are run as a module
    # For direct script execution from fvgrab_app/tests, sys.path manipulation might be needed
    # or running as 'python -m unittest tests.test_fvg_detector'
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
