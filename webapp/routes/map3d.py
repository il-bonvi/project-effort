# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""Map3D route - 3D map visualization with terrain and elevation"""

import logging
from typing import Dict, Any, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from dependencies import SessionsDep
from utils.map3d_generator import generate_3d_map_html
from routes.altimetria_d3 import get_chart_data_json

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_map3d_cache_signature(session: Dict[str, Any]) -> Tuple[Any, ...]:
    efforts = tuple((int(s), int(e), round(float(avg), 3)) for s, e, avg in session.get('efforts', []))
    sprints = tuple(
        (
            int(s.get('start', 0)),
            int(s.get('end', 0)),
            round(float(s.get('avg', 0.0)), 3)
        )
        for s in session.get('sprints', [])
    )
    df = session.get('df')
    df_len = int(len(df)) if df is not None else 0
    effort_config = session.get('effort_config')
    sprint_config = session.get('sprint_config')

    return (
        df_len,
        round(float(session.get('cp', session.get('ftp', 250))), 3),
        round(float(session.get('weight', 0)), 3),
        round(float(getattr(effort_config, 'window_seconds', 0)), 3),
        round(float(getattr(effort_config, 'merge_power_diff_percent', 0)), 3),
        round(float(getattr(effort_config, 'min_effort_intensity_cp', 0)), 3),
        round(float(getattr(sprint_config, 'min_power', 0)), 3),
        round(float(getattr(sprint_config, 'window_seconds', 0)), 3),
        round(float(getattr(sprint_config, 'merge_gap_sec', 0)), 3),
        efforts,
        sprints,
    )


def setup_map3d_router(sessions_dict: Dict[str, Any]):
    """Setup the map3d router with shared sessions dictionary"""
    _ = sessions_dict


@router.get("/map3d/{session_id}", response_class=HTMLResponse)
async def map3d_view(session_id: str, sessions: SessionsDep):
    """
    Generate 3D map visualization with terrain, efforts markers and elevation chart.
    Uses the same MapLibre GL JS implementation as the original PEFFORT desktop app.

    Args:
        session_id: Session identifier from upload

    Returns:
        HTMLResponse with interactive 3D map
    """
    # Check session exists
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found. Please upload a FIT file first.")

    session = sessions[session_id]

    # Extract session data
    df = session['df']
    efforts = session['efforts']
    sprints = session['sprints']
    cp = session.get('cp', session.get('ftp', 250))
    weight = session['weight']

    # Check for GPS data availability
    if 'position_lat' not in df.columns or 'position_long' not in df.columns:
        raise HTTPException(
            status_code=400,
            detail="GPS data not available in this FIT file. 3D map requires GPS coordinates."
        )

    try:
        signature = _build_map3d_cache_signature(session)
        cache = session.get('_map3d_html_cache')
        if isinstance(cache, dict) and cache.get('signature') == signature and isinstance(cache.get('html'), str):
            logger.info(f"3D Map visualization cache hit for session {session_id}")
            return HTMLResponse(content=cache['html'])

        try:
            map3d_chart_data_json = get_chart_data_json(session)
        except Exception as chart_err:
            logger.warning(f"Unable to prepare Altimetria chart data for Map3D session {session_id}: {chart_err}")
            map3d_chart_data_json = '{}'

        # Generate 3D map HTML using the same function as desktop app
        html_content = generate_3d_map_html(
            df=df,
            efforts=efforts,
            sprints=sprints,
            cp=cp,
            weight=weight,
            chart_data_json=map3d_chart_data_json,
            session_id=session_id
        )

        session['_map3d_html_cache'] = {
            'signature': signature,
            'html': html_content,
        }

        logger.info(f"3D Map visualization generated for session {session_id}")
        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error(f"Error generating 3D map view: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating 3D map: {str(e)}")
