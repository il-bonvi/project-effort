# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""Map3D route - 3D map visualization with terrain and elevation"""

import logging
import sys
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path for PEFFORT package imports
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from utils.map3d_generator import generate_3d_map_html

logger = logging.getLogger(__name__)

# This will be set by app.py
_shared_sessions: Dict[str, Any] = {}

router = APIRouter()


def setup_map3d_router(sessions_dict: Dict[str, Any]):
    """Setup the map3d router with shared sessions dictionary"""
    global _shared_sessions
    _shared_sessions = sessions_dict


@router.get("/map3d/{session_id}", response_class=HTMLResponse)
async def map3d_view(session_id: str):
    """
    Generate 3D map visualization with terrain, efforts markers and elevation chart.
    Uses the same MapLibre GL JS implementation as the original PEFFORT desktop app.

    Args:
        session_id: Session identifier from upload

    Returns:
        HTMLResponse with interactive 3D map
    """
    # Check session exists
    if session_id not in _shared_sessions:
        raise HTTPException(status_code=404, detail="Session not found. Please upload a FIT file first.")

    session = _shared_sessions[session_id]

    # Extract session data
    df = session['df']
    efforts = session['efforts']
    sprints = session['sprints']
    cp = session['cp']
    weight = session['weight']

    # Check for GPS data availability
    if 'position_lat' not in df.columns or 'position_long' not in df.columns:
        raise HTTPException(
            status_code=400,
            detail="GPS data not available in this FIT file. 3D map requires GPS coordinates."
        )

    try:
        # Generate 3D map HTML using the same function as desktop app
        html_content = generate_3d_map_html(
            df=df,
            efforts=efforts,
            sprints=sprints,
            cp=cp,
            weight=weight,
            session_id=session_id
        )

        logger.info(f"3D Map visualization generated for session {session_id}")
        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error(f"Error generating 3D map view: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating 3D map: {str(e)}")
