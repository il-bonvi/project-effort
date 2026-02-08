# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""Dashboard route - Main data overview and settings interface"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

logger = logging.getLogger(__name__)

# Setup Jinja2 templates
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# This will be set by app.py
_shared_sessions: Dict[str, Any] = {}

router = APIRouter()


def setup_dashboard_router(sessions_dict: Dict[str, Any]):
    """Setup the dashboard router with shared sessions dictionary"""
    global _shared_sessions
    _shared_sessions = sessions_dict


def format_duration(sec: int) -> str:
    """Convert seconds to human-readable duration string (h/m/s)"""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"


@router.get("/dashboard/{session_id}")
async def dashboard_view(request: Request, session_id: str):
    """
    Main dashboard with tab system: Overview, Inspection, Settings, Export.
    Displays comprehensive ride statistics, effort/sprint detection settings,
    and export options.
    """
    if session_id not in _shared_sessions:
        raise HTTPException(status_code=404, detail="Session not found. Please upload a FIT file.")
    
    session = _shared_sessions[session_id]
    stats = session.get('stats', {})
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "session_id": session_id,
            "session": session,
            "stats": stats,
            "format_duration": format_duration
        }
    )
