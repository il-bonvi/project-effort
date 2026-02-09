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
from typing import Dict, Any, List, Tuple

# Add parent directory to path for PEFFORT package imports
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
import numpy as np

from PEFFORT.peffort_engine import (
    format_time_hhmmss, format_time_mmss, get_zone_color
)

logger = logging.getLogger(__name__)

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
        seg_time = time_sec[start:end]
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


@router.get("/altimetria-echarts/{session_id}", response_class=HTMLResponse)
async def altimetria_echarts_view(session_id: str):
    """
    Generate elevation profile visualization with ECharts.js
    
    Args:
        session_id: Session identifier from upload
        
    Returns:
        HTMLResponse with interactive ECharts elevation profile
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
        
        # Generate HTML with ECharts
        html_content = generate_echarts_html(chart_data_json, session['filename'])
        
        logger.info(f"Altimetria ECharts visualization generated for session {session_id}")
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Error generating altimetria echarts view: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating elevation profile: {str(e)}")


def generate_echarts_html(chart_data_json: str, filename: str) -> str:
    """Generate HTML with ECharts visualization"""
    
    html = f"""
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Altimetria ECharts - {filename}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        html, body {{
            height: 100vh;
            width: 100vw;
            overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: white;
        }}
        #container {{
            display: flex;
            height: 100vh;
            width: 100vw;
        }}
        #chart {{
            flex: 1;
            height: 100%;
        }}
        #sidebar {{
            width: 350px;
            height: 100%;
            overflow-y: auto;
            background: #f8f9fa;
            border-left: 2px solid #e5e7eb;
            padding: 15px;
        }}
        .effort-card, .sprint-card {{
            background: white;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-left: 4px solid;
        }}
        .effort-card {{
            cursor: pointer;
            transition: all 0.2s;
        }}
        .effort-card:hover {{
            transform: translateX(-3px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }}
        .card-header {{
            font-weight: bold;
            font-size: 1.1rem;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .card-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 6px;
            font-size: 0.85rem;
        }}
        .card-metric {{
            display: flex;
            justify-content: space-between;
        }}
        .metric-label {{
            color: #6b7280;
        }}
        .metric-value {{
            font-weight: 600;
            color: #111827;
        }}
        h2 {{
            font-size: 1.2rem;
            margin-bottom: 12px;
            color: #374151;
            padding-bottom: 8px;
            border-bottom: 2px solid #3b82f6;
        }}
        .section {{
            margin-bottom: 25px;
        }}
        .config-info {{
            background: white;
            padding: 10px;
            border-radius: 6px;
            font-size: 0.8rem;
            color: #6b7280;
            margin-bottom: 15px;
            line-height: 1.6;
        }}
    </style>
</head>
<body>
    <div id="container">
        <div id="chart"></div>
        <div id="sidebar">
            <div class="config-info" id="config-section"></div>
            <div class="section">
                <h2>⚡ Efforts</h2>
                <div id="efforts-list"></div>
            </div>
            <div class="section">
                <h2>💨 Sprints</h2>
                <div id="sprints-list"></div>
            </div>
        </div>
    </div>
    
    <script>
        const chartData = {chart_data_json};
        const chartDom = document.getElementById('chart');
        const myChart = echarts.init(chartDom);
        
        // Build series for ECharts
        const series = [];
        
        // Base elevation area
        series.push({{
            name: 'Altitudine',
            type: 'line',
            data: chartData.elevation_data.map(d => [d.dist, d.alt]),
            smooth: true,
            symbol: 'none',
            lineStyle: {{ color: '#d1d5db', width: 1 }},
            areaStyle: {{ color: '#f3f4f6' }},
            tooltip: {{
                formatter: function(params) {{
                    const point = chartData.elevation_data[params.dataIndex];
                    return `📏 ${{point.dist}} km<br/>🏔️ ${{point.alt}} m<br/>⏱️ ${{point.time}}`;
                }}
            }}
        }});
        
        // Efforts
        chartData.efforts.forEach((effort, idx) => {{
            series.push({{
                name: `E#${{effort.id + 1}} ${{effort.avg_power}}W`,
                type: 'line',
                data: effort.line_data,
                lineStyle: {{ color: effort.color, width: 4 }},
                symbol: 'none',
                emphasis: {{ lineStyle: {{ width: 6 }} }},
                tooltip: {{
                    formatter: function(params) {{
                        let html = `<div style="text-align:left;">`;
                        html += `<strong>E#${{effort.id + 1}}</strong> (Rank #${{effort.rank}})<br/>`;
                        html += `⚡ ${{effort.avg_power}} W | 5"🔺${{effort.best_5s_watt}} W 🌀 ${{effort.avg_cadence}} rpm<br/>`;
                        html += `⏱️ ${{effort.duration}}s | 🕒 ${{effort.start_time}} | ${{effort.ftp_pct}}%<br/>`;
                        html += `⚖️ ${{effort.avg_power_per_kg}} W/kg | 5"🔺${{effort.best_5s_watt_kg}} W/kg<br/>`;
                        html += `🔀 ${{effort.avg_watts_first}} W | ${{effort.avg_watts_second}} W | ${{effort.watts_ratio}}<br/>`;
                        if (effort.avg_hr > 0) {{
                            html += `❤️ ∅${{effort.avg_hr}} bpm | 🔺${{effort.max_hr}} bpm<br/>`;
                        }}
                        html += `🚴‍♂️ ${{effort.avg_speed}} km/h 📏 ∅ ${{effort.avg_grade}}% | 🔺${{effort.max_grade}}%<br/>`;
                        
                        if (effort.avg_grade >= 4.5) {{
                            const diff_vam = Math.abs(effort.vam_teorico - effort.vam);
                            const arrow = effort.vam_teorico - effort.vam > 0 ? '⬆️' : (effort.vam_teorico - effort.vam < 0 ? '⬇️' : '');
                            const wkg_teoric = effort.gradient_factor > 0 ? effort.vam / (effort.gradient_factor * 100) : 0;
                            const diff_wkg = effort.avg_power_per_kg - wkg_teoric;
                            const perc_err = effort.avg_power_per_kg != 0 ? (diff_wkg / effort.avg_power_per_kg * 100) : 0;
                            const sign = perc_err > 0 ? '+' : (perc_err < 0 ? '-' : '');
                            html += `🚵‍♂️ ${{effort.vam}} m/h ${{arrow}} ${{diff_vam.toFixed(0)}} m/h | ${{Math.abs(diff_wkg).toFixed(2)}} W/kg<br/>`;
                            html += `🧮 ${{effort.vam_teorico}} m/h | ${{wkg_teoric.toFixed(2)}} W/kg | ${{sign}}${{Math.abs(perc_err).toFixed(1)}}%<br/>`;
                        }} else {{
                            html += `🚵‍♂️ ${{effort.vam}} m/h<br/>`;
                        }}
                        
                        html += `🔋 ${{effort.kj}} kJ | ${{effort.kj_over_cp}} kJ > CP<br/>`;
                        html += `💪 ${{effort.kj_kg}} kJ/kg | ${{effort.kj_kg_over_cp}} kJ/kg > CP<br/>`;
                        html += `🔥 ${{effort.kj_h_kg}} kJ/h/kg | ${{effort.kj_h_kg_over_cp}} kJ/h/kg > CP`;
                        html += `</div>`;
                        return html;
                    }}
                }}
            }});
        }});
        
        // Sprints
        chartData.sprints.forEach((sprint, idx) => {{
            series.push({{
                name: `S#${{sprint.rank}} ${{sprint.avg_power}}W`,
                type: 'line',
                data: sprint.line_data,
                lineStyle: {{ color: '#000000', width: 4 }},
                symbol: 'none',
                emphasis: {{ lineStyle: {{ width: 6 }} }},
                tooltip: {{
                    formatter: function(params) {{
                        let html = `<div style="text-align:left;">`;
                        html += `<strong>S#${{sprint.rank}}</strong><br/>`;
                        html += `⚡ ${{sprint.avg_power}} W  ⚖️ ${{sprint.avg_power_per_kg}} W/kg<br/>`;
                        html += `⚡ 🔺${{sprint.max_watt}} W | 🔻${{sprint.min_watt}} W<br/>`;
                        if (sprint.min_hr > 0) {{
                            html += `❤️ 🔻${{sprint.min_hr}} bpm | 🔺${{sprint.max_hr}} bpm<br/>`;
                        }}
                        if (sprint.avg_cadence > 0) {{
                            html += `🌀 ∅${{sprint.avg_cadence}} rpm | 🔻${{sprint.min_cadence}} rpm | 🔺${{sprint.max_cadence}} rpm<br/>`;
                        }}
                        if (sprint.v1 > 0 && sprint.v2 > 0) {{
                            html += `➡️ ${{sprint.v1}} km/h | ${{sprint.v2}} km/h<br/>`;
                        }}
                        html += `📏 ∅ ${{sprint.avg_grade}}% max. ${{sprint.max_grade}}%`;
                        html += `</div>`;
                        return html;
                    }}
                }}
            }});
        }});
        
        // Chart options
        const option = {{
            title: {{
                text: `UNIFIED ANALYSIS | EFFORTS: MRG [${{chartData.config.merge_pct}}%] WIN [${{chartData.config.window_sec}}s] MIN [${{chartData.config.min_ftp_pct}}%FTP] | TRIM [${{chartData.config.trim_win}}s, ${{chartData.config.trim_low}}%] EXT [${{chartData.config.extend_win}}s, ${{chartData.config.extend_low}}%] | SPRINTS: WIN [${{chartData.config.sprint_window_sec}}s] MIN [${{chartData.config.min_sprint_power}}W]`,
                textStyle: {{ fontSize: 12, color: '#374151' }},
                left: 'center',
                top: 10
            }},
            grid: {{
                left: 60,
                right: 20,
                top: 60,
                bottom: 60
            }},
            xAxis: {{
                type: 'value',
                name: 'Distance (km)',
                nameLocation: 'middle',
                nameGap: 30,
                axisLabel: {{ formatter: '{{value}}' }}
            }},
            yAxis: {{
                type: 'value',
                name: 'Altitude (m)',
                nameLocation: 'middle',
                nameGap: 50
            }},
            tooltip: {{
                trigger: 'item',
                axisPointer: {{ type: 'cross' }},
                backgroundColor: 'rgba(50, 50, 50, 0.95)',
                borderColor: '#777',
                borderWidth: 1,
                textStyle: {{ color: '#fff' }}
            }},
            legend: {{
                type: 'scroll',
                orient: 'vertical',
                right: 10,
                top: 60,
                bottom: 20,
                data: series.map(s => s.name),
                textStyle: {{ fontSize: 11 }}
            }},
            series: series
        }};
        
        myChart.setOption(option);
        
        // Render config section
        const configSection = document.getElementById('config-section');
        configSection.innerHTML = `
            <strong>Configuration</strong><br/>
            FTP: ${{chartData.ftp}}W | Weight: ${{chartData.weight}}kg<br/>
            Efforts: WIN ${{chartData.config.window_sec}}s | MRG ${{chartData.config.merge_pct}}% | MIN ${{chartData.config.min_ftp_pct}}%<br/>
            Sprints: WIN ${{chartData.config.sprint_window_sec}}s | MIN ${{chartData.config.min_sprint_power}}W
        `;
        
        // Render efforts list
        const effortsList = document.getElementById('efforts-list');
        chartData.efforts.forEach(effort => {{
            const card = document.createElement('div');
            card.className = 'effort-card';
            card.style.borderLeftColor = effort.color;
            card.innerHTML = `
                <div class="card-header">
                    <span>E#${{effort.id + 1}}</span>
                    <span style="color: ${{effort.color}};">${{effort.avg_power}}W (${{effort.ftp_pct}}%)</span>
                </div>
                <div class="card-row">
                    <div class="card-metric">
                        <span class="metric-label">🕒 Start</span>
                        <span class="metric-value">${{effort.start_time}}</span>
                    </div>
                    <div class="card-metric">
                        <span class="metric-label">⏱️ Duration</span>
                        <span class="metric-value">${{effort.duration}}s</span>
                    </div>
                </div>
                <div class="card-row">
                    <div class="card-metric">
                        <span class="metric-label">📏 Distance</span>
                        <span class="metric-value">${{effort.distance_tot}} km</span>
                    </div>
                    <div class="card-metric">
                        <span class="metric-label">🏔️ Elevation</span>
                        <span class="metric-value">${{effort.elevation_gain}} m</span>
                    </div>
                </div>
                <div style="border-top: 1px solid #e5e7eb; padding-top: 8px; margin-top: 8px;">
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">⚡ Avg Power</span>
                            <span class="metric-value">${{effort.avg_power}}W</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">⚖️ W/kg</span>
                            <span class="metric-value">${{effort.avg_power_per_kg}}</span>
                        </div>
                    </div>
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">5" Peak</span>
                            <span class="metric-value">${{effort.best_5s_watt}}W</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">5" W/kg</span>
                            <span class="metric-value">${{effort.best_5s_watt_kg}}</span>
                        </div>
                    </div>
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">🌀 Cadence</span>
                            <span class="metric-value">${{effort.avg_cadence}} rpm</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">🔀 1st/2nd</span>
                            <span class="metric-value">${{effort.avg_watts_first}}/${{effort.avg_watts_second}}</span>
                        </div>
                    </div>
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">Ratio</span>
                            <span class="metric-value">${{effort.watts_ratio}}</span>
                        </div>
                    </div>
                </div>
                <div style="border-top: 1px solid #e5e7eb; padding-top: 8px; margin-top: 8px;">
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">❤️ HR Avg</span>
                            <span class="metric-value">${{effort.avg_hr > 0 ? effort.avg_hr + ' bpm' : '-'}}</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">❤️ HR Max</span>
                            <span class="metric-value">${{effort.max_hr > 0 ? effort.max_hr + ' bpm' : '-'}}</span>
                        </div>
                    </div>
                </div>
                <div style="border-top: 1px solid #e5e7eb; padding-top: 8px; margin-top: 8px;">
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">🚴 Speed</span>
                            <span class="metric-value">${{effort.avg_speed}} km/h</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">📏 Grade</span>
                            <span class="metric-value">${{effort.avg_grade}}%</span>
                        </div>
                    </div>
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">Grade Max</span>
                            <span class="metric-value">${{effort.max_grade}}%</span>
                        </div>
                    </div>
                </div>
                <div style="border-top: 1px solid #e5e7eb; padding-top: 8px; margin-top: 8px;">
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">🚵 VAM</span>
                            <span class="metric-value">${{effort.vam}} m/h</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">VAM Teor.</span>
                            <span class="metric-value">${{effort.vam_teorico}} m/h</span>
                        </div>
                    </div>
                </div>
                <div style="border-top: 1px solid #e5e7eb; padding-top: 8px; margin-top: 8px;">
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">🔋 kJ Total</span>
                            <span class="metric-value">${{effort.kj}} kJ</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">kJ > CP</span>
                            <span class="metric-value">${{effort.kj_over_cp}} kJ</span>
                        </div>
                    </div>
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">💪 kJ/kg</span>
                            <span class="metric-value">${{effort.kj_kg}}</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">kJ/kg > CP</span>
                            <span class="metric-value">${{effort.kj_kg_over_cp}}</span>
                        </div>
                    </div>
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">🔥 kJ/h/kg</span>
                            <span class="metric-value">${{effort.kj_h_kg}}</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">kJ/h/kg > CP</span>
                            <span class="metric-value">${{effort.kj_h_kg_over_cp}}</span>
                        </div>
                    </div>
                </div>
            `;
            effortsList.appendChild(card);
        }});
        
        // Render sprints list
        const sprintsList = document.getElementById('sprints-list');
        chartData.sprints.forEach(sprint => {{
            const card = document.createElement('div');
            card.className = 'sprint-card';
            card.style.borderLeftColor = '#000000';
            card.innerHTML = `
                <div class="card-header">
                    <span>S#${{sprint.rank}}</span>
                    <span style="color: #000000;">${{sprint.avg_power}}W</span>
                </div>
                <div class="card-row">
                    <div class="card-metric">
                        <span class="metric-label">⏱️ Duration</span>
                        <span class="metric-value">${{sprint.duration}}s</span>
                    </div>
                    <div class="card-metric">
                        <span class="metric-label">📏 Distance</span>
                        <span class="metric-value">${{sprint.distance_tot}} km</span>
                    </div>
                </div>
                <div class="card-row">
                    <div class="card-metric">
                        <span class="metric-label">🏔️ Elevation</span>
                        <span class="metric-value">${{sprint.elevation_gain}} m</span>
                    </div>
                </div>
                <div style="border-top: 1px solid #e5e7eb; padding-top: 8px; margin-top: 8px;">
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">⚡ Avg Power</span>
                            <span class="metric-value">${{sprint.avg_power}}W</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">⚖️ W/kg</span>
                            <span class="metric-value">${{sprint.avg_power_per_kg}}</span>
                        </div>
                    </div>
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">⚡ Max</span>
                            <span class="metric-value">${{sprint.max_watt}}W</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">⚡ Min</span>
                            <span class="metric-value">${{sprint.min_watt}}W</span>
                        </div>
                    </div>
                </div>
                <div style="border-top: 1px solid #e5e7eb; padding-top: 8px; margin-top: 8px;">
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">❤️ HR Max</span>
                            <span class="metric-value">${{sprint.max_hr > 0 ? sprint.max_hr + ' bpm' : '-'}}</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">❤️ HR Min</span>
                            <span class="metric-value">${{sprint.min_hr > 0 ? sprint.min_hr + ' bpm' : '-'}}</span>
                        </div>
                    </div>
                </div>
                <div style="border-top: 1px solid #e5e7eb; padding-top: 8px; margin-top: 8px;">
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">🌀 Avg Cad.</span>
                            <span class="metric-value">${{sprint.avg_cadence > 0 ? sprint.avg_cadence + ' rpm' : '-'}}</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">🌀 Min Cad.</span>
                            <span class="metric-value">${{sprint.min_cadence > 0 ? sprint.min_cadence + ' rpm' : '-'}}</span>
                        </div>
                    </div>
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">🌀 Max Cad.</span>
                            <span class="metric-value">${{sprint.max_cadence > 0 ? sprint.max_cadence + ' rpm' : '-'}}</span>
                        </div>
                    </div>
                </div>
                <div style="border-top: 1px solid #e5e7eb; padding-top: 8px; margin-top: 8px;">
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">➡️ Speed Start</span>
                            <span class="metric-value">${{sprint.v1 > 0 ? sprint.v1 + ' km/h' : '-'}}</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">➡️ Speed End</span>
                            <span class="metric-value">${{sprint.v2 > 0 ? sprint.v2 + ' km/h' : '-'}}</span>
                        </div>
                    </div>
                </div>
                <div style="border-top: 1px solid #e5e7eb; padding-top: 8px; margin-top: 8px;">
                    <div class="card-row">
                        <div class="card-metric">
                            <span class="metric-label">📏 Grade Avg</span>
                            <span class="metric-value">${{sprint.avg_grade}}%</span>
                        </div>
                        <div class="card-metric">
                            <span class="metric-label">📏 Grade Max</span>
                            <span class="metric-value">${{sprint.max_grade}}%</span>
                        </div>
                    </div>
                </div>
            `;
            sprintsList.appendChild(card);
        }});
        
        // Resize handler
        window.addEventListener('resize', function() {{
            myChart.resize();
        }});
    </script>
</body>
</html>
    """
    
    return html


