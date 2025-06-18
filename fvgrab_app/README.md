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
*   Supports an optional threshold percentage for the body size of the FVG's middle candle.

### Bybit API Integration (`app.services.bybit_service`)
*   **Historical Data:** Fetches historical kline (OHLCV) data using Bybit's v5 API (`get_historical_klines_bybit`).
*   **WebSocket for Live Data:** Setup for live kline data streaming via Bybit's v5 WebSocket API (`start_kline_websocket`).
    *   *Note: WebSocket subscription is currently facing a `TypeError` within the `pybit` library during the `subscribe` call, hindering live data functionality.*

### FastAPI Backend (`app.main`, `app.api.fvg_router`)
*   **REST API:**
    *   `GET /api/v1/fvgs/historical`: Endpoint to fetch historical kline data for a specified symbol, interval, and category, then detect FVGs on this data. Returns a list of detected FVGs with their parameters.
*   **WebSocket API:**
    *   `WS /api/v1/ws/fvg-stream/{category}/{symbol}/{interval}`: Endpoint designed to stream newly detected FVGs in real-time. Clients connect specifying the market and kline interval.
    *   *Note: Functionality is currently impacted by the aforementioned `pybit` WebSocket subscription issue.*
*   Basic static file serving and HTML template rendering for a simple frontend (index page).

### Backtesting Engine (`app.core_logic.backtester`)
*   **Simulation:** `run_backtest` function simulates trades based on detected FVGs from historical data.
    *   Iterates through klines, checking for FVG entry triggers.
    *   Manages a single active trade at a time.
    *   Exits trades based on Stop-Loss or Take-Profit levels being hit by candle highs/lows.
*   **PNL Calculation:**
    *   Calculates Profit and Loss (PNL) for each trade, accounting for percentage-based commissions.
    *   Currently uses a fixed position size of 1 unit of the base currency for PNL calculation.
*   **Performance Metrics:** `calculate_performance_metrics` function computes:
    *   Total Trades, Winning Trades, Losing Trades, Neutral Trades.
    *   Win Rate, Loss Rate.
    *   Profit Factor.
    *   Total Net PNL (Absolute).
    *   Average PNL per Trade, Average Profit per Winning Trade, Average Loss per Losing Trade.
    *   Average Holding Time (in hours).
    *   Maximum Drawdown (percentage of equity).
    *   Final and Peak Equity.
    *   A simplified Sharpe Ratio (based on per-trade percentage returns, unannualized, assumes zero risk-free rate).

## How to Run

1.  **Prerequisites:**
    *   Python 3.8+ (developed with 3.10/3.11/3.12 in mind).
    *   Access to a terminal or command prompt.

2.  **Clone Repository (Example):**
    ```bash
    # git clone <repository_url> # If accessing from a Git repo
    # cd fvgrab_app
    ```
    (In the current environment, the code is already in the `fvgrab_app` directory).

3.  **Install Dependencies:**
    Navigate to the `fvgrab_app` project root directory and run:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the FastAPI Application:**
    From within the `fvgrab_app` directory, execute:
    ```bash
    python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    ```
    *   `--reload`: Enables auto-reloading on code changes (useful for development).
    *   `--host 0.0.0.0`: Makes the server accessible from your local network.
    *   `--port 8000`: Specifies the port.

5.  **Access API Documentation:**
    Once the server is running, open your browser and go to:
    `http://localhost:8000/docs`
    This will load the Swagger UI, where you can interact with the API endpoints. The root `http://localhost:8000/` serves a basic HTML page.

## Project Structure

*   `fvgrab_app/`
    *   `app/`: Main application module.
        *   `main.py`: FastAPI application initialization, root endpoint, and uvicorn startup.
        *   `api/`: Contains API routers.
            *   `fvg_router.py`: Handles FVG-related REST and WebSocket endpoints.
        *   `core_logic/`: Core business logic.
            *   `fvg_detector.py`: Logic for detecting FVGs.
            *   `backtester.py`: Backtesting engine for FVG strategies.
        *   `services/`: Integration with external services.
            *   `bybit_service.py`: Bybit API (REST and WebSocket) interaction.
        *   `static/`: Static files (CSS, JS - for future frontend).
            *   `style.css`: Basic empty stylesheet.
        *   `templates/`: HTML templates.
            *   `index.html`: Basic landing page.
    *   `tests/`: Unit and integration tests (basic structure in place).
        *   `test_fvg_detector.py`: Example tests for FVG detection.
    *   `requirements.txt`: Python package dependencies.
    *   `README.md`: This file.

## Dependencies

Key Python libraries used:
*   **FastAPI:** Modern, fast (high-performance) web framework for building APIs.
*   **Uvicorn:** ASGI server for running FastAPI applications.
*   **Pybit:** Python SDK for interacting with the Bybit cryptocurrency exchange API.
*   **Pandas:** Powerful data manipulation and analysis library, used for OHLCV data.
*   **Numpy:** Fundamental package for numerical computation, used in performance metrics.
*   **Jinja2:** Templating engine (for the basic HTML page).

## Known Limitations & TODOs

*   **Bybit WebSocket Subscription Issue:** The live FVG streaming via WebSockets (`/api/v1/ws/fvg-stream/...`) is currently **non-functional** due to a persistent `TypeError` encountered within the `pybit` library (version 5.11.0) during the `subscribe` operation. This requires further investigation, a potential workaround, or a library update.
*   **Bybit REST API Testability:** During development in some sandboxed environments, direct calls to the Bybit REST API (for historical klines) failed. The implemented code for `bybit_service.get_historical_klines_bybit` is based on `pybit` documentation but requires testing in an open network environment to confirm full functionality.
*   **Backtester Position Sizing:** The backtesting engine currently uses a fixed position size of 1 unit of the base currency. Future enhancements should include variable position sizing (e.g., risk-based).
*   **Simplified Metrics:** Some performance metrics (like Sharpe Ratio) are simplified.
*   **No Frontend UI:** The project currently focuses on the backend API. A frontend UI for interacting with the application is a future goal.
*   Refer to `TODO` comments embedded within the source code for more specific planned enhancements, bug fixes, and areas for improvement.

## Contributing (Placeholder)

Contributions to FVGrab are welcome! If you'd like to contribute, please feel free to fork the repository (if applicable), make your changes, and submit a pull request. For major changes, please open an issue first to discuss what you would like to change.

---

*This README provides a snapshot of the project's status and capabilities. Refer to the source code and inline comments for the most detailed and up-to-date information.*
