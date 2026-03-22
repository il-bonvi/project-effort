"""
WEBAPP - FastAPI web application for PEFFORT
Main entry point - Imports and registers modular routes from /routes directory
Each route module handles a specific functional area and uses APIRouter pattern
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Import routers and their setup functions
from routes.home import router as home_router, setup_home_router
from routes.upload import router as upload_router, setup_upload_router
from routes.dashboard import (
    router as dashboard_router, setup_dashboard_router
)
from routes.inspection import (
    router as inspection_router, setup_inspection_router
)
from routes.altimetria import (
    router as altimetria_router, setup_altimetria_router
)
from routes.altimetria_echarts import (
    router as altimetria_echarts_router, setup_altimetria_echarts_router
)
from routes.altimetria_d3 import (
    router as altimetria_d3_router, setup_altimetria_d3_router
)
from routes.map3d import router as map3d_router, setup_map3d_router
from routes.api import router as api_router, setup_api_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# FASTAPI APPLICATION INITIALIZATION
# ============================================================================

app = FastAPI(
    title="PEFFORT Web",
    description="Web interface for FIT file analysis and effort inspection",
    version="1.0.0"
)

# Mount static files directory
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Session storage (in-memory, stores analysis results and dataframes)
# Shared across all route modules via setup_XXXX_router(sessions) functions
sessions: Dict[str, Dict[str, Any]] = {}

logger.info("Initializing PEFFORT Web Application...")

# Initialize all route modules with shared sessions dictionary
logger.info("Setting up route modules with shared sessions...")
setup_home_router(sessions)
setup_upload_router(sessions)
setup_dashboard_router(sessions)
setup_inspection_router(sessions)
setup_altimetria_router(sessions)
setup_altimetria_echarts_router(sessions)
setup_altimetria_d3_router(sessions)
setup_map3d_router(sessions)
setup_api_router(sessions)

# Register all routers with the FastAPI application
# Registration order: home → upload → dashboard → inspection → altimetria → map3d → API
logger.info("Registering routes...")
app.include_router(home_router, tags=["home"])
app.include_router(upload_router, tags=["upload"])
app.include_router(dashboard_router, tags=["dashboard"])
app.include_router(inspection_router, tags=["inspection"])
app.include_router(altimetria_router, tags=["altimetria"])
app.include_router(altimetria_echarts_router, tags=["altimetria-echarts"])
app.include_router(altimetria_d3_router, tags=["altimetria-d3"])
app.include_router(map3d_router, tags=["map3d"])
app.include_router(api_router, tags=["api"])

logger.info("PEFFORT Web Application initialized successfully!")
logger.info("Available endpoints:")
logger.info("  GET  /                      - Home page with upload form")
logger.info("  POST /upload                - Upload and analyze FIT file")
logger.info(
    "  GET  /dashboard/{id}        - View analysis dashboard"
)
logger.info(
    "  GET  /inspection/{id}       - Interactive effort editor"
)
logger.info(
    "  GET  /altimetria/{id}       - Elevation profile visualization"
)
logger.info(
    "  GET  /altimetria-echarts/{id} - Elevation profile with ECharts.js"
)
logger.info(
    "  GET  /map3d/{id}            - 3D map with terrain visualization"
)
logger.info(
    "  GET  /api/session-data/{id} - Get session data as JSON"
)
logger.info(
    "  ...  /api/*                 - Various API endpoints "
    "(see routes/api.py)"
)


# ============================================================================
# STARTUP/SHUTDOWN EVENTS (if needed for future enhancements)
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Called when application starts"""
    logger.info("PEFFORT Web app started on http://localhost:8000")


@app.on_event("shutdown")
async def shutdown_event():
    """Called when application shuts down"""
    logger.info("PEFFORT Web app shut down")


# ============================================================================
# MAIN - Run with Uvicorn
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
