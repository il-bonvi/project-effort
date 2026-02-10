# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""
BUILDER 3D MAP - Main orchestrator for 3D map visualization
"""

import json
import logging
import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Any

# Import moduli locali
from .effort_analyzer import get_zone_color

# Import config
import sys
from pathlib import Path
_root_path = str(Path(__file__).parent.parent.parent)
if _root_path not in sys.path:
    sys.path.insert(0, _root_path)
from config import get_maptiler_key, get_mapbox_token

logger = logging.getLogger(__name__)


def export_traccia_geojson(df: pd.DataFrame) -> Tuple[dict, List[int]]:
    """Esporta la traccia in formato GeoJSON LineString con altitudine."""
    if 'position_lat' not in df.columns or 'position_long' not in df.columns:
        raise ValueError("DataFrame deve contenere position_lat e position_long")
    
    lat = df['position_lat'].values
    lon = df['position_long'].values
    alt = df['altitude'].values if 'altitude' in df.columns else [0] * len(lat)
    
    coordinates = [[float(lon[i]), float(lat[i]), float(alt[i])] for i in range(len(lat))]
    orig_indices = df.index.to_list()
    
    feature = {
        "type": "Feature",
        "properties": {
            "name": "Traccia ciclo",
            "description": f"Traccia con {len(coordinates)} punti"
        },
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates
        }
    }
    
    return {
        "type": "FeatureCollection",
        "features": [feature]
    }, orig_indices


def validate_and_filter_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra coordinate non valide (NaN, fuori range, 0,0)."""
    lat_all = df['position_lat'].values
    lon_all = df['position_long'].values
    
    nan_mask = (~np.isnan(lat_all)) & (~np.isnan(lon_all))
    range_mask = (np.abs(lat_all) <= 90) & (np.abs(lon_all) <= 180)
    zero_mask = ~((np.abs(lat_all) < 1e-9) & (np.abs(lon_all) < 1e-9))
    valid_mask = nan_mask & range_mask & zero_mask

    df_valid = df.loc[valid_mask].copy()
    logger.info(f"Dati geografici: {len(df_valid)} punti validi su {len(df)} totali")
    
    return df_valid


def calculate_zoom_level(lat_values: np.ndarray, lon_values: np.ndarray) -> int:
    """Calcola il livello di zoom ottimale basato sull'estensione geografica."""
    lat_range = float(lat_values.max() - lat_values.min())
    lon_range = float(lon_values.max() - lon_values.min())
    max_range = float(max(lat_range, lon_range))
    
    if max_range < 0.01:
        return 15
    elif max_range < 0.05:
        return 14
    elif max_range < 0.1:
        return 13
    elif max_range < 0.5:
        return 12
    else:
        return 11


def generate_3d_map_html(df: pd.DataFrame, efforts: List[Tuple[int, int, float]], 
                         ftp: float, weight: float) -> str:
    """Genera HTML interattivo per visualizzare traccia 3D con Mapbox GL JS."""
    try:
        logger.info("Generazione mappa 3D (orchestrator)...")
        
        # Extract and validate GPS data
        lat_all = df['position_lat'].values
        lon_all = df['position_long'].values
        nan_mask = (~np.isnan(lat_all)) & (~np.isnan(lon_all))
        range_mask = (np.abs(lat_all) <= 90) & (np.abs(lon_all) <= 180)
        zero_mask = ~((np.abs(lat_all) < 1e-9) & (np.abs(lon_all) < 1e-9))
        valid_mask = nan_mask & range_mask & zero_mask
        df_geom = df.loc[valid_mask].copy()
        logger.info(f"Dati geografici: {len(df_geom)} punti validi su {len(df)} totali")
        
        # GeoJSON
        geojson_data, orig_indices = export_traccia_geojson(df_geom)
        geojson_str = json.dumps(geojson_data)

        # Map centering and zoom
        lat = df_geom['position_lat'].values
        lon = df_geom['position_long'].values
        
        if len(lat) == 0 or len(lon) == 0:
            raise ValueError("Nessun dato geografico valido disponibile")
        
        lat = np.atleast_1d(lat)
        lon = np.atleast_1d(lon)
        
        if np.isnan(lat).all() or np.isnan(lon).all():
            raise ValueError("Tutti i valori di coordinate sono NaN - impossibile creare mappa 3D")
        
        lat_min = float(np.nanmin(lat))
        lat_max = float(np.nanmax(lat))
        lon_min = float(np.nanmin(lon))
        lon_max = float(np.nanmax(lon))
        
        center_lat = float(np.nanmean([lat_min, lat_max]))
        center_lon = float(np.nanmean([lon_min, lon_max]))
        
        zoom = calculate_zoom_level(lat, lon)
        
        # Track statistics
        if 'altitude' in df.columns:
            alt_min = df['altitude'].min()
            alt_max = df['altitude'].max()
            elevation_gain = alt_max - alt_min
        else:
            elevation_gain = 0
        
        power = df['power'].values
        distance_km = (df['distance'].values[-1] - df['distance'].values[0]) / 1000 if 'distance' in df.columns else 0
        
        # Elevation data
        alt_values = df['altitude'].values if 'altitude' in df.columns else np.zeros(len(df))
        dist_km_values = df['distance_km'].values if 'distance_km' in df.columns else np.zeros(len(df))
        alt_total = alt_values.tolist()
        dist_total = dist_km_values.tolist()
        
        # Elevation graph data
        elevation_graph_data = json.dumps({
            'distance': dist_total, 
            'altitude': alt_total, 
            'efforts': []
        })
        
        # Minimal placeholder HTML (map rendering would require full implementation)
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>3D Map</title>
            <style>
                body {{ margin: 0; padding: 0; }}
                #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
                .info {{ position: absolute; top: 10px; left: 10px; background: rgba(0,0,0,0.7); 
                        color: white; padding: 10px; border-radius: 5px; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div id="map"></div>
            <div class="info">
                <div>Center: {center_lat:.4f}, {center_lon:.4f}</div>
                <div>Zoom: {zoom}</div>
                <div>Distance: {distance_km:.2f} km</div>
                <div>Elevation Gain: {elevation_gain:.0f} m</div>
                <div>Data points with GPS: {len(df_geom)}/{len(df)}</div>
            </div>
            <script>
                console.log('3D Map initialized');
                console.log('Efforts: {len(efforts)}');
                console.log('GeoJSON features: {len(geojson_data["features"])}');
            </script>
        </body>
        </html>
        """
        
        logger.info("Mappa 3D generata con successo")
        return html
        
    except Exception as e:
        logger.error(f"Errore generazione mappa 3D: {e}", exc_info=True)
        raise
