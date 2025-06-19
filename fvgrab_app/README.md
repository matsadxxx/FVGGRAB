# FVGrab - Fair Value Gap Analyzer & Backtester

## Overview

FVGrab is a Python-based application designed to detect Fair Value Gaps (FVGs) in financial market data, primarily focusing on cryptocurrency markets via the Bybit API. It provides tools for fetching historical data, identifying FVG patterns, backtesting FVG-based trading strategies, and scanning multiple symbols for current FVGs. The application is built using FastAPI for its backend API and WebSocket communication.

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

### Symbol Scanner Service (`app.services.scanner_service`)
*   **Multi-Symbol Scanning:** Concurrently scans a list of symbols over a specified interval for FVGs using `scan_symbols_for_fvgs`.
*   Utilizes the FVG detection logic with configurable parameters.
*   Handles API errors per symbol gracefully.

### FastAPI Backend (`app.main`, `app.api.*_router.py`)
*   **REST API:**
    *   `GET /api/v1/fvgs/historical`: Endpoint to fetch historical kline data and detect FVGs using configurable detection parameters.
    *   `POST /api/v1/backtest/run`: Endpoint to run a full backtest using specified market parameters, FVG detection settings, and backtester configurations. Returns detailed trade lists and performance metrics.
    *   `POST /api/v1/scanner/run-scan`: Accepts a list of symbols, intervals, and FVG detection parameters to scan for current FVGs concurrently.
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
*   **Performance Metrics:** `calculate_performance_metrics` function computes a comprehensive set of metrics (Win Rate, Profit Factor, Max Drawdown, simplified Sharpe Ratio, etc.).

### Basic Web Interface
*   `/ui/backtester`: An HTML page with a form to input all parameters for running a backtest and display the results (metrics and trades table) dynamically using JavaScript.

## How to Run

1.  **Prerequisites:** Python 3.8+, Pip.
2.  **Clone/Setup:** Get the code into `fvgrab_app` directory.
3.  **Install Dependencies:** `cd fvgrab_app && pip install -r requirements.txt`
4.  **Run Application:** `python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` (from `fvgrab_app` directory).
5.  **Access Application:**
    *   API Docs (Swagger UI): `http://localhost:8000/docs`
    *   Backtester UI: `http://localhost:8000/ui/backtester`
    *   Root Page: `http://localhost:8000/`

## Project Structure (Key Components)

*   `fvgrab_app/app/main.py`: FastAPI app initialization, UI endpoints.
*   `fvgrab_app/app/api/`: API routers (`fvg_router.py`, `scanner_router.py`).
*   `fvgrab_app/app/core_logic/`: Business logic (`fvg_detector.py`, `backtester.py`).
*   `fvgrab_app/app/services/`: External services (`bybit_service.py`, `scanner_service.py`).
*   `fvgrab_app/app/static/` & `app/templates/`: Basic frontend files.
*   `fvgrab_app/tests/`: Unit tests.
*   `fvgrab_app/tools/`: Utility/manual test scripts.

## Dependencies
FastAPI, Uvicorn, Pybit, Pandas, Numpy, Jinja2, HTTPX.

## Project Status Summary (Based on Sandbox Investigations)

*   **Bybit REST API Connectivity:** Live fetching of historical kline data is **blocked** (Bybit returns 403 Forbidden, likely IP restriction). `bybit_service.py` handles this error. Backtests and historical FVG analysis needing live data are impacted in this environment. The scanner API endpoint, for instance, was tested and correctly returns empty results due to this.
*   **Bybit WebSocket Subscription:** **Non-functional**. Attempts to subscribe via `pybit` v5.11.0 result in a `TypeError: 'bool' object is not iterable` within `pybit`. Live FVG streaming is not operational.
*   **Unit Test Execution:**
    *   `ModuleNotFoundError` for tests was resolved by setting `PYTHONPATH=/app/fvgrab_app`.
    *   `test_fvg_detector.py` (14 tests): **All PASS**. FVG detection logic (including adaptive thresholds, volume, and size filters) is functioning as expected.
    *   `test_scanner_service.py` (6 tests): **All PASS**. Scanner service orchestration logic is correct under mocked conditions.
    *   `test_backtester.py` (4 tests): 2 tests **FAILING** due to a persistent `KeyError: 'fvg_type'`. This indicates an issue where code corrections in `backtester.py` (changing `fvg['fvg_type']` to `fvg['type']`) are not reflected at runtime in the sandbox, possibly due to file caching or module reloading issues. Core backtesting logic with position sizing is implemented but not fully verifiable by its tests due to this.
*   **Overall Application State:**
    *   Core FVG detection and backtesting engines are implemented with key features. FastAPI endpoints provide access to these. A basic UI for backtests exists.
    *   FVG detection and scanner service logic are unit-tested and largely passing.
    *   **Key Blockers:** Bybit API access restrictions and the runtime code update issue for `backtester.py` prevent full end-to-end validation and functionality of live data features and some backtesting test cases.

## Known Limitations & TODOs (General)
*   **Resolve `backtester.py` Runtime Issue:** Investigate why changes to `backtester.py` (correcting `fvg_type` key access) are not reflected in the test execution environment.
*   **Backtester Enhancements:** Slippage modeling, handling of trades open at data end, more position sizing models.
*   **Performance Metrics:** More rigorous Sharpe Ratio, Buy & Hold return, Sortino, Calmar, etc.
*   **API & Service Layer:** Robust retry for Bybit REST calls; investigate `pybit` WebSocket `TypeError` or alternatives; API pagination.
*   **Configuration & Logging:** Centralized and environment-driven configuration; structured logging.
*   **Frontend UI:** Develop a more comprehensive frontend.
*   Refer to specific `TODO` comments in the source code.

## Contributing (Placeholder)
Contributions welcome. Please open an issue for major changes.

---
*This README provides a snapshot of the project's status. Refer to source code and inline comments for details.*
