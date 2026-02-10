# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""Altimetria ECharts route - Elevation profile visualization with ECharts.js"""

import logging
import sys
import json
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path for PEFFORT package imports
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

from fastapi import APIRouter, HTTPException, Request
from starlette.templating import Jinja2Templates
import numpy as np

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
        return {k: convert_to_python_types(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_to_python_types(item) for item in obj]
    return obj


def setup_altimetria_echarts_router(sessions_dict: Dict[str, Any]):
    """Setup the altimetria echarts router with shared sessions dictionary"""
    global _shared_sessions
    _shared_sessions = sessions_dict


def prepare_chart_data(session: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare all data needed for ECharts visualization
    
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
        
        duration = seg_time[-1] - seg_time[0] + 1
        elevation_gain = seg_alt[-1] - seg_alt[0]
        dist_tot = seg_dist[-1] - seg_dist[0]
        avg_speed = dist_tot / (duration / 3600) / 1000 if duration > 0 else 0
        vam = elevation_gain / (duration / 3600) if duration > 0 else 0
        avg_grade = (elevation_gain / dist_tot * 100) if dist_tot > 0 else 0
        
        half = len(seg_power) // 2
        avg_watts_first = seg_power[:half].mean() if half > 0 else 0
        avg_watts_second = seg_power[half:].mean() if len(seg_power) > half else 0
        watts_ratio = avg_watts_first / avg_watts_second if avg_watts_second > 0 else 0
        
        valid_hr = seg_hr[seg_hr > 0]
        avg_hr = valid_hr.mean() if len(valid_hr) > 0 else 0
        max_hr = valid_hr.max() if len(valid_hr) > 0 else 0
        max_grade = seg_grade.max() if len(seg_grade) > 0 else 0
        
        best_5s_watt = 0
        best_5s_watt_kg = 0
        if len(seg_power) >= 5 and weight > 0:
            moving_avgs = [seg_power[i:i+5].mean() for i in range(len(seg_power)-4)]
            best_5s = max(moving_avgs) if moving_avgs else 0
            best_5s_watt = int(best_5s)
            best_5s_watt_kg = best_5s / weight
        
        avg_power_per_kg = avg_power / weight if weight > 0 else 0
        avg_cadence = seg_cadence[seg_cadence > 0].mean() if len(seg_cadence[seg_cadence > 0]) > 0 else 0
        
        hours = time_sec[s] / 3600 if time_sec[s] > 0 else 0
        kj = joules_cumulative[s] / 1000 if s < len(joules_cumulative) else 0
        kj_over_cp = joules_over_cp_cumulative[s] / 1000 if s < len(joules_over_cp_cumulative) else 0
        kj_kg = (kj / weight) if weight > 0 else 0
        kj_kg_over_cp = (kj_over_cp / weight) if weight > 0 else 0
        kj_h_kg = (kj_kg / hours) if hours > 0 else 0
        kj_h_kg_over_cp = (kj_kg_over_cp / hours) if hours > 0 else 0
        
        gradient_factor = 2 + (avg_grade / 10)
        vam_teorico = (avg_power / weight) * (gradient_factor * 100) if weight > 0 else 0
        
        # Line data for this effort
        line_data = []
        for i in range(len(seg_dist_km)):
            line_data.append([round(seg_dist_km[i], 2), round(seg_alt[i], 1)])
        
        effort_info = {
            'id': orig_idx,
            'rank': rank_idx + 1,
            'color': color,
            'line_data': line_data,
            'label_x': round((seg_dist_km[0] + seg_dist_km[-1]) / 2, 2),
            'label_y': round(seg_alt.max(), 1),
            'avg_power': round(avg_power, 0),
            'duration': int(duration),
            'start_time': format_time_hhmmss(seg_time[0]),
            'ftp_pct': round(avg_power/ftp*100, 0),
            'best_5s_watt': best_5s_watt,
            'best_5s_watt_kg': round(best_5s_watt_kg, 2),
            'avg_cadence': round(avg_cadence, 0),
            'avg_power_per_kg': round(avg_power_per_kg, 2),
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
            'vam_teorico': round(vam_teorico, 0),
            'kj': round(kj, 0),
            'kj_over_cp': round(kj_over_cp, 0),
            'kj_kg': round(kj_kg, 1),
            'kj_kg_over_cp': round(kj_kg_over_cp, 1),
            'kj_h_kg': round(kj_h_kg, 1),
            'kj_h_kg_over_cp': round(kj_h_kg_over_cp, 1),
            'gradient_factor': round(gradient_factor, 2)
        }
        
        efforts_data.append(effort_info)
    
    # Process sprints
    sprints_data = []
    sorted_sprints = sorted(enumerate(sprints), key=lambda x: x[1]['avg'], reverse=True)
    
    for rank_idx, (orig_idx, sprint) in enumerate(sorted_sprints):
        start = sprint['start']
        end = sprint['end']
        avg_power = sprint['avg']
        duration = end - start
        
        seg_power = power[start:end]
        seg_alt = alt[start:end]
        seg_dist_km = dist_km[start:end]
        seg_dist = distance[start:end]
        seg_hr = hr[start:end]
        seg_grade = grade[start:end]
        seg_cadence = cadence[start:end]
        
        elevation_gain = seg_alt[-1] - seg_alt[0]
        dist_tot = seg_dist[-1] - seg_dist[0]
        avg_grade = (elevation_gain / dist_tot * 100) if dist_tot > 0 else 0
        
        valid_hr = seg_hr[seg_hr > 0]
        min_hr = valid_hr.min() if len(valid_hr) > 0 else 0
        max_hr = valid_hr.max() if len(valid_hr) > 0 else 0
        min_watt = seg_power.min() if len(seg_power) > 0 else 0
        max_watt = seg_power.max() if len(seg_power) > 0 else 0
        max_grade = seg_grade.max() if len(seg_grade) > 0 else 0
        
        v1 = v2 = 0
        if len(seg_dist_km) >= 2:
            v1 = (seg_dist_km[1] - seg_dist_km[0]) * 3600
            v2 = (seg_dist_km[-1] - seg_dist_km[-2]) * 3600
        
        avg_power_per_kg = avg_power / weight if weight > 0 else 0
        valid_cadence = seg_cadence[seg_cadence > 0]
        avg_cadence = valid_cadence.mean() if len(valid_cadence) > 0 else 0
        min_cadence = valid_cadence.min() if len(valid_cadence) > 0 else 0
        max_cadence = valid_cadence.max() if len(valid_cadence) > 0 else 0
        
        # Line data for this sprint
        line_data = []
        for i in range(len(seg_dist_km)):
            line_data.append([round(seg_dist_km[i], 2), round(seg_alt[i], 1)])
        
        sprint_info = {
            'id': orig_idx,
            'rank': rank_idx + 1,
            'line_data': line_data,
            'label_x': round((seg_dist_km[0] + seg_dist_km[-1]) / 2, 2),
            'label_y': round(seg_alt.max(), 1),
            'avg_power': round(avg_power, 0),
            'duration': int(duration),
            'avg_power_per_kg': round(avg_power_per_kg, 2),
            'min_watt': round(min_watt, 0),
            'max_watt': round(max_watt, 0),
            'min_hr': round(min_hr, 0) if min_hr > 0 else 0,
            'max_hr': round(max_hr, 0) if max_hr > 0 else 0,
            'avg_cadence': round(avg_cadence, 0) if avg_cadence > 0 else 0,
            'min_cadence': round(min_cadence, 0) if min_cadence > 0 else 0,
            'max_cadence': round(max_cadence, 0) if max_cadence > 0 else 0,
            'v1': round(v1, 1),
            'v2': round(v2, 1),
            'avg_grade': round(avg_grade, 1),
            'max_grade': round(max_grade, 1),
            'elevation_gain': round(elevation_gain, 1),
            'distance_tot': round(dist_tot / 1000, 2)
        }
        
        sprints_data.append(sprint_info)
    
    # Get config params
    effort_config = session['effort_config']
    sprint_config = session['sprint_config']
    
    return {
        'elevation_data': elevation_data,
        'efforts': efforts_data,
        'sprints': sprints_data,
        'ftp': ftp,
        'weight': weight,
        'config': {
            'window_sec': effort_config.window_seconds,
            'merge_pct': effort_config.merge_power_diff_percent,
            'min_ftp_pct': effort_config.min_effort_intensity_ftp,
            'trim_win': effort_config.trim_window_seconds,
            'trim_low': effort_config.trim_low_percent,
            'extend_win': effort_config.extend_window_seconds,
            'extend_low': effort_config.extend_low_percent,
            'sprint_window_sec': sprint_config.window_seconds,
            'min_sprint_power': sprint_config.min_power
        }
    }


@router.get("/altimetria-echarts/{session_id}")
async def altimetria_echarts_view(request: Request, session_id: str):
    """
    Generate elevation profile visualization with ECharts.js
    
    Args:
        request: FastAPI Request object
        session_id: Session identifier from upload
        
    Returns:
        TemplateResponse with interactive ECharts elevation profile
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
        
        # Render template with data
        logger.info(f"Altimetria ECharts visualization generated for session {session_id}")
        return templates.TemplateResponse("altimetria_echarts.html", {
            "request": request,
            "filename": session['filename'],
            "chart_data_json": chart_data_json
        })
        
    except Exception as e:
        logger.error(f"Error generating altimetria echarts view: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating elevation profile: {str(e)}")



