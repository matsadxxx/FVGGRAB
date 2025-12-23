import asyncio
import unittest
from unittest.mock import patch, AsyncMock # Requires Python 3.8+ for AsyncMock
import pandas as pd
from typing import List, Dict, Any, Optional

# Adjust sys.path to allow imports from 'app'
import sys
import os
script_dir = os.path.dirname(os.path.abspath(__file__)) # .../fvgrab_app/tests
project_root = os.path.dirname(script_dir) # .../fvgrab_app
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.services import scanner_service # Import the module to be tested

class TestScannerService(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.fvg_params_default = {
            "static_threshold_percent": 0.0,
            "use_adaptive_threshold": False,
            "adaptive_threshold_period_UNUSED": 0,
            "use_volume_confirmation": False,
            "volume_lookback_period": 20,
            "volume_factor": 1.5,
            "min_fvg_price_height": 0.0
        }
        self.sample_ohlcv_data = pd.DataFrame({
            'time': pd.to_datetime(['2023-01-01 10:00', '2023-01-01 10:05', '2023-01-01 10:10', '2023-01-01 10:15']),
            'open': [100, 101, 102, 103], 'high': [105, 106, 107, 108],
            'low': [99, 100, 101, 102], 'close': [101, 102, 103, 104],
            'volume': [1000, 1100, 1200, 1300]
        })

    async def test_scan_symbols_for_fvgs_no_input(self): # Renamed for clarity
        """Test scan_symbols_for_fvgs with empty symbols list or if intervals logic was different."""
        with patch('app.services.scanner_service._fetch_and_detect_for_pair', new_callable=AsyncMock) as mock_helper:
            # Test with empty symbols list
            result_no_symbols = await scanner_service.scan_symbols_for_fvgs(
                symbols=[],
                interval="60", # Corrected: single interval
                category="linear",
                kline_limit=10,
                fvg_detection_params=self.fvg_params_default
            )
            self.assertEqual(result_no_symbols, [])
            mock_helper.assert_not_called()

            # Test with symbols but if intervals were incorrectly handled (original test logic)
            # This part of test becomes less relevant as API itself loops intervals.
            # For service, it expects one interval.
            # If API passes empty intervals list, it won't call service.
            # This test is now primarily for empty symbols list.
            # To test "no intervals" case, that would be an API level test for fvg_router.

    @patch('app.services.scanner_service._fetch_and_detect_for_pair', new_callable=AsyncMock)
    async def test_scan_symbols_for_fvgs_aggregates_results(self, mock_fetch_detect):
        """Test scan_symbols_for_fvgs aggregates results from helper correctly for a single interval."""
        mock_result_btc = {"symbol": "BTCUSDT", "fvgs": [{"type": "bullish"}]}
        mock_result_eth = {"symbol": "ETHUSDT", "fvgs": [{"type": "bearish"}]}

        mock_fetch_detect.side_effect = [mock_result_btc, mock_result_eth]

        symbols_to_scan = ["BTCUSDT", "ETHUSDT"]
        interval_to_scan = "60" # Single interval for this service unit test

        results = await scanner_service.scan_symbols_for_fvgs(
            symbols=symbols_to_scan,
            interval=interval_to_scan, # Corrected
            category="linear", kline_limit=30,
            fvg_detection_params=self.fvg_params_default
        )

        self.assertEqual(mock_fetch_detect.call_count, 2)
        self.assertIn(mock_result_btc, results)
        self.assertIn(mock_result_eth, results)
        self.assertEqual(len(results), 2)

    @patch('app.services.scanner_service._fetch_and_detect_for_pair', new_callable=AsyncMock)
    async def test_scan_symbols_for_fvgs_handles_helper_exception(self, mock_fetch_detect):
        """Test scan_symbols_for_fvgs handles exceptions from _fetch_and_detect_for_pair."""
        mock_fvg_ok = {"symbol": "OK_SYMBOL", "fvgs": [{"type": "bullish"}]}

        mock_fetch_detect.side_effect = [
            Exception("Simulated processing error"), # FAIL_SYMBOL
            mock_fvg_ok                          # OK_SYMBOL
        ]

        results = await scanner_service.scan_symbols_for_fvgs(
            symbols=["FAIL_SYMBOL", "OK_SYMBOL"],
            interval="60", # Corrected
            fvg_detection_params=self.fvg_params_default
        )

        self.assertEqual(mock_fetch_detect.call_count, 2)
        # scan_symbols_for_fvgs filters out results that are Exceptions
        self.assertEqual(len(results), 1, "Should return results for successful calls only")
        self.assertIn(mock_fvg_ok, results)

    # Patch target for get_historical_klines_bybit should be where it's LOOKED UP (i.e. in scanner_service)
    @patch('app.services.scanner_service.get_historical_klines_bybit', new_callable=AsyncMock)
    @patch('app.services.scanner_service.detect_fvgs') # detect_fvgs is also imported into scanner_service
    async def test_fetch_and_detect_for_pair_no_data_returned(self, mock_detect_fvgs, mock_get_klines):
        """Test _fetch_and_detect_for_pair when kline service returns None or empty DataFrame."""
        # Case 1: get_historical_klines_bybit returns None
        mock_get_klines.return_value = None
        result_none = await scanner_service._fetch_and_detect_for_pair(
            "BTCUSDT", "60", "linear", 100, self.fvg_params_default
        )
        self.assertIsNone(result_none, "Should return None if klines are None")
        mock_detect_fvgs.assert_not_called()

        # Case 2: get_historical_klines_bybit returns empty DataFrame
        mock_get_klines.reset_mock()
        mock_detect_fvgs.reset_mock()
        mock_get_klines.return_value = pd.DataFrame() # Set new return value for this case
        result_empty_df = await scanner_service._fetch_and_detect_for_pair(
            "BTCUSDT", "60", "linear", 100, self.fvg_params_default
        )
        self.assertIsNotNone(result_empty_df)
        self.assertEqual(result_empty_df["symbol"], "BTCUSDT")
        self.assertEqual(result_empty_df["fvgs"], [])
        mock_detect_fvgs.assert_not_called() # Should not be called if df is empty

    @patch('app.services.scanner_service.get_historical_klines_bybit', new_callable=AsyncMock)
    @patch('app.services.scanner_service.detect_fvgs')
    async def test_fetch_and_detect_for_pair_with_data_no_fvgs(self, mock_detect_fvgs, mock_get_klines):
        """Test _fetch_and_detect_for_pair when klines have data but no FVGs are found."""
        mock_get_klines.return_value = self.sample_ohlcv_data
        mock_detect_fvgs.return_value = [] # No FVGs detected

        result = await scanner_service._fetch_and_detect_for_pair(
            "BTCUSDT", "60", "linear", 100, self.fvg_params_default
        )

        mock_get_klines.assert_called_once()
        # Check that detect_fvgs was called with the DataFrame and the fvg_params
        # We need to use unittest.mock.ANY for the DataFrame if we don't want to assert exact DF content
        # For simplicity, let's assume the df passed is the one from mock_get_klines
        args, kwargs = mock_detect_fvgs.call_args
        pd.testing.assert_frame_equal(args[0], self.sample_ohlcv_data)
        self.assertEqual(kwargs, self.fvg_params_default)

        self.assertIsNotNone(result)
        self.assertEqual(result["symbol"], "BTCUSDT")
        self.assertEqual(result["fvgs"], [])

    @patch('app.services.scanner_service.get_historical_klines_bybit', new_callable=AsyncMock)
    @patch('app.services.scanner_service.detect_fvgs')
    async def test_fetch_and_detect_for_pair_returns_all_found_fvgs(self, mock_detect_fvgs, mock_get_klines):
        """Test _fetch_and_detect_for_pair returns all FVGs found by detector and adds symbol."""
        mock_get_klines.return_value = self.sample_ohlcv_data

        fvg1 = {'type': 'bullish', 'trigger_candle_time': pd.Timestamp("2023-01-01 10:10:00")}
        fvg2 = {'type': 'bearish', 'trigger_candle_time': pd.Timestamp("2023-01-01 10:15:00")}
        mock_detect_fvgs.return_value = [fvg1, fvg2] # Detector found these

        result = await scanner_service._fetch_and_detect_for_pair(
            "TESTSYMBOL", "15", "spot", 30, self.fvg_params_default
        )

        mock_get_klines.assert_called_once_with(symbol="TESTSYMBOL", interval="15", limit=30, category="spot")
        args, kwargs = mock_detect_fvgs.call_args
        pd.testing.assert_frame_equal(args[0], self.sample_ohlcv_data)
        self.assertEqual(kwargs, self.fvg_params_default)

        self.assertIsNotNone(result)
        self.assertEqual(result["symbol"], "TESTSYMBOL")
        self.assertEqual(len(result["fvgs"]), 2) # Should return all FVGs from detector
        self.assertIn(fvg1, result["fvgs"])
        self.assertIn(fvg2, result["fvgs"])

if __name__ == '__main__':
    unittest.main()
