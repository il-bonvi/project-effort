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
from html import escape
from pathlib import Path
from typing import List, Tuple, Dict, Any

# Add parent directory to path for PEFFORT package imports
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

# Configure logging
logger = logging.getLogger(__name__)

# Shared sessions dict - set by setup_inspection_router()
_shared_sessions: Dict[str, Dict[str, Any]] = {}


def setup_inspection_router(sessions_dict: Dict[str, Dict[str, Any]]) -> APIRouter:
    """
    Set up the inspection router with access to shared sessions.

    Args:
        sessions_dict: Reference to the main sessions dictionary from app.py

    Returns:
        Configured APIRouter instance
    """
    global _shared_sessions
    _shared_sessions = sessions_dict
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
async def inspection_view(session_id: str):
    """
    Display the interactive inspection/effort editor view.
    Uses ECharts-based HTML generation for visualization and manipulation.
    """
    if session_id not in _shared_sessions:
        raise HTTPException(status_code=404, detail="Session not found. Please upload a FIT file.")

    session = _shared_sessions[session_id]
    df = session['df']
    efforts = session['efforts']
    sprints = session.get('sprints', [])
    ftp = session['ftp']
    weight = session['weight']
    stats = session.get('stats', {})

    # Generate HTML using the same logic as inspection_web_gui.py
    html_content = generate_inspection_html(
        df=df,
        efforts=efforts,
        sprints=sprints,
        ftp=ftp,
        weight=weight,
        stats=stats,
        session_id=session_id,
        filename=session['filename']
    )

    return HTMLResponse(content=html_content)


# =============================================================================
# HTML GENERATION - Extracted from inspection_web_gui.py (300+ lines)
# =============================================================================

