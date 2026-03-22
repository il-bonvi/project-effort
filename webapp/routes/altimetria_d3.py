# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""Altimetria D3.js route - Elevation profile visualization with D3.js"""

import logging
import sys
import json
from pathlib import Path
from typing import Dict, Any

import numpy as np

# Add parent directory to path for PEFFORT package imports
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from utils.effort_analyzer import (
    format_time_hhmmss, format_time_mmss, get_zone_color
)

logger = logging.getLogger(__name__)

# Setup Jinja2 templates using an absolute path based on this file's location
_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

# This will be set by app.py
_shared_sessions: Dict[str, Any] = {}

router = APIRouter()


def convert_to_python_types(obj: Any) -> Any:
    """
    Recursively convert numpy types to Python native types for JSON serialization
    """
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_to_python_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_python_types(item) for item in obj]
    return obj


def prepare_chart_data(session: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare all data needed for D3 visualization (same as ECharts version)
    
    Returns:
        Dictionary with all chart data and configurations
    """
    df = session['df']
    efforts = session['efforts']
    sprints = session['sprints']
    ftp = session['ftp']
    weight = session['weight']
    
    power = df["power"].values
    time_sec = df["time_sec"].values
    dist_km = df["distance_km"].values
    distance = df["distance"].values
    alt = df["altitude"].values
    hr = df["heartrate"].values
    grade = df["grade"].values
    cadence = df["cadence"].values
    
    # Sample data for performance (max 1000 points for base elevation)
    step = max(1, len(dist_km) // 1000)
    
    # Base elevation data
    elevation_data = []
    for i in range(0, len(dist_km), step):
        t = time_sec[i]
        if t >= 3600:
            time_str = format_time_hhmmss(t)
        else:
            time_str = format_time_mmss(t)
        elevation_data.append({
            'dist': round(dist_km[i], 2),
            'alt': round(alt[i], 1),
            'time': time_str
        })
    
    # Calculate cumulative joules
    joules_cumulative = np.zeros(len(power))
    joules_over_cp_cumulative = np.zeros(len(power))
    for i in range(1, len(power)):
        dt = time_sec[i] - time_sec[i-1]
        if dt > 0 and dt < 30:
            joules_cumulative[i] = joules_cumulative[i-1] + power[i] * dt
            if power[i] >= ftp:
                joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1] + power[i] * dt
            else:
                joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1]
        else:
            joules_cumulative[i] = joules_cumulative[i-1]
            joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1]
    
    # Process efforts
    efforts_data = []
    efforts_with_idx = [(i, eff) for i, eff in enumerate(efforts)]
    sorted_efforts = sorted(efforts_with_idx, key=lambda x: x[1][2], reverse=True)
    
    for rank_idx, (orig_idx, (s, e, avg)) in enumerate(sorted_efforts):
        seg_power = power[s:e]
        seg_alt = alt[s:e]
        seg_dist_km = dist_km[s:e]
        seg_dist = distance[s:e]
        seg_time = time_sec[s:e]
        seg_hr = hr[s:e]
        seg_grade = grade[s:e]
        seg_cadence = cadence[s:e]
        
        avg_power = avg
        color = get_zone_color(avg_power, ftp)
        
        duration = float(seg_time[-1] - seg_time[0] + 1)
        elevation_gain = float(seg_alt[-1] - seg_alt[0])
        dist_tot = float(seg_dist[-1] - seg_dist[0])
        avg_speed = float(dist_tot / (duration / 3600) / 1000) if duration > 0 else 0.0
        vam = float(elevation_gain / (duration / 3600)) if duration > 0 else 0.0
        avg_grade = float((elevation_gain / dist_tot * 100) if dist_tot > 0 else 0)
        
        half = len(seg_power) // 2
        avg_watts_first = float(seg_power[:half].mean()) if half > 0 else 0.0
        avg_watts_second = float(seg_power[half:].mean()) if len(seg_power) > half else 0.0
        watts_ratio = float(avg_watts_first / avg_watts_second) if avg_watts_second > 0 else 0.0
        
        valid_hr = seg_hr[seg_hr > 0]
        avg_hr = float(valid_hr.mean()) if len(valid_hr) > 0 else 0.0
        max_hr = float(valid_hr.max()) if len(valid_hr) > 0 else 0.0
        max_grade = float(seg_grade.max()) if len(seg_grade) > 0 else 0.0
        
        best_5s_watt = 0
        best_5s_watt_kg = 0
        if len(seg_power) >= 5 and weight > 0:
            moving_avgs = [seg_power[i:i+5].mean() for i in range(len(seg_power)-4)]
            best_5s = max(moving_avgs) if moving_avgs else 0
            best_5s_watt = int(best_5s)
            best_5s_watt_kg = best_5s / weight
        
        avg_power_per_kg = float(avg_power / weight) if weight > 0 else 0.0
        valid_cadence = seg_cadence[seg_cadence > 0]
        avg_cadence = float(valid_cadence.mean()) if len(valid_cadence) > 0 else 0.0
        
        hours = float(time_sec[s] / 3600) if time_sec[s] > 0 else 0.0
        kj = float(joules_cumulative[s] / 1000) if s < len(joules_cumulative) else 0.0
        kj_over_cp = float(joules_over_cp_cumulative[s] / 1000) if s < len(joules_over_cp_cumulative) else 0.0
        kj_kg = float((kj / weight) if weight > 0 else 0)
        kj_kg_over_cp = float((kj_over_cp / weight) if weight > 0 else 0)
        kj_h_kg = float((kj_kg / hours) if hours > 0 else 0)
        kj_h_kg_over_cp = float((kj_kg_over_cp / hours) if hours > 0 else 0)
        
        gradient_factor = 2 + (avg_grade / 10)
        vam_teorico = (avg_power / weight) * (gradient_factor * 100) if weight > 0 else 0
        
        # Line data for this effort
        line_data = []
        for i in range(len(seg_dist_km)):
            line_data.append([round(seg_dist_km[i], 2), round(seg_alt[i], 1)])
        
        effort_info = {
            'id': orig_idx,
            'rank': rank_idx + 1,
            'line_data': line_data,
            'label_x': round((seg_dist_km[0] + seg_dist_km[-1]) / 2, 2),
            'label_y': round(seg_alt.max(), 1),
            'color': color,
            'avg_power': round(avg_power, 0),
            'duration': int(duration),
            'start_time': format_time_hhmmss(time_sec[s]) if s < len(time_sec) else '',
            'ftp_pct': round((avg_power / ftp * 100), 0),
            'avg_power_per_kg': round(avg_power_per_kg, 2),
            'best_5s_watt': best_5s_watt,
            'best_5s_watt_kg': round(best_5s_watt_kg, 2),
            'avg_cadence': round(avg_cadence, 0) if avg_cadence > 0 else 0,
            'avg_watts_first': round(avg_watts_first, 0),
            'avg_watts_second': round(avg_watts_second, 0),
            'watts_ratio': round(watts_ratio, 2),
            'avg_hr': round(avg_hr, 0) if avg_hr > 0 else 0,
            'max_hr': round(max_hr, 0) if max_hr > 0 else 0,
            'avg_speed': round(avg_speed, 1),
            'avg_grade': round(avg_grade, 1),
            'max_grade': round(max_grade, 1),
            'elevation_gain': round(elevation_gain, 1),
            'distance_tot': round(dist_tot / 1000, 2),
            'vam': round(vam, 0),
            'vam_arrow': '⬆️' if vam_teorico - vam > 0 else ('⬇️' if vam_teorico - vam < 0 else ''),
            'diff_vam': round(abs(vam_teorico - vam), 0) if avg_grade >= 4.5 else 0,
            'vam_teorico': round(vam_teorico, 0),
            'wkg_teoric': round((vam / (gradient_factor * 100) if gradient_factor > 0 else 0), 2),
            'diff_wkg': round(abs(avg_power_per_kg - (vam / (gradient_factor * 100) if gradient_factor > 0 else 0)), 2),
            'perc_err': round(((avg_power_per_kg - (vam / (gradient_factor * 100) if gradient_factor > 0 else 0)) / avg_power_per_kg * 100) if avg_power_per_kg != 0 else 0, 1) if avg_grade >= 4.5 else 0,
            'kj': round(kj, 0),
            'kj_over_cp': round(kj_over_cp, 0),
            'kj_kg': round(kj_kg, 1),
            'kj_kg_over_cp': round(kj_kg_over_cp, 1),
            'kj_h_kg': round(kj_h_kg, 1),
            'kj_h_kg_over_cp': round(kj_h_kg_over_cp, 1)
        }
        
        efforts_data.append(effort_info)
    
    # Process sprints (simplified)
    sprints_data = []
    for rank_idx, sprint in enumerate(sprints):
        start = sprint['start']
        end = sprint['end']
        avg_power = sprint['avg']
        
        seg_power = power[start:end]
        seg_alt = alt[start:end]
        seg_dist_km = dist_km[start:end]
        
        duration = int(end - start)
        elevation_gain = float(seg_alt[-1] - seg_alt[0]) if len(seg_alt) > 0 else 0
        dist_tot = float(seg_dist_km[-1] - seg_dist_km[0]) if len(seg_dist_km) > 0 else 0
        avg_grade = float((elevation_gain / dist_tot * 100) if dist_tot > 0 else 0)
        
        # Line data for this sprint
        line_data = []
        for i in range(len(seg_dist_km)):
            line_data.append([round(seg_dist_km[i], 2), round(seg_alt[i], 1)])
        
        sprint_info = {
            'id': rank_idx,
            'rank': rank_idx + 1,
            'line_data': line_data,
            'label_x': round((seg_dist_km[0] + seg_dist_km[-1]) / 2, 2) if len(seg_dist_km) > 0 else 0,
            'label_y': round(seg_alt.max(), 1) if len(seg_alt) > 0 else 0,
            'avg_power': round(avg_power, 0),
            'duration': duration,
            'start_time': format_time_hhmmss(time_sec[start]) if start < len(time_sec) else '',
            'avg_grade': round(avg_grade, 1),
            'distance_tot': round(dist_tot / 1000, 2),
            'max_watt': round(seg_power.max(), 0) if len(seg_power) > 0 else 0,
            'min_watt': round(seg_power.min(), 0) if len(seg_power) > 0 else 0
        }
        
        sprints_data.append(sprint_info)
    
    # Get config params
    effort_config = session['effort_config']
    sprint_config = session['sprint_config']
    
    return {
        'elevation_data': elevation_data,
        'efforts': efforts_data,
        'sprints': sprints_data,
        'ftp': float(ftp),
        'weight': float(weight),
        'config': {
            'window_sec': float(effort_config.window_seconds),
            'merge_pct': float(effort_config.merge_power_diff_percent),
            'min_ftp_pct': float(effort_config.min_effort_intensity_ftp),
            'sprint_window_sec': float(sprint_config.window_seconds),
            'min_sprint_power': float(sprint_config.min_power)
        }
    }


def setup_altimetria_d3_router(sessions_dict: Dict[str, Any]):
    """Setup the altimetria D3 router with shared sessions dictionary"""
    global _shared_sessions
    _shared_sessions = sessions_dict


@router.get("/altimetria-d3/{session_id}")
async def altimetria_d3_view(request: Request, session_id: str):
    """
    Generate elevation profile visualization with D3.js

    Args:
        session_id: Session identifier from upload

    Returns:
        HTMLResponse with D3.js elevation profile
    """
    # Check session exists
    if session_id not in _shared_sessions:
        raise HTTPException(status_code=404, detail="Session not found. Please upload a FIT file first.")

    session = _shared_sessions[session_id]

    try:
        # Prepare all chart data
        chart_data = prepare_chart_data(session)
        
        # Convert numpy types to Python native types for JSON serialization
        chart_data = convert_to_python_types(chart_data)
        
        # Convert to JSON for embedding in HTML
        chart_data_json = json.dumps(chart_data)
        
        # Return the D3 template
        logger.info(f"Altimetria D3 visualization generated for session {session_id}")
        return templates.TemplateResponse(
            "altimetria_d3.html",
            {
                "request": request,
                "filename": session.get('filename', 'Unknown'),
                "chart_data_json": chart_data_json,
                "session_id": session_id
            }
        )

    except Exception as e:
        logger.error(f"Error generating D3 altimetria for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating visualization: {str(e)}")
