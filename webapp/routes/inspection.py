# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""
INSPECTION ROUTES - Interactive Effort Editor Interface
Handles the inspection/effort editor view with ECharts visualization
"""

import sys
import json
import logging
import numpy as np
from html import escape
from pathlib import Path
from typing import List, Tuple, Dict, Any

# Add parent directory to path for PEFFORT package imports
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Configure logging
logger = logging.getLogger(__name__)

# Shared sessions dict - set by setup_inspection_router()
_shared_sessions: Dict[str, Dict[str, Any]] = {}

# Jinja2 templates - set by setup_inspection_router()
_templates: Jinja2Templates = None


def setup_inspection_router(sessions_dict: Dict[str, Dict[str, Any]], templates_dir: Path = None) -> APIRouter:
    """
    Set up the inspection router with access to shared sessions.

    Args:
        sessions_dict: Reference to the main sessions dictionary from app.py
        templates_dir: Path to templates directory (default: webapp/templates)

    Returns:
        Configured APIRouter instance
    """
    global _shared_sessions, _templates
    _shared_sessions = sessions_dict
    
    if templates_dir is None:
        templates_dir = Path(__file__).parent.parent / "templates"
    
    _templates = Jinja2Templates(directory=str(templates_dir))
    
    return router


# Create the APIRouter
router = APIRouter(
    prefix="/inspection",
    tags=["inspection"],
    responses={404: {"description": "Not found"}}
)


# =============================================================================
# INSPECTION VIEW - Interactive Effort Editor (ECharts-based HTML)
# =============================================================================

@router.get("/{session_id}", response_class=HTMLResponse)
async def inspection_view(session_id: str, request: Request):
    """
    Display the interactive inspection/effort editor view.
    Uses ECharts-based HTML template with Jinja2 rendering.
    """
    if session_id not in _shared_sessions:
        raise HTTPException(status_code=404, detail="Session not found. Please upload a FIT file.")

    if _templates is None:
        raise HTTPException(status_code=500, detail="Templates not initialized")

    session = _shared_sessions[session_id]
    
    # Generate data for template
    template_data = generate_inspection_data(
        df=session['df'],
        efforts=session['efforts'],
        sprints=session.get('sprints', []),
        cp=session['cp'],
        weight=session['weight'],
        stats=session.get('stats', {}),
        session_id=session_id,
        filename=session['filename']
    )
    
    # Add request for template context
    template_data['request'] = request
    
    return _templates.TemplateResponse("inspection.html", template_data)


# =============================================================================
# DATA GENERATION - Prepare data for inspection template
# =============================================================================

def generate_inspection_data(
    df,
    efforts: List[Tuple[int, int, float]],
    sprints: List[Dict[str, Any]],
    cp: float,
    weight: float,
    stats: Dict[str, Any],
    session_id: str,
    filename: str
) -> dict:
    """
    Generate data for ECharts inspection template.
    
    Args:
        df: Pandas DataFrame with FIT data (time_sec, power columns required)
        efforts: List of effort tuples (start_idx, end_idx, avg_power)
        sprints: List of sprint dictionaries
        cp: Critical Power in watts
        weight: Body weight in kilograms
        stats: Dictionary of ride statistics
        session_id: Session ID for API calls
        filename: Original FIT filename

    Returns:
        Dictionary of template context data
    """
    # Prepare data for ECharts
    time_axis = df['time_sec'].tolist()
    power_data = df['power'].tolist()
    n_samples = len(time_axis)

    # Convert efforts to timeline format
    efforts_data = []
    colors = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#8b5cf6']

    for i, (start_idx, end_idx, avg_w) in enumerate(efforts):
        # Validate indices
        if not (0 <= start_idx < n_samples):
            continue
        if not (0 < end_idx <= n_samples):
            continue
        if end_idx <= start_idx:
            continue

        start_time = time_axis[start_idx]
        last_included_idx = end_idx - 1
        end_time = time_axis[last_included_idx]

        color = colors[i % len(colors)]
        efforts_data.append({
            'id': i,
            'start': start_time,
            'end': end_time,
            'avg_power': avg_w,
            'color': color,
            'label': f"Effort {i+1}"
        })

    # Convert sprints to display format
    sprints_data = []
    sprint_colors = ['#dc2626', '#ea580c', '#f59e0b', '#84cc16', '#10b981', '#06b6d4']

    for i, sprint in enumerate(sprints):
        start_idx = sprint.get('start', 0)
        end_idx = sprint.get('end', start_idx + 1)

        if not (0 <= start_idx < n_samples and 0 < end_idx <= n_samples and end_idx > start_idx):
            continue

        start_time = time_axis[start_idx]
        end_time = time_axis[end_idx - 1]
        
        # Calculate power statistics for this sprint
        sprint_power_data = power_data[start_idx:end_idx]
        max_power = float(np.max(sprint_power_data)) if sprint_power_data else 0.0
        avg_power = float(np.mean(sprint_power_data)) if sprint_power_data else 0.0

        color = sprint_colors[i % len(sprint_colors)]
        sprints_data.append({
            'id': i,
            'start': start_time,
            'end': end_time,
            'max_power': max_power,
            'avg_power': avg_power,
            'duration': end_time - start_time,
            'color': color,
            'label': f"Sprint {i+1}"
        })

    # Format stats for display
    def format_duration(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        if h > 0:
            return f"{h}h {m}m {s}s"
        elif m > 0:
            return f"{m}m {s}s"
        else:
            return f"{s}s"

    stats_html = f"""
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 15px;">
            <div style="background: linear-gradient(135deg, #eff6ff, #dbeafe); padding: 12px; border-radius: 6px; border: 2px solid #93c5fd;">
                <div style="font-size: 11px; color: #1e40af; font-weight: bold; margin-bottom: 4px;">⏱️ DURATION</div>
                <div style="font-size: 18px; font-weight: bold; color: #1e3a8a;">{format_duration(stats.get('duration_sec', 0))}</div>
            </div>
            <div style="background: linear-gradient(135deg, #fef3c7, #fde68a); padding: 12px; border-radius: 6px; border: 2px solid #fbbf24;">
                <div style="font-size: 11px; color: #92400e; font-weight: bold; margin-bottom: 4px;">⚡ AVG POWER</div>
                <div style="font-size: 18px; font-weight: bold; color: #78350f;">{int(stats.get('avg_power', 0))} W</div>
            </div>
            <div style="background: linear-gradient(135deg, #fee2e2, #fecaca); padding: 12px; border-radius: 6px; border: 2px solid #f87171;">
                <div style="font-size: 11px; color: #991b1b; font-weight: bold; margin-bottom: 4px;">🔥 NP</div>
                <div style="font-size: 18px; font-weight: bold; color: #7f1d1d;">{int(stats.get('normalized_power', 0))} W</div>
            </div>
            <div style="background: linear-gradient(135deg, #f3e8ff, #e9d5ff); padding: 12px; border-radius: 6px; border: 2px solid #c084fc;">
                <div style="font-size: 11px; color: #6b21a8; font-weight: bold; margin-bottom: 4px;">📊 IF</div>
                <div style="font-size: 18px; font-weight: bold; color: #581c87;">{stats.get('intensity_factor', 0):.2f}</div>
            </div>
            <div style="background: linear-gradient(135deg, #dcfce7, #bbf7d0); padding: 12px; border-radius: 6px; border: 2px solid #4ade80;">
                <div style="font-size: 11px; color: #166534; font-weight: bold; margin-bottom: 4px;">💪 TSS</div>
                <div style="font-size: 18px; font-weight: bold; color: #14532d;">{int(stats.get('tss', 0))}</div>
            </div>
            <div style="background: linear-gradient(135deg, #e0f2fe, #bae6fd); padding: 12px; border-radius: 6px; border: 2px solid #38bdf8;">
                <div style="font-size: 11px; color: #075985; font-weight: bold; margin-bottom: 4px;">📈 VI</div>
                <div style="font-size: 18px; font-weight: bold; color: #0c4a6e;">{stats.get('variability_index', 1):.2f}</div>
            </div>
            <div style="background: linear-gradient(135deg, #fef2f2, #fee2e2); padding: 12px; border-radius: 6px; border: 2px solid #fca5a5;">
                <div style="font-size: 11px; color: #991b1b; font-weight: bold; margin-bottom: 4px;">💓 AVG HR</div>
                <div style="font-size: 18px; font-weight: bold; color: #7f1d1d;">{int(stats.get('avg_hr', 0))} bpm</div>
            </div>
            <div style="background: linear-gradient(135deg, #fef3c7, #fed7aa); padding: 12px; border-radius: 6px; border: 2px solid #fb923c;">
                <div style="font-size: 11px; color: #9a3412; font-weight: bold; margin-bottom: 4px;">📏 DISTANCE</div>
                <div style="font-size: 18px; font-weight: bold; color: #7c2d12;">{stats.get('total_distance_km', 0):.1f} km</div>
            </div>
            <div style="background: linear-gradient(135deg, #e0e7ff, #c7d2fe); padding: 12px; border-radius: 6px; border: 2px solid #818cf8;">
                <div style="font-size: 11px; color: #3730a3; font-weight: bold; margin-bottom: 4px;">⛰️ ELEVATION</div>
                <div style="font-size: 18px; font-weight: bold; color: #312e81;">{int(stats.get('elevation_gain_m', 0))} m</div>
            </div>
        </div>
    """ if stats else ""

    # Generate JSON for JavaScript
    time_axis_json = json.dumps(time_axis)
    power_data_json = json.dumps(power_data)
    efforts_data_json = json.dumps(efforts_data)
    sprints_data_json = json.dumps(sprints_data)
    cp_json = json.dumps(cp)

    # Escape filename for safe HTML rendering
    safe_filename = escape(filename)

    return {
        'safe_filename': safe_filename,
        'num_efforts': len(efforts_data),
        'num_sprints': len(sprints_data),
        'cp': int(cp),
        'ftp': int(cp),
        'weight': int(weight),
        'session_id': session_id,
        'stats_html': stats_html,
        'time_axis_json': time_axis_json,
        'power_data_json': power_data_json,
        'efforts_data_json': efforts_data_json,
        'sprints_data_json': sprints_data_json,
        'cp_json': cp_json,
        'ftp_json': cp_json,
    }


__all__ = ['router', 'setup_inspection_router', 'generate_inspection_data']
