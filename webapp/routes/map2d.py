"""Map2D route - 2D map visualization with Leaflet.js + OpenStreetMap (free, no API key)"""

import logging
import json
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from routes.altimetria_d3 import get_chart_data_json
from utils.effort_analyzer import format_time_hhmmss, format_time_mmss

logger = logging.getLogger(__name__)

_shared_sessions: Dict[str, Any] = {}

router = APIRouter()


def _build_map2d_cache_signature(session: Dict[str, Any]) -> tuple[Any, ...]:
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


def setup_map2d_router(sessions_dict: Dict[str, Any]):
    """Setup the map2d router with shared sessions dictionary"""
    global _shared_sessions
    _shared_sessions = sessions_dict


@router.get("/map2d/{session_id}", response_class=HTMLResponse)
async def map2d_view(session_id: str):
    """
    Generate 2D map visualization with Leaflet.js + OpenStreetMap.
    Completely free — no API key required.
    """
    if session_id not in _shared_sessions:
        raise HTTPException(status_code=404, detail="Session not found. Please upload a FIT file first.")

    session = _shared_sessions[session_id]
    df      = session['df']
    efforts = session['efforts']
    sprints = session['sprints']
    cp      = session.get('cp', session.get('ftp', 250))
    weight  = session['weight']

    if 'position_lat' not in df.columns or 'position_long' not in df.columns:
        raise HTTPException(
            status_code=400,
            detail="GPS data not available in this FIT file."
        )

    try:
        signature = _build_map2d_cache_signature(session)
        cache = session.get('_map2d_html_cache')
        if isinstance(cache, dict) and cache.get('signature') == signature and isinstance(cache.get('html'), str):
            logger.info(f"2D Map cache hit for session {session_id}")
            return HTMLResponse(content=cache['html'])

        # Reuse the same data-preparation pipeline as the 3D map
        import numpy as np

        # ── Build GeoJSON track ──
        from utils.map3d_core import export_traccia_geojson, calculate_zoom_level
        from utils.map3d_core import prepare_efforts_data

        lat_all = df['position_lat'].values
        lon_all = df['position_long'].values
        nan_mask   = (~np.isnan(lat_all)) & (~np.isnan(lon_all))
        range_mask = (np.abs(lat_all) <= 90) & (np.abs(lon_all) <= 180)
        zero_mask  = ~((np.abs(lat_all) < 1e-9) & (np.abs(lon_all) < 1e-9))
        valid_mask = nan_mask & range_mask & zero_mask
        df_geom = df.loc[valid_mask].copy()

        geojson_data, orig_indices = export_traccia_geojson(df_geom)
        geojson_str = json.dumps(geojson_data)

        lat = df_geom['position_lat'].values
        lon = df_geom['position_long'].values
        if len(lat) == 0:
            raise ValueError("No valid GPS data available")

        center_lat = float(np.nanmean([np.nanmin(lat), np.nanmax(lat)]))
        center_lon = float(np.nanmean([np.nanmin(lon), np.nanmax(lon)]))
        zoom = calculate_zoom_level(lat, lon)

        alt_full     = df['altitude'].values   if 'altitude'    in df.columns else np.zeros(len(df))
        dist_full    = df['distance_km'].values if 'distance_km' in df.columns else np.zeros(len(df))
        alt_filtered = df_geom['altitude'].values   if 'altitude'    in df_geom.columns else np.zeros(len(df_geom))
        dist_filtered= df_geom['distance_km'].values if 'distance_km' in df_geom.columns else np.zeros(len(df_geom))

        distance_km = float(np.max(dist_full)) if len(dist_full) > 0 else 0.0

        efforts_data_json = prepare_efforts_data(
            df, efforts, sprints, cp, weight, geojson_data,
            orig_indices, alt_full, dist_full, alt_filtered, dist_filtered
        )
        efforts_list = json.loads(efforts_data_json)

        # Full elevation/power data for altimetry chart
        time_total    = df['time_sec'].values.tolist()   if 'time_sec'   in df.columns else list(range(len(df)))
        power_total   = df['power'].values.tolist()       if 'power'      in df.columns else [0.0]*len(df)
        hr_total      = df['heartrate'].values.tolist()   if 'heartrate'  in df.columns else [0.0]*len(df)
        cadence_total = df['cadence'].values.tolist()     if 'cadence'    in df.columns else [0.0]*len(df)
        
        # Format time values as HH:MM:SS or MM:SS
        time_formatted = []
        for t in time_total:
            if t >= 3600:
                time_formatted.append(format_time_hhmmss(t))
            else:
                time_formatted.append(format_time_mmss(t))

        elevation_graph_data = json.dumps({
            'distance':  dist_full.tolist(),
            'altitude':  alt_full.tolist(),
            'time_sec':  time_total,
            'time':      time_formatted,
            'power':     power_total,
            'heartrate': hr_total,
            'cadence':   cadence_total,
            'efforts':   efforts_list,
        })

        # Chart data (zones, cp, sprints with stream data)
        try:
            chart_data_json = get_chart_data_json(session)
        except Exception as e:
            logger.warning(f"Could not prepare chart data: {e}")
            chart_data_json = '{}'

        # ── Render template ──
        templates_dir = Path(__file__).parent.parent / 'templates'
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(['html', 'xml'])
        )
        template = env.get_template('map2d.html')

        html = template.render(
            distance_km   = distance_km,
            geojson_str   = geojson_str,
            elevation_data_json = elevation_graph_data,
            efforts_data_json   = efforts_data_json,
            chart_data_json     = chart_data_json,
            center_lat    = center_lat,
            center_lon    = center_lon,
            zoom          = zoom,
            session_id    = session_id,
        )

        session['_map2d_html_cache'] = {
            'signature': signature,
            'html': html,
        }

        logger.info(f"2D Map generated for session {session_id}")
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Error generating 2D map: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating 2D map: {str(e)}")
