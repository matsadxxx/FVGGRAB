"""
Main application file for FVGrab.

This file initializes the FastAPI application, sets up static file serving,
HTML templates, and includes the API routers. It also contains the
main entry point for running the Uvicorn server.
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.responses import HTMLResponse # For serving HTML pages
import logging
import os

# TODO: Implement robust application configuration management:
#   - Use environment variables for sensitive data (e.g., API keys if used for private endpoints in Bybit).
#   - Configuration for testnet/mainnet toggles for services (e.g., Bybit service).
#   - Centralized logging configuration (levels, formats, handlers).
#   - Consider using a library like Pydantic for settings management (e.g., `pydantic-settings`).

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="FVGrab - FVG Monitoring Dashboard & Backtester",
    description="API for detecting Fair Value Gaps (FVGs) from Bybit market data, "
                "streaming live FVGs, and backtesting FVG-based strategies.",
    version="0.1.0"
)

# Determine base directory of the application module
base_dir = os.path.dirname(os.path.abspath(__file__))

static_dir = os.path.join(base_dir, "static")
templates_dir = os.path.join(base_dir, "templates")

# Ensure static/templates directories exist (especially for environments where they might be missing)
if not os.path.exists(static_dir):
    logger.warning(f"Static directory not found at {static_dir}. Creating it.")
    os.makedirs(static_dir, exist_ok=True)
    # Create js subdir if it doesn't exist
    js_dir = os.path.join(static_dir, "js")
    if not os.path.exists(js_dir):
        os.makedirs(js_dir, exist_ok=True)
        logger.info(f"Created js directory at {js_dir}")
        # Create an empty backtest.js if it's missing, to prevent 404s from template
        # Though it should be created by another step, this is a safeguard.
        if not os.path.exists(os.path.join(js_dir, "backtest.js")):
            with open(os.path.join(js_dir, "backtest.js"), "w") as f:
                f.write("// Placeholder backtest.js - should be populated by its creation step\nconsole.log('backtest.js loaded');")
            logger.info("Created placeholder backtest.js")


if not os.path.exists(templates_dir):
    logger.warning(f"Templates directory not found at {templates_dir}. Creating it.")
    os.makedirs(templates_dir, exist_ok=True)
    # Create an empty index.html if it's missing
    if not os.path.exists(os.path.join(templates_dir, "index.html")):
         with open(os.path.join(templates_dir, "index.html"), "w") as f:
            f.write("<!DOCTYPE html><html><head><title>FVGrab</title></head><body><h1>Welcome to FVGrab (Placeholder Index)</h1><p><a href='/ui/backtester'>Run Backtester</a></p></body></html>")
         logger.info("Created placeholder index.html")
    # Create an empty backtest_runner.html if it's missing
    if not os.path.exists(os.path.join(templates_dir, "backtest_runner.html")):
         with open(os.path.join(templates_dir, "backtest_runner.html"), "w") as f:
            f.write("<!DOCTYPE html><html><head><title>Backtester</title></head><body><h1>Backtester UI (Placeholder)</h1><p>Content should be populated by its creation step.</p></body></html>")
         logger.info("Created placeholder backtest_runner.html")


app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

from app.api import fvg_router
app.include_router(fvg_router.router, prefix="/api/v1")

# --- UI Endpoints ---
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def read_root_html(request: Request):
    """Serves the main landing page (index.html)."""
    logger.info("Serving root page (index.html)")
    return templates.TemplateResponse("index.html", {"request": request, "title": "Welcome to FVGrab"})

@app.get("/ui/backtester", response_class=HTMLResponse, include_in_schema=False)
async def get_backtester_page(request: Request):
    """Serves the backtester UI page."""
    logger.info("Serving backtester UI page (backtest_runner.html)")
    return templates.TemplateResponse("backtest_runner.html", {"request": request, "title": "FVGrab Backtester"})

# --- Main Entry Point for Uvicorn ---
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting FVGrab application with Uvicorn...")
    # Host, port, reload should be ideally configured via environment variables or CLI for production.
    # For development, these defaults are fine.
    host = os.getenv("FVGRAB_HOST", "0.0.0.0")
    port = int(os.getenv("FVGRAB_PORT", "8000"))
    reload = os.getenv("FVGRAB_RELOAD", "true").lower() == "true"

    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
