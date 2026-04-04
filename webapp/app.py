"""
WEBAPP - FastAPI web application for PEFFORT
Main entry point - Imports and registers modular routes from /routes directory
Each route module handles a specific functional area and uses APIRouter pattern
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sessions import SessionStore

# Import routers and their setup functions
from routes.home import router as home_router, setup_home_router
from routes.upload import router as upload_router, setup_upload_router
from routes.dashboard import (
    router as dashboard_router, setup_dashboard_router
)
from routes.inspection import (
    router as inspection_router, setup_inspection_router
)
from routes.altimetria_d3 import (
    router as altimetria_d3_router, setup_altimetria_d3_router
)
from routes.map3d import router as map3d_router, setup_map3d_router
from routes.map2d import router as map2d_router, setup_map2d_router
from routes.api import router as api_router, setup_api_router

# Configure logging
_log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)
logging.basicConfig(level=_log_level)
logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

# ============================================================================
# FASTAPI APPLICATION INITIALIZATION
# ============================================================================

@asynccontextmanager
async def lifespan(_: FastAPI):
    async def cleanup_task():
        while True:
            await asyncio.sleep(3600)
            sessions.cleanup()
            logger.info("Periodic session cleanup completed")

    task = asyncio.create_task(cleanup_task())

    maptiler_key_present = bool(os.getenv("MAPTILER_API_KEY", "").strip())
    maptiler_restriction_ack = _env_bool("MAPTILER_KEY_DOMAIN_RESTRICTED", default=False)
    if maptiler_key_present and not maptiler_restriction_ack:
        logger.warning(
            "MAPTILER_API_KEY is configured but MAPTILER_KEY_DOMAIN_RESTRICTED is false. "
            "Restrict the key by domain/referrer in MapTiler dashboard."
        )

    logger.info("PEFFORT Web app started on http://localhost:8001")
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        logger.info("PEFFORT Web app shut down")


app = FastAPI(
    title="PEFFORT Web",
    description="Web interface for FIT file analysis and effort inspection",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files directory
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Session storage (in-memory, stores analysis results and dataframes)
# Shared across all route modules via setup_XXXX_router(sessions) functions
sessions: Dict[str, Dict[str, Any]] = SessionStore(max_sessions=20, ttl_seconds=86400)

logger.info("Initializing PEFFORT Web Application...")

# Initialize all route modules with shared sessions dictionary
logger.info("Setting up route modules with shared sessions...")
setup_home_router(sessions)
setup_upload_router(sessions)
setup_dashboard_router(sessions)
setup_inspection_router(sessions)
setup_altimetria_d3_router(sessions)
setup_map3d_router(sessions)
setup_map2d_router(sessions)
setup_api_router(sessions)

# Register all routers with the FastAPI application
# Registration order: home → upload → dashboard → inspection → altimetria → map3d → API
logger.info("Registering routes...")
app.include_router(home_router, tags=["home"])
app.include_router(upload_router, tags=["upload"])
app.include_router(dashboard_router, tags=["dashboard"])
app.include_router(inspection_router, tags=["inspection"])
app.include_router(altimetria_d3_router, tags=["altimetria-d3"])
app.include_router(map3d_router, tags=["map3d"])
app.include_router(map2d_router, tags=["map2d"])
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
    "GET  /altimetria-d3/{id}    - Elevation profile visualization (D3.js)"
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


@app.get("/health")
async def health():
    maptiler_key_present = bool(os.getenv("MAPTILER_API_KEY", "").strip())
    maptiler_restriction_ack = _env_bool("MAPTILER_KEY_DOMAIN_RESTRICTED", default=False)
    return {
        "status": "ok",
        "sessions_active": len(sessions),
        "version": "1.0.0",
        "maptiler_key_present": maptiler_key_present,
        "maptiler_domain_restriction_ack": maptiler_restriction_ack,
    }


@app.get("/ready")
async def ready():
    return {"status": "ready"}


# ============================================================================
# MAIN - Run with Uvicorn
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
