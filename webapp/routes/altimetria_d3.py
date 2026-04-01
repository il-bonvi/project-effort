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
from fastapi.templating import Jinja2Templates

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
    Prepare all data needed for D3 visualization
    
    Returns:
        Dictionary with all chart data and configurations
    """
    df = session['df']
    efforts = session['efforts']
    sprints = session['sprints']
    cp = session.get('cp', session.get('ftp', 250))
    weight = session['weight']
    
    power = df["power"].values
    time_sec = df["time_sec"].values
    dist_km = df["distance_km"].values
    distance = df["distance"].values
    alt = df["altitude"].values
    hr = df["heartrate"].values
    grade = df["grade"].values
    cadence = df["cadence"].values
    
    # Base elevation data
    elevation_data = []
    for i in range(len(dist_km)):
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
            if power[i] >= cp:
                joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1] + power[i] * dt
            else:
                joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1]
        else:
            joules_cumulative[i] = joules_cumulative[i-1]
            joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1]
    
    # Initialize torque and cadence settings (used for both efforts and sprints)
    cadence_min_rpm = 20
    torque_available = 'torque' in df.columns
    
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
        color = get_zone_color(avg_power, cp)
        
        duration = float(seg_time[-1] - seg_time[0] + 1)
        
        # Extended stream data for moving averages (includes buffer before/after effort)
        # This allows 30s/60s moving averages to have proper context at effort boundaries
        buffer_seconds = 120  # Look 120s before and after effort
        s_ext = s
        e_ext = e
        # Find extended indices by time distance
        while s_ext > 0 and (time_sec[s] - time_sec[s_ext - 1]) < buffer_seconds:
            s_ext -= 1
        while e_ext < len(time_sec) and (time_sec[e_ext] - time_sec[e - 1]) < buffer_seconds:
            e_ext += 1
        
        seg_power_ext = power[s_ext:e_ext]
        seg_time_ext = time_sec[s_ext:e_ext]
        seg_hr_ext = hr[s_ext:e_ext]
        seg_cadence_ext = cadence[s_ext:e_ext]
        if torque_available:
            seg_torque_ext = df["torque"].values[s_ext:e_ext]
        else:
            seg_torque_ext = np.zeros_like(seg_power_ext)
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
        
        # Stream data for zoom modal (power, HR, W/kg time series) — using EXTENDED data
        # Normalize: t=0 is the effort start (buffer has negative times)
        effort_t0 = time_sec[s]
        time_stream = [round(float(t - effort_t0), 2) for t in seg_time_ext]
        power_stream = [float(p) for p in seg_power_ext]
        hr_stream = [float(h) if h > 0 else None for h in seg_hr_ext]
        wkg_stream = [float(p / weight) if weight > 0 else 0 for p in seg_power_ext]
        
        # Cadence and torque streams (for consistency with sprints)
        cadence_min_rpm = 20
        seg_cadence_ext_clean = np.where(seg_cadence_ext >= cadence_min_rpm, seg_cadence_ext, 0)
        cadence_stream = [float(c) if c >= cadence_min_rpm else None for c in seg_cadence_ext]
        
        # Torque stream (extended)
        valid_torque_idx = (seg_cadence_ext_clean > 0) & (seg_power_ext > 0)
        seg_torque_ext[valid_torque_idx] = (seg_power_ext[valid_torque_idx] * 60) / (2 * np.pi * seg_cadence_ext_clean[valid_torque_idx])
        torque_stream = [float(t) if t > 0 else None for t in seg_torque_ext]
        
        # Speed stream (km/h) - calculated from distance changes using FULL DATA
        dist_km_ext = dist_km[s_ext:e_ext]
        raw_speed = [0.0]  # First value is 0
        for i in range(1, len(dist_km_ext)):
            dt = seg_time_ext[i] - seg_time_ext[i-1]
            if dt > 0:
                dist_diff_km = dist_km_ext[i] - dist_km_ext[i-1]
                speed_kmh = (dist_diff_km / (dt / 3600))  # km/h
                raw_speed.append(float(max(0, speed_kmh)))
            else:
                raw_speed.append(0.0)
        
        # Apply 3-point moving average to smooth out noise
        win = min(3, len(raw_speed))
        speed_stream = []
        for i in range(len(raw_speed)):
            start = max(0, i - win // 2)
            end = min(len(raw_speed), i + win // 2 + 1)
            speed_stream.append(float(np.mean(raw_speed[start:end])))
        
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
            'cp_pct': round((avg_power / cp * 100), 0),
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
            'perc_err': round((((vam / (gradient_factor * 100) if gradient_factor > 0 else 0) - avg_power_per_kg) / avg_power_per_kg * 100) if avg_power_per_kg != 0 else 0, 1) if avg_grade >= 4.5 else 0,
            'kj': round(kj, 0),
            'kj_over_cp': round(kj_over_cp, 0),
            'kj_kg': round(kj_kg, 1),
            'kj_kg_over_cp': round(kj_kg_over_cp, 1),
            'kj_h_kg': round(kj_h_kg, 1),
            'kj_h_kg_over_cp': round(kj_h_kg_over_cp, 1),
            # Stream data for zoom modal (extended with 120s buffer before/after)
            'time_stream': time_stream,
            'power_stream': power_stream,
            'hr_stream': hr_stream,
            'wkg_stream': wkg_stream,
            'cadence_stream': cadence_stream,
            'torque_stream': torque_stream,
            'speed_stream': speed_stream,
            # Track effort position: ACTUAL times relative to buffer start (not indices)
            'stream_effort_start': 0.0,  # Effort always starts at t=0
            'stream_effort_end':   float(time_sec[e - 1] - effort_t0 + 1),
            'stream_effort_duration': int(duration)  # Actual effort duration (not including buffer)
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
        seg_time = time_sec[start:end]
        seg_hr = hr[start:end]
        seg_grade = grade[start:end]
        seg_cadence_raw = cadence[start:end]
        seg_cadence = np.where(seg_cadence_raw >= cadence_min_rpm, seg_cadence_raw, 0)
        
        # Handle torque
        if torque_available:
            seg_torque = df["torque"].values[start:end]
        else:
            seg_torque = np.zeros_like(seg_power)
            valid_torque_idx = (seg_cadence > 0) & (seg_power > 0)
            seg_torque[valid_torque_idx] = (seg_power[valid_torque_idx] * 60) / (2 * np.pi * seg_cadence[valid_torque_idx])
        
        # Extended stream data for moving averages (includes buffer before/after sprint)
        buffer_seconds = 120  # Look 120s before and after sprint
        s_ext = start
        e_ext = end
        # Find extended indices by time distance
        while s_ext > 0 and (time_sec[start] - time_sec[s_ext - 1]) < buffer_seconds:
            s_ext -= 1
        while e_ext < len(time_sec) and (time_sec[e_ext] - time_sec[end - 1]) < buffer_seconds:
            e_ext += 1
        
        seg_power_ext = power[s_ext:e_ext]
        seg_time_ext = time_sec[s_ext:e_ext]
        seg_hr_ext = hr[s_ext:e_ext]
        seg_cadence_ext = cadence[s_ext:e_ext]
        if torque_available:
            seg_torque_ext = df["torque"].values[s_ext:e_ext]
        else:
            seg_torque_ext = np.zeros_like(seg_power_ext)
            seg_torque[valid_torque_idx] = (seg_power[valid_torque_idx] * 60) / (2 * np.pi * seg_cadence[valid_torque_idx])
        
        elevation_gain = float(seg_alt[-1] - seg_alt[0]) if len(seg_alt) > 1 else 0.0
        dist_tot = float(seg_dist[-1] - seg_dist[0]) if len(seg_dist) > 1 else 0.0
        avg_grade = float((elevation_gain / dist_tot * 100) if dist_tot > 0 else 0)
        
        valid_hr = seg_hr[seg_hr > 0]
        min_hr = float(valid_hr.min()) if len(valid_hr) > 0 else 0.0
        max_hr = float(valid_hr.max()) if len(valid_hr) > 0 else 0.0
        min_watt = float(seg_power.min()) if len(seg_power) > 0 else 0.0
        max_watt = float(seg_power.max()) if len(seg_power) > 0 else 0.0
        max_grade = float(seg_grade.max()) if len(seg_grade) > 0 else 0.0
        
        # Torque metrics
        valid_torque = seg_torque[seg_torque > 0]
        avg_torque = float(valid_torque.mean()) if len(valid_torque) > 0 else 0.0
        min_torque = float(valid_torque.min()) if len(valid_torque) > 0 else 0.0
        max_torque = float(valid_torque.max()) if len(valid_torque) > 0 else 0.0
        
        # Speed start/end (km/h) based on real delta-time, robust to non-1s sampling
        v1 = v2 = 0.0
        if len(seg_dist_km) >= 2 and len(seg_time) >= 2:
            edge_window_s = 3.0
            inst_speeds = []
            for i in range(1, len(seg_dist_km)):
                dt = float(seg_time[i] - seg_time[i - 1])
                if dt <= 0:
                    continue
                dkm = float(seg_dist_km[i] - seg_dist_km[i - 1])
                # Ignore backwards/noise spikes from GPS drift in edge speed estimate
                if dkm < 0:
                    continue
                speed_kmh = dkm / (dt / 3600.0)
                if 0 <= speed_kmh <= 130:
                    inst_speeds.append((i, speed_kmh))

            if inst_speeds:
                start_candidates = [s for i, s in inst_speeds if (seg_time[i] - seg_time[0]) <= edge_window_s]
                end_candidates = [s for i, s in inst_speeds if (seg_time[-1] - seg_time[i]) <= edge_window_s]

                if not start_candidates:
                    start_candidates = [s for _, s in inst_speeds[:3]]
                if not end_candidates:
                    end_candidates = [s for _, s in inst_speeds[-3:]]

                v1 = float(np.mean(start_candidates)) if start_candidates else 0.0
                v2 = float(np.mean(end_candidates)) if end_candidates else 0.0
        
        avg_power_per_kg = float(avg_power / weight) if weight > 0 else 0.0
        valid_cadence = seg_cadence[seg_cadence > 0]
        avg_cadence = float(valid_cadence.mean()) if len(valid_cadence) > 0 else 0.0
        min_cadence = float(valid_cadence.min()) if len(valid_cadence) > 0 else 0.0
        max_cadence = float(valid_cadence.max()) if len(valid_cadence) > 0 else 0.0
        
        # Find indices for max/min power
        max_power_idx = np.argmax(seg_power) if len(seg_power) > 0 else -1
        min_power_idx = np.argmin(seg_power) if len(seg_power) > 0 else -1
        
        rpm_at_max = float(round(seg_cadence[max_power_idx])) if max_power_idx >= 0 and seg_cadence[max_power_idx] > 0 else 0.0
        torque_at_max = float(round(seg_torque[max_power_idx])) if max_power_idx >= 0 and seg_torque[max_power_idx] > 0 else 0.0
        rpm_at_min = float(round(seg_cadence[min_power_idx])) if min_power_idx >= 0 and seg_cadence[min_power_idx] > 0 else 0.0
        torque_at_min = float(round(seg_torque[min_power_idx])) if min_power_idx >= 0 and seg_torque[min_power_idx] > 0 else 0.0
        
        # kJ calculations (use joules_cumulative[start], not end!)
        start_time_sec = time_sec[start] if start < len(time_sec) else 0
        hours = start_time_sec / 3600 if start_time_sec > 0 else 0
        kj = joules_cumulative[start] / 1000 if start < len(joules_cumulative) else 0
        kj_over_cp = joules_over_cp_cumulative[start] / 1000 if start < len(joules_over_cp_cumulative) else 0
        kj_kg = (kj / weight) if weight > 0 else 0
        kj_kg_over_cp = (kj_over_cp / weight) if weight > 0 else 0
        kj_h_kg = (kj_kg / hours) if hours > 0 else 0
        kj_h_kg_over_cp = (kj_kg_over_cp / hours) if hours > 0 else 0
        
        # Line data
        line_data = []
        for i in range(len(seg_dist_km)):
            line_data.append([round(seg_dist_km[i], 2), round(seg_alt[i], 1)])
        
        # Stream data for zoom modal (power, HR, W/kg time series) — using EXTENDED data
        # Normalize: t=0 is the effort start (buffer has negative times)
        effort_t0 = time_sec[start]
        time_stream = [round(float(t - effort_t0), 2) for t in seg_time_ext]
        stream_effort_start = 0.0
        stream_effort_end   = float(time_sec[end - 1] - effort_t0)
        power_stream = [float(p) for p in seg_power_ext]
        hr_stream = [float(h) if h > 0 else None for h in seg_hr_ext]
        wkg_stream = [float(p / weight) if weight > 0 else 0 for p in seg_power_ext]
        
        # Cadence and torque streams (extended)
        seg_cadence_ext_clean = np.where(seg_cadence_ext >= cadence_min_rpm, seg_cadence_ext, 0)
        cadence_stream = [float(c) if c >= cadence_min_rpm else None for c in seg_cadence_ext]
        
        # Torque stream (extended)
        valid_torque_idx = (seg_cadence_ext_clean > 0) & (seg_power_ext > 0)
        seg_torque_ext[valid_torque_idx] = (seg_power_ext[valid_torque_idx] * 60) / (2 * np.pi * seg_cadence_ext_clean[valid_torque_idx])
        torque_stream = [float(t) if t > 0 else None for t in seg_torque_ext]
        
        # Speed stream (km/h) - calculated from distance changes using FULL DATA
        dist_km_ext = dist_km[s_ext:e_ext]
        raw_speed = [0.0]  # First value is 0
        for i in range(1, len(dist_km_ext)):
            dt = seg_time_ext[i] - seg_time_ext[i-1]
            if dt > 0:
                dist_diff_km = dist_km_ext[i] - dist_km_ext[i-1]
                speed_kmh = (dist_diff_km / (dt / 3600))  # km/h
                raw_speed.append(float(max(0, speed_kmh)))
            else:
                raw_speed.append(0.0)
        
        # Apply 3-point moving average to smooth out noise
        win = min(3, len(raw_speed))
        speed_stream = []
        for i in range(len(raw_speed)):
            start_idx = max(0, i - win // 2)
            end_idx = min(len(raw_speed), i + win // 2 + 1)
            speed_stream.append(float(np.mean(raw_speed[start_idx:end_idx])))
        
        sprint_info = {
            'id': orig_idx,
            'rank': rank_idx + 1,
            'line_data': line_data,
            'label_x': round((seg_dist_km[0] + seg_dist_km[-1]) / 2, 2),
            'label_y': round(seg_alt.max(), 1),
            'avg_power': round(avg_power, 0),
            'duration': int(duration),
            'start_time': format_time_hhmmss(time_sec[start]) if start < len(time_sec) else '',
            'avg_power_per_kg': round(avg_power_per_kg, 2),
            'min_watt': round(min_watt, 0),
            'max_watt': round(max_watt, 0),
            'min_hr': round(min_hr, 0) if min_hr > 0 else 0,
            'max_hr': round(max_hr, 0) if max_hr > 0 else 0,
            'avg_cadence': round(avg_cadence, 0) if avg_cadence > 0 else 0,
            'min_cadence': round(min_cadence, 0) if min_cadence > 0 else 0,
            'max_cadence': round(max_cadence, 0) if max_cadence > 0 else 0,
            'avg_torque': round(avg_torque, 0) if avg_torque > 0 else 0,
            'min_torque': round(min_torque, 0) if min_torque > 0 else 0,
            'max_torque': round(max_torque, 0) if max_torque > 0 else 0,
            'rpm_at_max': rpm_at_max,
            'torque_at_max': torque_at_max,
            'rpm_at_min': rpm_at_min,
            'torque_at_min': torque_at_min,
            'v1': round(v1, 1),
            'v2': round(v2, 1),
            'avg_grade': round(avg_grade, 1),
            'max_grade': round(max_grade, 1),
            'elevation_gain': round(elevation_gain, 1),
            'distance_tot': round(dist_tot / 1000, 2),
            'kj': round(kj, 0),
            'kj_over_cp': round(kj_over_cp, 0),
            'kj_kg': round(kj_kg, 1),
            'kj_kg_over_cp': round(kj_kg_over_cp, 1),
            'kj_h_kg': round(kj_h_kg, 1),
            'kj_h_kg_over_cp': round(kj_h_kg_over_cp, 1),
            # Stream data for zoom modal (extended with 120s buffer before/after)
            'time_stream': time_stream,
            'stream_effort_start': stream_effort_start,
            'stream_effort_end':   stream_effort_end,
            'power_stream': power_stream,
            'hr_stream': hr_stream,
            'wkg_stream': wkg_stream,
            'cadence_stream': cadence_stream,
            'torque_stream': torque_stream,
            'speed_stream': speed_stream,
            # Track sprint position: ACTUAL times relative to buffer start (not indices)
            'stream_effort_start': 0.0,
            'stream_effort_end':   float(time_sec[end - 1] - time_sec[start]),
            'stream_effort_duration': int(duration)     # Actual sprint duration (not including buffer)
        }
        sprints_data.append(sprint_info)
    
    # Get config params
    effort_config = session['effort_config']
    sprint_config = session['sprint_config']
    
    # Standard intensity zones (% of CP)
    # Intensity zones are defined and stored exclusively in the Inspection tab (localStorage).
    # The browser sends them at export time. We ship an empty list here as a safe placeholder —
    # the real zones always come from the client via the POST body.
    intensity_zones = []
    
    return {
        'elevation_data': elevation_data,
        'efforts': efforts_data,
        'sprints': sprints_data,
        'cp': float(cp),
        'weight': float(weight),
        'intensity_zones': intensity_zones,
        'torque_available': 'torque' in df.columns,
        'config': {
            'window_sec': float(effort_config.window_seconds),
            'merge_pct': float(effort_config.merge_power_diff_percent),
            'min_cp_pct': float(effort_config.min_effort_intensity_cp),
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
            request=request,
            name="altimetria_d3.html",
            context={
                "request": request,
                "filename": session.get('filename', 'Unknown'),
                "chart_data_json": chart_data_json,
                "session_id": session_id
            }
        )

    except Exception as e:
        logger.error(f"Error generating D3 altimetria for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating visualization: {str(e)}")