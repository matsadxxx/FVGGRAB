from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request # Required for templates

# Import the router
from app.api import fvg_router

app = FastAPI(title="FVGrab - FVG Monitoring Dashboard")

# Mount static files directory (for CSS, JS)
# Ensure the path "app/static" is correct relative to where uvicorn is run.
# If running from fvgrab_app/, then "app/static" is fine.
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# Setup templates directory
templates = Jinja2Templates(directory="app/templates")

@app.get("/")
async def read_root_html(request: Request): # Added request parameter
    # Example of rendering a template
    return templates.TemplateResponse("index.html", {"request": request, "title": "Welcome"})


# Include the API router
app.include_router(fvg_router.router, prefix="/api/v1", tags=["fvg"])

if __name__ == "__main__":
    import uvicorn
    # Running from fvgrab_app directory, so app.main:app
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
