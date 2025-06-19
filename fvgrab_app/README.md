# FVGrab - Fair Value Gap Analyzer & Backtester

## Overview

FVGrab is a Python-based application designed to detect Fair Value Gaps (FVGs) in financial market data, primarily focusing on cryptocurrency markets via the Bybit API. It provides tools for fetching historical data, identifying FVG patterns, and backtesting basic FVG-based trading strategies. The application is built using FastAPI for its backend API and WebSocket communication.

## Current Features

### FVG Detection (`app.core_logic.fvg_detector`)
*   Identifies the classic 3-candle bullish and bearish Fair Value Gaps from OHLCV data.
*   Calculates potential trade parameters for each FVG:
    *   Entry price (midpoint of the FVG).
    *   Stop-Loss (SL) price (low/high of the candle prior to the FVG's middle candle).
    *   Take-Profit (TP) price (based on a 2:1 reward:risk ratio from the entry and SL).
*   Supports multiple filtering options for FVG qualification:
    *   Static percentage threshold for the middle candle's body size.
    *   Adaptive percentage threshold (based on `2 * cumulative average absolute body %`).
    *   Volume confirmation (middle candle volume vs. rolling average).
    *   Minimum FVG price height (absolute price units).

### Bybit API Integration (`app.services.bybit_service`)
*   **Historical Data:** Fetches historical kline (OHLCV) data using Bybit's v5 API (`get_historical_klines_bybit`).
*   **WebSocket for Live Data:** Setup for live kline data streaming via Bybit's v5 WebSocket API (`start_kline_websocket`).

### FastAPI Backend (`app.main`, `app.api.fvg_router`)
*   **REST API:**
    *   `GET /api/v1/fvgs/historical`: Endpoint to fetch historical kline data and detect FVGs using configurable detection parameters.
    *   `POST /api/v1/backtest/run`: Endpoint to run a full backtest using specified market parameters, FVG detection settings, and backtester configurations (initial balance, risk, commission). Returns detailed trade lists and performance metrics.
*   **WebSocket API:**
    *   `WS /api/v1/ws/fvg-stream/{category}/{symbol}/{interval}`: Endpoint designed to stream newly detected FVGs in real-time, using configurable FVG detection parameters per stream.
*   Basic static file serving and HTML template rendering for UI pages (`/`, `/ui/backtester`).

### Backtesting Engine (`app.core_logic.backtester`)
*   **Simulation:** `run_backtest` function simulates trades based on detected FVGs from historical data.
    *   Implements risk-based position sizing (percentage of current balance per trade).
    *   Iterates through klines, checking for FVG entry triggers.
    *   Manages a single active trade at a time.
    *   Exits trades based on Stop-Loss or Take-Profit levels.
*   **PNL Calculation:** Calculates Profit and Loss (PNL) for each trade, accounting for percentage-based commissions and variable position sizes. `pnl_percent` is calculated as return on risked capital.
*   **Performance Metrics:** `calculate_performance_metrics` function computes a comprehensive set of metrics:
    *   Total Trades, Winning/Losing/Neutral Trades, Win/Loss Rate, Profit Factor.
    *   Total Net PNL (Absolute), Average PNL per Trade, Average Profit/Loss per Winning/Losing Trade.
    *   Average Holding Time, Total Commissions Paid.
    *   Maximum Drawdown (percentage of equity), Final and Peak Equity.
    *   A simplified Sharpe Ratio (based on per-trade percentage returns on risked capital).

### Basic Web Interface
*   `/ui/backtester`: An HTML page with a form to input all parameters for running a backtest and display the results (metrics and trades table) dynamically using JavaScript.

## How to Run

1.  **Prerequisites:**
    *   Python 3.8+ (developed with 3.10-3.12 in mind).
    *   Pip for package installation.

2.  **Clone Repository (Example):**
    ```bash
    # git clone <repository_url>
    # cd fvgrab_app
    ```

3.  **Install Dependencies:**
    Navigate to the `fvgrab_app` project root directory and run:
    ```bash
    pip install -r requirements.txt
    ```
    (Ensure `httpx` is included for `TestClient` functionality if running test scripts that use it).

4.  **Run the FastAPI Application:**
    From within the `fvgrab_app` directory, execute:
    ```bash
    python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    ```

5.  **Access Application:**
    *   **API Docs (Swagger UI):** `http://localhost:8000/docs`
    *   **Backtester UI:** `http://localhost:8000/ui/backtester`
    *   **Root Page:** `http://localhost:8000/`

## Project Structure

*   `fvgrab_app/`
    *   `app/`: Main application module.
        *   `main.py`: FastAPI app initialization, UI endpoints.
        *   `api/fvg_router.py`: API (REST & WebSocket) and Backtest endpoints.
        *   `core_logic/fvg_detector.py`: FVG detection algorithms.
        *   `core_logic/backtester.py`: Backtesting engine and performance metrics.
        *   `services/bybit_service.py`: Bybit API interaction (REST & WebSocket).
        *   `static/js/backtest.js`: Client-side JavaScript for the backtester UI.
        *   `templates/backtest_runner.html`: HTML for the backtester UI.
        *   `templates/index.html`: Basic landing page.
    *   `tests/`: Unit tests.
        *   `test_fvg_detector.py`: Tests for FVG detection logic.
        *   `test_backtester.py`: Tests for the backtesting engine.
    *   `tools/`: Utility/test scripts.
        *   `test_bybit_rest.py`: Script for testing Bybit REST API connectivity.
        *   `test_backtest_api_nofetch.py`: Script for testing backtest API endpoint error handling.
    *   `requirements.txt`: Python package dependencies.
    *   `README.md`: This file.

## Dependencies

Key Python libraries used: FastAPI, Uvicorn, Pybit, Pandas, Numpy, Jinja2, HTTPX (for TestClient).

## Project Status Summary (Based on Sandbox Investigations)

This section summarizes the operational status of key components based on testing within the development sandbox environment.

*   **Bybit REST API Connectivity:** Live fetching of historical kline data via Bybit's REST API (e.g., for backtests or historical FVG analysis) is currently **blocked**. Bybit returns a `403 Forbidden` error, likely due to IP address restrictions (geo-blocking or general cloud IP block) from the execution environment. The application's service layer (`bybit_service.py`) correctly handles this error and returns `None`, which in turn causes API endpoints relying on this data to report service unavailability (e.g., HTTP 503).
    *   _Impact:_ End-to-end testing of features requiring live Bybit historical data is not possible in this environment. The logic is implemented but cannot be fully validated against live API responses.

*   **Bybit WebSocket Subscription:** Subscription to live kline data via Bybit WebSockets (using `pybit` v5.11.0) is **non-functional**. Attempts to subscribe (e.g., to `kline.1.BTCUSDT`) consistently result in a `TypeError: 'bool' object is not iterable` originating from within the `pybit` library's `prepare_subscription_args` function. This issue persists across various tested calling patterns and topic types.
    *   _Impact:_ The live FVG streaming WebSocket endpoint (`/api/v1/ws/fvg-stream/...`) cannot receive data from Bybit and is therefore not operational for its primary purpose.

*   **Unit Test Execution:**
    *   **Import Resolution:** `ModuleNotFoundError` issues previously encountered when running tests were **resolved** by ensuring the `PYTHONPATH` environment variable was set to the project root (`/app/fvgrab_app`) during test execution. This allowed `unittest` to correctly discover and import modules from the `app` package.
    *   **`test_fvg_detector.py`:** All 14 tests in this suite **PASS**. This indicates the FVG detection logic, including static and adaptive thresholds, volume confirmation, and minimum FVG size filters, is functioning as expected according to the defined test cases.
    *   **`test_backtester.py`:** Currently, 2 out of 4 tests are **FAILING**. These failures are due to a persistent `KeyError: 'fvg_type'` when `backtester.py` attempts to access `fvg['fvg_type']` from an FVG dictionary. The FVG dictionaries produced by `fvg_detector.py` use the key `'type'`. Multiple attempts to correct this key access in `backtester.py` (changing to `fvg['type']`) using file overwrite tools have not been reflected at runtime in the execution environment, suggesting a possible file caching, update propagation, or module reloading issue within the sandbox.
        *   _Impact:_ The core backtesting logic, including risk-based position sizing and PNL calculations, is implemented but cannot be fully verified by its unit tests in this environment due to this runtime anomaly preventing the code fix from taking effect.

*   **Overall Application State:**
    *   The application's codebase includes a comprehensive FVG detection engine with multiple filters, a backtesting engine featuring risk-based position sizing and detailed performance metrics, FastAPI endpoints for accessing these features (REST for historical/backtest, WebSocket for intended live streaming), and a basic web UI for triggering backtests.
    *   The core FVG detection logic is unit-tested and confirmed to be working correctly.
    *   The backtesting API endpoint (`/api/v1/backtest/run`) is structurally sound and handles errors related to data fetching as expected (verified using `TestClient`).
    *   **Key Blockers:**
        1.  External Bybit API access (both REST and WebSocket) is restricted/non-functional in the current environment.
        2.  A runtime issue is preventing a necessary code correction in `backtester.py` from being applied, which blocks full unit test validation of the backtesting engine.

## Known Limitations & TODOs (General)

*   **Backtester Enhancements:**
    *   Implement more advanced order execution simulation (slippage modeling).
    *   Add logic to handle trades open at the end of historical data.
    *   Consider FVG expiration if not entered within N candles.
    *   Implement variable position sizing beyond the current risk-percentage model (e.g., fixed monetary amount, Kelly criterion).
*   **Performance Metrics:**
    *   Implement a more rigorous, annualized Sharpe Ratio.
    *   Calculate Buy and Hold return for comparison in backtests.
    *   Generate data for equity curve plotting.
    *   Add other metrics like Sortino Ratio, Calmar Ratio, win/loss streaks.
*   **API & Service Layer:**
    *   Implement robust retry mechanisms for Bybit API calls.
    *   For WebSockets: Investigate `pybit` TypeError or alternative libraries if it persists; implement auto-reconnect and health monitoring for WebSocket connections.
    *   Consider pagination for API endpoints that might return large lists of data (e.g., historical FVGs over very long periods).
*   **Configuration & Logging:**
    *   Implement robust application configuration (e.g., using Pydantic settings, environment variables for API keys, testnet toggles, logging levels).
    *   Set up centralized, structured logging.
*   **Frontend UI:** Develop a more comprehensive frontend UI for better interaction with all application features.
*   Refer to specific `TODO` comments embedded within the source code for more granular planned enhancements and known minor issues.

## Contributing (Placeholder)

Contributions to FVGrab are welcome! If you'd like to contribute, please feel free to fork the repository (if applicable), make your changes, and submit a pull request. For major changes, please open an issue first to discuss what you would like to change.

---

*This README provides a snapshot of the project's status and capabilities. Refer to the source code and inline comments for the most detailed and up-to-date information.*
