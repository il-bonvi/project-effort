# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""Altimetria route - Elevation profile visualization with Plotly"""

import logging
import sys
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path for PEFFORT package imports
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from PEFFORT.peffort_exporter import plot_unified_html  # type: ignore

logger = logging.getLogger(__name__)

# This will be set by app.py
_shared_sessions: Dict[str, Any] = {}

router = APIRouter()


def setup_altimetria_router(sessions_dict: Dict[str, Any]):
    """Setup the altimetria router with shared sessions dictionary"""
    global _shared_sessions
    _shared_sessions = sessions_dict


@router.get("/altimetria/{session_id}", response_class=HTMLResponse)
async def altimetria_view(session_id: str):
    """
    Generate elevation profile visualization with efforts and sprints.
    Uses the same Plotly implementation as the original PEFFORT desktop app.

    Args:
        session_id: Session identifier from upload

    Returns:
        HTMLResponse with interactive Plotly elevation profile
    """
    # Check session exists
    if session_id not in _shared_sessions:
        raise HTTPException(status_code=404, detail="Session not found. Please upload a FIT file first.")

    session = _shared_sessions[session_id]

    # Extract session data
    df = session['df']
    efforts = session['efforts']
    sprints = session['sprints']
    ftp = session['ftp']
    weight = session['weight']

    # Get configuration parameters from session
    effort_config = session['effort_config']
    sprint_config = session['sprint_config']

    window_sec = effort_config.window_seconds
    merge_pct = effort_config.merge_power_diff_percent
    min_ftp_pct = effort_config.min_effort_intensity_ftp
    trim_win = effort_config.trim_window_seconds
    trim_low = effort_config.trim_low_percent
    extend_win = effort_config.extend_window_seconds
    extend_low = effort_config.extend_low_percent

    sprint_window_sec = sprint_config.window_seconds
    min_sprint_power = sprint_config.min_power

    try:
        # Generate Plotly HTML using the same function as desktop app
        html_content = plot_unified_html(
            df=df,
            efforts=efforts,
            sprints=sprints,
            ftp=ftp,
            weight=weight,
            window_sec=window_sec,
            merge_pct=merge_pct,
            min_ftp_pct=min_ftp_pct,
            trim_win=trim_win,
            trim_low=trim_low,
            extend_win=extend_win,
            extend_low=extend_low,
            sprint_window_sec=sprint_window_sec,
            min_sprint_power=min_sprint_power
        )

        logger.info(f"Altimetria visualization generated for session {session_id}")
        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error(f"Error generating altimetria view: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating elevation profile: {str(e)}")
