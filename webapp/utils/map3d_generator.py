"""
BUILDER 3D MAP - Main orchestrator for 3D map visualization
"""

import json
import logging
import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Any

# Import moduli locali
from .map3d_core import (
    export_traccia_geojson,
    calculate_zoom_level,
    prepare_efforts_data
)
from .map3d_renderer import generate_3d_map_html as render_html

# Import config
import sys
from pathlib import Path
_root_path = str(Path(__file__).parent.parent.parent)
if _root_path not in sys.path:
    sys.path.insert(0, _root_path)
from config import get_maptiler_key

logger = logging.getLogger(__name__)


def generate_3d_map_html(df: pd.DataFrame, efforts: List[Tuple[int, int, float]], 
                         sprints: List[Dict[str, Any]], ftp: float, weight: float) -> str:
    """
    Genera HTML interattivo per visualizzare traccia 3D con MapTiler GL JS.
    
    Orchestrates data processing from map3d_core and rendering from map3d_renderer.
    
    Args:
        df: DataFrame con dati attività (lat, lon, alt, power, etc)
        efforts: Lista efforts (start, end, avg_power)
        sprints: Lista sprints (start, end, avg_power)
        ftp: Functional Threshold Power
        weight: Peso atleta
        
    Returns:
        String HTML completo per visualizzazione 3D
    """
    try:
        logger.info("Generazione mappa 3D (orchestrator)...")
        
        # ===== STEP 1: Data Extraction =====
        # Use complete DataFrame for all calculations (including GPS-less points with power data)
        # But filter GPS coordinates for visualization only
        lat_all = df['position_lat'].values
        lon_all = df['position_long'].values
        nan_mask = (~np.isnan(lat_all)) & (~np.isnan(lon_all))
        range_mask = (np.abs(lat_all) <= 90) & (np.abs(lon_all) <= 180)
        zero_mask = ~((np.abs(lat_all) < 1e-9) & (np.abs(lon_all) < 1e-9))
        valid_mask = nan_mask & range_mask & zero_mask
        df_geom = df.loc[valid_mask].copy()  # For GeoJSON visualization only
        logger.info(f"Dati geografici: {len(df_geom)} punti validi su {len(df)} totali")
        
        # ===== STEP 2: Coordinate Extraction & GeoJSON =====
        # Estrai traccia GeoJSON dal DF filtrato per GPS (visualization)
        geojson_data, orig_indices = export_traccia_geojson(df_geom)
        geojson_str = json.dumps(geojson_data)

        # ===== STEP 3: Map Centering & Zoom =====
        lat = df_geom['position_lat'].values
        lon = df_geom['position_long'].values
        
        # Valida dati geografici
        if len(lat) == 0 or len(lon) == 0:
            raise ValueError("Nessun dato geografico valido disponibile")
        
        # Ensure we have arrays with proper shape
        lat = np.atleast_1d(lat)
        lon = np.atleast_1d(lon)
        
        # Valida che non tutti siano NaN
        if np.isnan(lat).all() or np.isnan(lon).all():
            raise ValueError("Tutti i valori di coordinate sono NaN - impossibile creare mappa 3D")
        
        # Calcola centro (ignora NaN)
        lat_min = float(np.nanmin(lat))
        lat_max = float(np.nanmax(lat))
        lon_min = float(np.nanmin(lon))
        lon_max = float(np.nanmax(lon))
        
        center_lat = float(np.nanmean([lat_min, lat_max]))
        center_lon = float(np.nanmean([lon_min, lon_max]))
        
        # Calcola zoom basato sull'extent
        zoom = calculate_zoom_level(lat, lon)
        
        # ===== STEP 4: Track Statistics =====
        # (elevation_gain and power are calculated in map3d_core as needed)
        
        # ===== STEP 5: Elevation Data Preparation =====
        alt_values = df['altitude'].values if 'altitude' in df.columns else np.zeros(len(df))
        dist_km_values = df['distance_km'].values if 'distance_km' in df.columns else np.zeros(len(df))
        alt_total = alt_values.tolist()
        dist_total = dist_km_values.tolist()
        
        # ===== STEP 6: Efforts Data Calculation (Using Core Module) =====
        # Prepare data for core processing - use df (complete) for energy calcs to include all power data
        efforts_data_json = prepare_efforts_data(
            df, efforts, sprints, ftp, weight, geojson_data, 
            orig_indices, alt_values, dist_km_values
        )
        
        # Parse to get efforts_list for elevation graph
        efforts_list = json.loads(efforts_data_json)
        elevation_graph_data = json.dumps({
            'distance': dist_total, 
            'altitude': alt_total, 
            'efforts': efforts_list
        })
        
        # ===== STEP 7: HTML Rendering (Using Renderer Module) =====
        html = render_html(
            efforts_data_json=efforts_data_json,
            elevation_data_json=elevation_graph_data,
            geojson_str=geojson_str,
            maptiler_key=get_maptiler_key(),
            center_lat=center_lat,
            center_lon=center_lon,
            zoom=zoom,
            distance_km=distance_km
        )
        
        logger.info("Mappa 3D generata con successo")
        return html
        
    except Exception as e:
        logger.error(f"Errore generazione mappa 3D: {e}", exc_info=True)
        raise