def generate_inspection_html(
    df,
    efforts: List[Tuple[int, int, float]],
    sprints: List[Dict[str, Any]],
    ftp: float,
    weight: float,
    stats: Dict[str, Any],
    session_id: str,
    filename: str
) -> str:
    """
    Generate interactive ECharts HTML for effort inspection.
    Includes complete HTML/CSS/JS for:
    - Three synchronized power graphs (raw, 30s moving avg, 60s moving avg)
    - Effort legend with delete buttons and drag-drop support
    - Sprint legend display
    - Control panel with configurable sliders
    - FTP input control
    - Save modifications button with JSON download
    - Complete JavaScript for: centered moving average calculation, drag-drop,
      zoom/pan controls, effort rebinding

    Args:
        df: Pandas DataFrame with FIT data (time_sec, power columns required)
        efforts: List of effort tuples (start_idx, end_idx, avg_power)
        sprints: List of sprint dictionaries
        ftp: Functional Threshold Power in watts
        weight: Body weight in kilograms
        stats: Dictionary of ride statistics
        session_id: Session ID for API calls
        filename: Original FIT filename

    Returns:
        Complete HTML document as string
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
        start_idx = sprint.get('start_idx', sprint.get('start', 0))
        end_idx = sprint.get('end_idx', sprint.get('end', start_idx + 1))

        if not (0 <= start_idx < n_samples and 0 < end_idx <= n_samples and end_idx > start_idx):
            continue

        start_time = time_axis[start_idx]
        end_time = time_axis[end_idx - 1]

        color = sprint_colors[i % len(sprint_colors)]
        sprints_data.append({
            'id': i,
            'start': start_time,
            'end': end_time,
            'max_power': sprint.get('max_power', 0),
            'avg_power': sprint.get('avg_power', 0),
            'duration': sprint.get('duration', end_time - start_time),
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
    ftp_json = json.dumps(ftp)

    # Escape filename for safe HTML rendering
    safe_filename = escape(filename)

    html = f"""
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PEFFORT Web - Inspection: {safe_filename}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #ffffff;
            color: #111827;
            padding: 15px;
            line-height: 1.6;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border-radius: 8px;
            margin-bottom: 20px;
            color: white;
        }}
        .header h1 {{
            font-size: 1.5rem;
            background: linear-gradient(135deg, #60a5fa, #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .header-info {{
            display: flex;
            gap: 20px;
            font-size: 0.9rem;
            color: #94a3b8;
        }}
        .header-info strong {{
            color: #60a5fa;
        }}
        .back-btn {{
            display: inline-block;
            padding: 8px 16px;
            background: linear-gradient(135deg, #3b82f6, #2563eb);
            color: white;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 600;
            transition: all 0.3s ease;
        }}
        .back-btn:hover {{
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
        }}
        #mainChart {{
            width: 100%;
            height: 800px;
            border-radius: 6px;
            border: 1px solid #d1d5db;
            background: #ffffff;
            margin-bottom: 20px;
        }}
        .legend {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
            margin-bottom: 20px;
        }}
        .legend-item {{
            padding: 10px;
            background: #f9fafb;
            border-radius: 6px;
            border-left: 4px solid;
            font-size: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .legend-color {{
            width: 16px;
            height: 16px;
            border-radius: 3px;
            flex-shrink: 0;
        }}
        .legend-item.deleted {{
            opacity: 0.5;
            text-decoration: line-through;
            background: #fef2f2 !important;
        }}
        .delete-btn {{
            margin-left: auto;
            background: #ef4444;
            color: white;
            border: none;
            border-radius: 50%;
            width: 24px;
            height: 24px;
            padding: 0;
            font-size: 16px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
            flex-shrink: 0;
        }}
        .delete-btn:hover {{
            background: #dc2626;
            transform: scale(1.1);
        }}
        .control-panel {{
            display: flex;
            align-items: flex-start;
            justify-content: center;
            gap: 30px;
            margin: 20px 0;
            padding: 20px;
            background: linear-gradient(135deg, #f8fafc, #f1f5f9);
            border-radius: 12px;
            border: 2px solid #e2e8f0;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        }}
        .control-group {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 12px;
            min-width: 300px;
            flex: 1;
            text-align: center;
        }}
        .control-group label {{
            font-size: 13px;
            font-weight: bold;
            color: #374151;
        }}
        .slider-container {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
            width: 100%;
        }}
        .control-group input[type="range"] {{
            width: 250px;
            height: 10px;
            border-radius: 5px;
            background: linear-gradient(to right, #fee2e2 0%, #fecaca 50%, #fca5a5 100%);
            outline: none;
            cursor: pointer;
        }}
        .value-display {{
            font-size: 16px;
            font-weight: bold;
            color: #1f2937;
            background: linear-gradient(135deg, #ffffff, #f8fafc);
            padding: 6px 12px;
            border-radius: 6px;
            min-width: 50px;
            text-align: center;
            border: 2px solid #e5e7eb;
        }}
        .ftp-panel {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
            margin: 20px 0;
            padding: 15px;
            background: linear-gradient(135deg, #eff6ff, #f0f9ff);
            border-radius: 8px;
            border: 2px solid #bfdbfe;
        }}
        .ftp-control {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .ftp-control label {{
            font-size: 13px;
            font-weight: bold;
            color: #1e40af;
        }}
        .ftp-control input {{
            width: 80px;
            padding: 6px 8px;
            border: 2px solid #bfdbfe;
            border-radius: 4px;
            font-size: 13px;
            text-align: center;
            background: white;
            color: #1f2937;
            font-weight: bold;
        }}
        .save-controls {{
            margin: 15px 0;
            text-align: center;
        }}
        .save-btn {{
            background: linear-gradient(135deg, #3b82f6, #2563eb);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            font-weight: bold;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s ease;
        }}
        .save-btn:hover {{
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
        }}
        #saveStatus {{
            margin-top: 8px;
            font-size: 12px;
            color: #666;
            min-height: 16px;
        }}
        .instructions {{
            padding: 15px;
            background: #f9fafb;
            border-radius: 6px;
            border-left: 4px solid #22c55e;
            font-size: 12px;
            color: #374151;
            margin-top: 15px;
        }}
        .instructions strong {{
            color: #111827;
            display: block;
            margin-bottom: 8px;
        }}
        .tip {{
            margin: 3px 0;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>🚴 PEFFORT Web - Effort Inspection</h1>
            <div class="header-info">
                <span><strong>File:</strong> {safe_filename}</span>
                <span><strong>Efforts:</strong> {len(efforts_data)}</span>
                <span><strong>Sprints:</strong> {len(sprints_data)}</span>
                <span><strong>FTP:</strong> {ftp}W</span>
                <span><strong>Weight:</strong> {weight}kg</span>
                <span><strong>Session:</strong> {session_id}</span>
            </div>
        </div>
        <a href="/" class="back-btn">⬅️ Nuovo Upload</a>
    </div>

    {stats_html}

    <div id="mainChart" style="width: 100%; height: 800px; border-radius: 6px; border: 1px solid #d1d5db; background: #ffffff;"></div>

    <div style="margin: 20px 0;">
        <h3 style="font-size: 1.2rem; color: #374151; margin-bottom: 10px;">💪 Efforts Detected</h3>
        <div class="legend" id="legend"></div>
    </div>

    <div style="margin: 20px 0;" id="sprintsContainer">
        <h3 style="font-size: 1.2rem; color: #374151; margin-bottom: 10px;">🚀 Sprints Detected</h3>
        <div class="legend" id="sprintsLegend"></div>
    </div>

    <div class="control-panel">
        <div class="control-group">
            <label for="avg30sSeconds">🟠 Chart 2 - Avg</label>
            <div class="slider-container">
                <span class="value-display" id="avg30sValue">30s</span>
                <input type="range" id="avg30sSeconds" value="30" min="1" max="60" step="1">
            </div>
        </div>

        <div class="control-group">
            <label for="avg60sSeconds">🔴 Chart 3 - Avg</label>
            <div class="slider-container">
                <span class="value-display" id="avg60sValue">60s</span>
                <input type="range" id="avg60sSeconds" value="60" min="60" max="360" step="1">
            </div>
        </div>
    </div>

    <div class="ftp-panel">
        <div class="ftp-control">
            <label for="ftpInput">FTP:</label>
            <input type="number" id="ftpInput" value="{int(ftp)}" min="50" max="500" step="5">
            <span style="font-size: 12px; color: #1e40af; font-weight: bold;">W</span>
        </div>
    </div>

    <div class="save-controls">
        <button id="saveButton" class="save-btn">💾 Salva Modifiche</button>
        <div id="saveStatus"></div>
    </div>

    <div class="instructions">
        <strong>🎮 Controlli Interattivi:</strong>
        <div class="tip">• <strong>🔵 Grafico 1:</strong> Potenza istantanea per vedere i picchi</div>
        <div class="tip">• <strong>🟠 Grafico 2:</strong> Media centrata configurabile (1-60s, default 30s)</div>
        <div class="tip">• <strong>🔴 Grafico 3:</strong> Media centrata configurabile (60-360s, default 60s)</div>
        <div class="tip">• <strong>Pan:</strong> Clic sinistro + drag per spostare qualsiasi grafico</div>
        <div class="tip">• <strong>Zoom:</strong> Rotella del mouse per zoomare</div>
        <div class="tip">• <strong>Drag & Drop:</strong> Clic destro sui punti START/END per modificare gli intervalli</div>
        <div class="tip">• <strong>Elimina Effort:</strong> Clicca il bottone '×' nella legenda</div>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            const timeAxis = {time_axis_json};
            const powerData = {power_data_json};
            const effortsData = {efforts_data_json};
            const sprintsData = {sprints_data_json};
            let ftp = {ftp_json};

            const samplingRate = timeAxis.length > 1 ? 1 / (timeAxis[1] - timeAxis[0]) : 1;
            let avg30sSeconds = 30;
            let avg60sSeconds = 60;

            if (sprintsData.length === 0) {{
                document.getElementById('sprintsContainer').style.display = 'none';
            }}

            function calculateCenteredMovingAverage(data, windowSize) {{
                const result = [];
                const halfWindow = Math.floor(windowSize / 2);
                for (let i = 0; i < data.length; i++) {{
                    const start = Math.max(0, i - halfWindow);
                    const end = Math.min(data.length, i + halfWindow + 1);
                    const slice = data.slice(start, end);
                    const avg = slice.reduce((sum, val) => sum + val, 0) / slice.length;
                    result.push(avg);
                }}
                return result;
            }}

            const power30s = calculateCenteredMovingAverage(powerData, Math.round(avg30sSeconds * samplingRate));
            const power60s = calculateCenteredMovingAverage(powerData, Math.round(avg60sSeconds * samplingRate));

            const powerCoords = timeAxis.map((time, idx) => [time, powerData[idx]]);
            const power30sCoords = timeAxis.map((time, idx) => [time, power30s[idx]]);
            const power60sCoords = timeAxis.map((time, idx) => [time, power60s[idx]]);

            const deletedEfforts = new Set();
            const legendDiv = document.getElementById('legend');

            effortsData.forEach((effort, idx) => {{
                const item = document.createElement('div');
                item.className = 'legend-item';
                item.id = `effort-${{idx}}`;
                item.style.borderLeftColor = effort.color;
                item.innerHTML = `
                    <div style="display: flex; gap: 8px; align-items: center; flex: 1;">
                        <div class="legend-color" style="background: ${{effort.color}};"></div>
                        <div>
                            <strong>${{effort.label}}</strong><br>
                            <span style="color: #9ca3b8;">
                                ${{effort.start.toFixed(0)}}s - ${{effort.end.toFixed(0)}}s | ${{(effort.end - effort.start).toFixed(0)}}s | ${{effort.avg_power.toFixed(0)}}W
                            </span>
                        </div>
                    </div>
                    <button class="delete-btn" data-effort-idx="${{idx}}">×</button>
                `;
                legendDiv.appendChild(item);

                const deleteBtn = item.querySelector('.delete-btn');
                deleteBtn.addEventListener('click', function(e) {{
                    e.preventDefault();
                    const effortIdx = parseInt(this.dataset.effortIdx);
                    if (deletedEfforts.has(effortIdx)) {{
                        deletedEfforts.delete(effortIdx);
                        item.classList.remove('deleted');
                    }} else {{
                        deletedEfforts.add(effortIdx);
                        item.classList.add('deleted');
                    }}
                    rebuildChart();
                }});
            }});

            const sprintsLegendDiv = document.getElementById('sprintsLegend');
            sprintsData.forEach((sprint, idx) => {{
                const item = document.createElement('div');
                item.className = 'legend-item';
                item.style.borderLeftColor = sprint.color;
                item.style.background = '#fef2f2';
                item.innerHTML = `
                    <div style="display: flex; gap: 8px; align-items: center; flex: 1;">
                        <div class="legend-color" style="background: ${{sprint.color}};"></div>
                        <div>
                            <strong>${{sprint.label}}</strong><br>
                            <span style="color: #9ca3b8;">
                                ${{sprint.start.toFixed(0)}}s - ${{sprint.end.toFixed(0)}}s | ${{sprint.duration.toFixed(1)}}s | Max: ${{sprint.max_power.toFixed(0)}}W | Avg: ${{sprint.avg_power.toFixed(0)}}W
                            </span>
                        </div>
                    </div>
                `;
                sprintsLegendDiv.appendChild(item);
            }});

            const mainChartDiv = document.getElementById('mainChart');
            let myChart = echarts.init(mainChartDiv, 'light');
            const minTime = Math.min(...timeAxis);
            const maxTime = Math.max(...timeAxis);
            const maxPower = Math.max(...powerData);

            function buildOption() {{
                const option = {{
                    tooltip: {{
                        trigger: 'axis',
                        backgroundColor: '#ffffff',
                        borderColor: '#d1d5db',
                        borderWidth: 2,
                        textStyle: {{ color: '#111827', fontSize: 12 }},
                        axisPointer: {{
                            type: 'line',
                            lineStyle: {{ color: '#9ca3af', type: 'dashed' }},
                            link: [{{ xAxisIndex: 'all' }}]
                        }}
                    }},
                    grid: [
                        {{ left: 70, right: 30, top: '4%', height: '26%', show: true }},
                        {{ left: 70, right: 30, top: '30%', height: '26%', show: true }},
                        {{ left: 70, right: 30, top: '56%', bottom: 50, show: true }}
                    ],
                    xAxis: [
                        {{ gridIndex: 0, type: 'value', min: 0, max: maxTime, show: false }},
                        {{ gridIndex: 1, type: 'value', min: 0, max: maxTime, show: false }},
                        {{ gridIndex: 2, type: 'value', name: 'Tempo (secondi)', min: 0, max: maxTime,
                           nameTextStyle: {{ color: '#374151', fontSize: 11 }},
                           axisLabel: {{ color: '#374151', fontSize: 10, formatter: function(val) {{
                               const mins = Math.floor(val / 60);
                               const secs = Math.round(val % 60);
                               return mins > 0 ? mins + 'm' + secs + 's' : val.toFixed(0) + 's';
                           }} }},
                           splitLine: {{ lineStyle: {{ color: '#f3f4f6' }} }},
                           axisLine: {{ lineStyle: {{ color: '#6b7280', width: 1 }} }}
                        }}
                    ],
                    yAxis: [
                        {{ gridIndex: 0, type: 'value', name: 'Power (W)', min: 0, max: Math.ceil(maxPower * 1.1),
                           nameLocation: 'middle', nameRotate: 90, nameGap: 40, nameTextStyle: {{ color: '#374151', fontSize: 10 }},
                           axisLabel: {{ color: '#374151', fontSize: 9 }}, splitLine: {{ lineStyle: {{ color: '#f3f4f6' }} }} }},
                        {{ gridIndex: 1, type: 'value', name: avg30sSeconds + 's Avg (W)', min: 0, max: Math.ceil(maxPower * 1.1),
                           nameLocation: 'middle', nameRotate: 90, nameGap: 40, nameTextStyle: {{ color: '#374151', fontSize: 10 }},
                           axisLabel: {{ color: '#374151', fontSize: 9 }}, splitLine: {{ lineStyle: {{ color: '#f3f4f6' }} }} }},
                        {{ gridIndex: 2, type: 'value', name: avg60sSeconds + 's Avg (W)', min: 0, max: Math.ceil(maxPower * 1.1),
                           nameLocation: 'middle', nameRotate: 90, nameGap: 40, nameTextStyle: {{ color: '#374151', fontSize: 10 }},
                           axisLabel: {{ color: '#374151', fontSize: 9 }}, splitLine: {{ lineStyle: {{ color: '#f3f4f6' }} }} }}
                    ],
                    dataZoom: [
                        {{ type: 'slider', show: true, xAxisIndex: [0, 1, 2], start: 0, end: 100,
                           textStyle: {{ color: '#374151' }}, fillerColor: 'rgba(59, 130, 246, 0.15)',
                           borderColor: '#d1d5db', backgroundColor: '#f9fafb', height: 20, bottom: 10 }},
                        {{ type: 'inside', xAxisIndex: [0, 1, 2], start: 0, end: 100 }}
                    ],
                    series: [
                        {{ name: 'Power', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: powerCoords,
                           smooth: 0.5, lineStyle: {{ color: '#3b82f6', width: 2 }},
                           areaStyle: {{ color: 'rgba(59, 130, 246, 0.1)' }}, symbol: 'none',
                           sampling: 'average', itemStyle: {{ color: '#3b82f6' }}, z: 1 }},
                        {{ name: '30s Avg Power', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: power30sCoords,
                           smooth: 0.3, lineStyle: {{ color: '#f59e0b', width: 2 }},
                           areaStyle: {{ color: 'rgba(245, 158, 11, 0.1)' }}, symbol: 'none',
                           sampling: 'average', itemStyle: {{ color: '#f59e0b' }}, z: 1 }},
                        {{ name: '60s Avg Power', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: power60sCoords,
                           smooth: 0.3, lineStyle: {{ color: '#ef4444', width: 2 }},
                           areaStyle: {{ color: 'rgba(239, 68, 68, 0.1)' }}, symbol: 'none',
                           sampling: 'average', itemStyle: {{ color: '#ef4444' }}, z: 1 }}
                    ]
                }};

                effortsData.forEach((effort, idx) => {{
                    if (deletedEfforts.has(idx)) return;
                    const startIdx = timeAxis.findIndex(t => t >= effort.start);
                    const endIdx = timeAxis.findIndex(t => t >= effort.end);
                    const startPower = startIdx >= 0 ? powerData[startIdx] : 0;
                    const endPower = endIdx >= 0 ? powerData[endIdx] : 0;

                    for (let gridIdx = 0; gridIdx < 3; gridIdx++) {{
                        option.series.push({{
                            name: effort.label, type: 'line', xAxisIndex: gridIdx, yAxisIndex: gridIdx,
                            data: [], lineStyle: {{ opacity: 0 }},
                            markArea: {{
                                silent: true,
                                itemStyle: {{ color: effort.color, opacity: 0.15, borderColor: effort.color, borderWidth: 1 }},
                                label: {{
                                    show: gridIdx === 0, position: 'top', color: effort.color,
                                    fontSize: 11, fontWeight: 'bold', formatter: effort.label,
                                    backgroundColor: '#ffffff', borderColor: effort.color, borderWidth: 1, borderRadius: 3, padding: [2, 6]
                                }},
                                data: [[{{ xAxis: effort.start }}, {{ xAxis: effort.end }}]]
                            }}, z: 0
                        }});

                        if (gridIdx === 0) {{
                            option.series.push({{
                                name: effort.label + ' (punti)', type: 'scatter', xAxisIndex: gridIdx, yAxisIndex: gridIdx,
                                data: [[effort.start, startPower], [effort.end, endPower]],
                                symbolSize: 10, color: effort.color,
                                itemStyle: {{ color: effort.color, borderColor: '#fff', borderWidth: 1, opacity: 0.8 }},
                                label: {{
                                    show: true, position: 'top', color: effort.color, fontSize: 9, fontWeight: 'bold',
                                    formatter: function(params) {{ return params.dataIndex === 0 ? 'START' : 'END'; }},
                                    backgroundColor: '#ffffff', borderColor: effort.color, borderWidth: 1, borderRadius: 2, padding: [1, 3]
                                }}, z: 4
                            }});
                        }}
                    }}
                }});

                const ftpLineData = timeAxis.map((t, i) => [t, ftp]);
                for (let i = 0; i < 3; i++) {{
                    option.series.push({{
                        name: 'FTP', type: 'line', xAxisIndex: i, yAxisIndex: i, data: ftpLineData,
                        lineStyle: {{ color: '#4b5563', width: 1, type: 'dashed' }},
                        smooth: false, z: 999, symbol: 'none', animation: false
                    }});
                }}

                sprintsData.forEach((sprint, idx) => {{
                    option.series.push({{
                        name: sprint.label, type: 'line', xAxisIndex: 0, yAxisIndex: 0,
                        data: [], lineStyle: {{ opacity: 0 }},
                        markArea: {{
                            silent: true,
                            itemStyle: {{ color: sprint.color, opacity: 0.25, borderColor: sprint.color, borderWidth: 2, borderType: 'solid' }},
                            label: {{
                                show: true, position: 'insideTop', color: '#fff',
                                fontSize: 10, fontWeight: 'bold', formatter: sprint.label,
                                backgroundColor: sprint.color, borderRadius: 3, padding: [2, 6]
                            }},
                            data: [[{{ xAxis: sprint.start }}, {{ xAxis: sprint.end }}]]
                        }}, z: 2
                    }});
                }});

                return option;
            }}

            function rebuildChart() {{
                const currentOption = myChart.getOption();
                let dataZoomState = null;
                if (currentOption && currentOption.dataZoom && currentOption.dataZoom[0]) {{
                    dataZoomState = {{ start: currentOption.dataZoom[0].start, end: currentOption.dataZoom[0].end }};
                }}
                const newOption = buildOption();
                if (dataZoomState) {{
                    newOption.dataZoom[0].start = dataZoomState.start;
                    newOption.dataZoom[0].end = dataZoomState.end;
                    newOption.dataZoom[1].start = dataZoomState.start;
                    newOption.dataZoom[1].end = dataZoomState.end;
                }}
                myChart.setOption(newOption, {{ notMerge: true }});
            }}

            function updateMovingAverages() {{
                const window30sSize = Math.round(avg30sSeconds * samplingRate);
                const power30sAvg = calculateCenteredMovingAverage(powerData, window30sSize);
                const power30sNewCoords = timeAxis.map((time, idx) => [time, power30sAvg[idx]]);
                const window60sSize = Math.round(avg60sSeconds * samplingRate);
                const power60sAvg = calculateCenteredMovingAverage(powerData, window60sSize);
                const power60sNewCoords = timeAxis.map((time, idx) => [time, power60sAvg[idx]]);
                power30sCoords.length = 0;
                power30sCoords.push(...power30sNewCoords);
                power60sCoords.length = 0;
                power60sCoords.push(...power60sNewCoords);
                rebuildChart();
            }}

            myChart.setOption(buildOption());

            const avg30sInput = document.getElementById('avg30sSeconds');
            const avg30sValue = document.getElementById('avg30sValue');
            const avg60sInput = document.getElementById('avg60sSeconds');
            const avg60sValue = document.getElementById('avg60sValue');
            const ftpInput = document.getElementById('ftpInput');

            let updateTimeout = null;
            avg30sInput.addEventListener('input', function() {{
                avg30sSeconds = parseInt(this.value);
                avg30sValue.textContent = avg30sSeconds + 's';
                if (updateTimeout) clearTimeout(updateTimeout);
                updateTimeout = setTimeout(updateMovingAverages, 50);
            }});

            avg60sInput.addEventListener('input', function() {{
                avg60sSeconds = parseInt(this.value);
                avg60sValue.textContent = avg60sSeconds + 's';
                if (updateTimeout) clearTimeout(updateTimeout);
                updateTimeout = setTimeout(updateMovingAverages, 50);
            }});

            ftpInput.addEventListener('change', function() {{
                ftp = parseInt(this.value);
                rebuildChart();
            }});

            let draggingState = null;
            document.addEventListener('contextmenu', function(e) {{
                if (mainChartDiv.contains(e.target)) e.preventDefault();
            }});

            document.addEventListener('mousedown', function(e) {{
                if (!mainChartDiv.contains(e.target) || e.button !== 2) return;
                e.preventDefault();
                const rect = mainChartDiv.getBoundingClientRect();
                const relativeY = e.clientY - rect.top;
                const gridIndex = Math.floor(relativeY / rect.height * 3);
                const pixelCoords = myChart.convertFromPixel({{ gridIndex: Math.min(gridIndex, 2) }}, [e.clientX - rect.left, relativeY]);
                if (!pixelCoords) return;
                const clickTime = pixelCoords[0];
                const tolerance = (maxTime - minTime) * 0.01;
                let closestMatch = null;
                let closestDistance = Infinity;
                effortsData.forEach((effort, effortIdx) => {{
                    if (deletedEfforts.has(effortIdx)) return;
                    const distToStart = Math.abs(clickTime - effort.start);
                    if (distToStart < tolerance && distToStart < closestDistance) {{
                        closestMatch = {{ effortIdx, isStart: true }};
                        closestDistance = distToStart;
                    }}
                    const distToEnd = Math.abs(clickTime - effort.end);
                    if (distToEnd < tolerance && distToEnd < closestDistance) {{
                        closestMatch = {{ effortIdx, isStart: false }};
                        closestDistance = distToEnd;
                    }}
                }});
                if (closestMatch) {{
                    draggingState = {{ ...closestMatch, gridIndex: Math.min(gridIndex, 2) }};
                }}
            }});

            document.addEventListener('mousemove', function(e) {{
                if (!draggingState) return;
                const effort = effortsData[draggingState.effortIdx];
                const rect = mainChartDiv.getBoundingClientRect();
                const pixelCoords = myChart.convertFromPixel({{ gridIndex: draggingState.gridIndex }}, [e.clientX - rect.left, e.clientY - rect.top]);
                if (!pixelCoords) return;
                const newTime = Math.max(0, Math.min(maxTime, pixelCoords[0]));
                if (draggingState.isStart) {{
                    if (newTime < effort.end - 5) effort.start = newTime;
                }} else {{
                    if (newTime > effort.start + 5) effort.end = newTime;
                }}
                rebuildChart();
                const legendItem = document.getElementById(`effort-${{draggingState.effortIdx}}`);
                if (legendItem) {{
                    const infoDiv = legendItem.querySelector('div > div:last-child');
                    if (infoDiv) {{
                        infoDiv.innerHTML = `
                            <strong>${{effort.label}}</strong><br>
                            <span style="color: #9ca3b8;">
                                ${{effort.start.toFixed(0)}}s - ${{effort.end.toFixed(0)}}s | ${{(effort.end - effort.start).toFixed(0)}}s | ${{effort.avg_power.toFixed(0)}}W
                            </span>
                        `;
                    }}
                }}
            }});

            document.addEventListener('mouseup', function() {{
                draggingState = null;
            }});

            window.addEventListener('resize', function() {{
                myChart.resize();
            }});

            document.getElementById('saveButton').addEventListener('click', function() {{
                const saveBtn = this;
                const saveStatus = document.getElementById('saveStatus');
                saveBtn.disabled = true;
                saveBtn.textContent = '⏳ Salvataggio...';
                const modifiedEfforts = effortsData.map((effort, idx) => ({{
                    index: idx,
                    new_start: effort.start,
                    new_end: effort.end,
                    duration: effort.end - effort.start,
                    avg_power: effort.avg_power,
                    label: effort.label,
                    deleted: deletedEfforts.has(idx)
                }}));
                const activeEfforts = modifiedEfforts.filter(e => !e.deleted);
                const dataToSend = {{
                    session_id: '{session_id}',
                    efforts: activeEfforts,
                    deleted_efforts: Array.from(deletedEfforts),
                    timestamp: new Date().toISOString(),
                    total_efforts_original: modifiedEfforts.length,
                    total_efforts_active: activeEfforts.length
                }};
                const jsonData = JSON.stringify(dataToSend, null, 2);
                const blob = new Blob([jsonData], {{ type: 'application/json' }});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'effort_modifications.json';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                saveBtn.disabled = false;
                saveBtn.textContent = '✅ File Scaricato!';
                saveStatus.textContent = 'File delle modifiche scaricato.';
                saveStatus.style.color = '#22c55e';
                setTimeout(() => {{
                    saveBtn.textContent = '💾 Salva Modifiche';
                    saveStatus.textContent = '';
                }}, 3000);
            }});
        }});
    </script>
</body>
</html>
    """

    return html


__all__ = ['router', 'setup_inspection_router', 'generate_inspection_html']
